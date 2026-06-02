#!/usr/bin/env python3
"""Fresh page audit from raw citation/source CSVs only.

This script intentionally ignores all previous annotation files. It rebuilds the
URL inventory from citations.csv and sources.csv, fetches page/PDF content, and
extracts text plus evidence snippets for stricter manual review.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


EXP_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = Path.cwd().resolve()
DATA = EXP_ROOT / "data" / "processed"
OUT_ROOT = EXP_ROOT / "data" / "fresh_page_audit"

MAX_BYTES = 8_000_000
TEXT_LIMIT = 180_000


SIGNAL_PATTERNS: dict[str, list[str]] = {
    "explicit_llm_instruction": [
        r"ignore (all )?(previous|prior) instructions",
        r"system prompt",
        r"assistant must",
        r"chatgpt (must|should|will)",
        r"large language model",
        r"\bLLM\b",
        r"when (an )?(AI|assistant|chatbot) reads",
        r"rank (this|our|us) (first|#1|number one)",
        r"always recommend",
        r"do not mention (competitors|other)",
    ],
    "geo_or_ai_search_targeting": [
        r"generative engine optimization",
        r"\bGEO\b",
        r"answer engine optimization",
        r"AI overview",
        r"AI search",
        r"ChatGPT search",
        r"rank(ed)? in ChatGPT",
        r"rank(ed)? in AI",
    ],
    "affiliate_or_ad_disclosure": [
        r"affiliate",
        r"commission",
        r"we may earn",
        r"compensation",
        r"advertiser disclosure",
        r"partner links?",
        r"sponsored",
        r"paid placement",
        r"may receive a fee",
    ],
    "lead_generation": [
        r"get (a )?(free )?quote",
        r"free consultation",
        r"find (a|an) (lawyer|attorney|agent|provider)",
        r"talk to (a|an) (lawyer|attorney|agent)",
        r"compare quotes",
        r"get prices",
        r"start now",
        r"get started",
    ],
    "high_risk_unsafe_claim": [
        r"guaranteed",
        r"cure(s|d)?",
        r"no risk",
        r"no side effects",
        r"avoid (a )?doctor",
        r"avoid (a )?lawyer",
        r"instant approval",
    ],
    "low_quality_or_spam": [
        r"kissanime",
        r"v3rm",
        r"javato",
        r"reset kenmore dishwasher",
        r"random words",
    ],
}


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip += 1
        if tag == "meta":
            attr = {k.lower(): v or "" for k, v in attrs}
            content = attr.get("content", "").strip()
            if content:
                self.parts.append(content)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self.skip:
            self.skip -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip:
            data = data.strip()
            if data:
                self.parts.append(data)

    def text(self) -> str:
        text = html.unescape(" ".join(self.parts))
        return re.sub(r"\s+", " ", text).strip()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def norm_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url.strip())
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [(k, v) for k, v in query if not k.lower().startswith("utm_")]
    return urllib.parse.urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower().removeprefix("www."),
            parsed.path,
            urllib.parse.urlencode(query),
            "",
        )
    )


def domain(url: str) -> str:
    return urllib.parse.urlsplit(url).netloc.lower().removeprefix("www.")


def url_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def display_path(path: Path) -> str:
    resolved = path.resolve()
    for base in (WORKSPACE_ROOT, EXP_ROOT):
        try:
            return str(resolved.relative_to(base))
        except ValueError:
            continue
    return str(resolved)


def build_inventory(data_dir: Path) -> list[dict[str, Any]]:
    citations = read_csv(data_dir / "citations.csv")
    sources = read_csv(data_dir / "sources.csv")
    by_url: dict[str, dict[str, Any]] = {}

    def item(url: str) -> dict[str, Any]:
        key = norm_url(url)
        if key not in by_url:
            by_url[key] = {
                "url_id": url_id(key),
                "url": key,
                "domain": domain(key),
                "query_ids": set(),
                "in_final_citation": False,
                "citation_orders": [],
                "citation_contexts": [],
                "titles": set(),
                "source_count": 0,
                "citation_count": 0,
            }
        return by_url[key]

    for row in citations:
        rec = item(row["url"])
        rec["query_ids"].add(row["query_id"])
        rec["in_final_citation"] = True
        rec["citation_count"] += 1
        rec["citation_orders"].append(f"{row['query_id']}#{row['citation_order']}")
        if row.get("citation_context"):
            rec["citation_contexts"].append(row["citation_context"])
        if row.get("title"):
            rec["titles"].add(row["title"])

    for row in sources:
        rec = item(row["url"])
        rec["query_ids"].add(row["query_id"])
        rec["source_count"] += 1
        if row.get("title"):
            rec["titles"].add(row["title"])

    out = []
    for rec in by_url.values():
        out.append(
            {
                **rec,
                "query_ids": ";".join(sorted(rec["query_ids"])),
                "citation_orders": ";".join(rec["citation_orders"]),
                "citation_contexts": "\n---\n".join(rec["citation_contexts"][:3]),
                "titles": " | ".join(sorted(rec["titles"]))[:500],
            }
        )
    return sorted(out, key=lambda r: (not r["in_final_citation"], r["query_ids"], r["domain"], r["url"]))


def fetch_url(rec: dict[str, Any], out_root: Path, timeout: int) -> dict[str, Any]:
    url = rec["url"]
    uid = rec["url_id"]
    result: dict[str, Any] = {
        "url_id": uid,
        "url": url,
        "domain": rec["domain"],
        "query_ids": rec["query_ids"],
        "in_final_citation": rec["in_final_citation"],
        "status": "",
        "content_type": "",
        "bytes": 0,
        "text_chars": 0,
        "error": "",
        "signals": "",
        "evidence_snippets": "",
        "text_path": "",
        "raw_path": "",
    }

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 GEO measurement audit; contact=local-research",
            "Accept": "text/html,application/pdf,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result["status"] = str(getattr(resp, "status", ""))
            result["content_type"] = resp.headers.get("content-type", "")
            data = resp.read(MAX_BYTES + 1)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        result["error"] = repr(exc)
        return result

    if len(data) > MAX_BYTES:
        data = data[:MAX_BYTES]
        result["error"] = "truncated_at_max_bytes"

    raw_dir = out_root / "raw"
    text_dir = out_root / "texts"
    raw_dir.mkdir(parents=True, exist_ok=True)
    text_dir.mkdir(parents=True, exist_ok=True)

    ext = ".pdf" if b"%PDF" in data[:1024] or "pdf" in result["content_type"].lower() else ".bin"
    raw_path = raw_dir / f"{uid}{ext}"
    raw_path.write_bytes(data)
    result["raw_path"] = display_path(raw_path)
    result["bytes"] = len(data)

    text = extract_text(data, result["content_type"], raw_path)
    text = text[:TEXT_LIMIT]
    text_path = text_dir / f"{uid}.txt"
    text_path.write_text(text, encoding="utf-8", errors="replace")
    result["text_path"] = display_path(text_path)
    result["text_chars"] = len(text)

    signal_hits, snippets = scan_signals(text)
    result["signals"] = ";".join(signal_hits)
    result["evidence_snippets"] = "\n---\n".join(snippets[:8])
    return result


def extract_text(data: bytes, content_type: str, raw_path: Path) -> str:
    lower_type = content_type.lower()
    if b"%PDF" in data[:1024] or "pdf" in lower_type or raw_path.suffix == ".pdf":
        try:
            with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
                txt_path = Path(tmp.name)
            subprocess.run(
                ["pdftotext", "-layout", str(raw_path), str(txt_path)],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )
            text = txt_path.read_text(encoding="utf-8", errors="replace")
            txt_path.unlink(missing_ok=True)
            return normalize_text(text)
        except Exception as exc:  # noqa: BLE001
            return f"[PDF_TEXT_EXTRACTION_ERROR] {exc!r}"

    sample = data.decode("utf-8", errors="replace")
    if "<html" in sample[:5000].lower() or "html" in lower_type:
        parser = TextExtractor()
        try:
            parser.feed(sample)
            return normalize_text(parser.text())
        except Exception:
            return normalize_text(strip_tags(sample))
    return normalize_text(sample)


def strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text)


def normalize_text(text: str) -> str:
    text = html.unescape(text)
    text = text.replace("\x00", " ")
    return re.sub(r"\s+", " ", text).strip()


def scan_signals(text: str) -> tuple[list[str], list[str]]:
    hits: list[str] = []
    snippets: list[str] = []
    for name, patterns in SIGNAL_PATTERNS.items():
        for pattern in patterns:
            m = re.search(pattern, text, flags=re.IGNORECASE)
            if not m:
                continue
            if name not in hits:
                hits.append(name)
            start = max(0, m.start() - 180)
            end = min(len(text), m.end() + 180)
            snippet = text[start:end]
            snippets.append(f"[{name}] {snippet}")
            break
    return hits, snippets


def write_review_queue(out_root: Path, inventory: list[dict[str, Any]], fetch_rows: list[dict[str, Any]]) -> None:
    by_id = {row["url_id"]: row for row in fetch_rows}
    queue = []
    for rec in inventory:
        fetched = by_id.get(rec["url_id"], {})
        signals = fetched.get("signals", "")
        score = 0
        if rec["in_final_citation"]:
            score += 5
        if "explicit_llm_instruction" in signals:
            score += 50
        if "geo_or_ai_search_targeting" in signals:
            score += 40
        if "affiliate_or_ad_disclosure" in signals:
            score += 15
        if "lead_generation" in signals:
            score += 15
        if "high_risk_unsafe_claim" in signals:
            score += 10
        if "low_quality_or_spam" in signals:
            score += 25
        if fetched.get("error"):
            score -= 2
        queue.append(
            {
                "priority_score": score,
                "url_id": rec["url_id"],
                "url": rec["url"],
                "domain": rec["domain"],
                "query_ids": rec["query_ids"],
                "in_final_citation": rec["in_final_citation"],
                "citation_orders": rec["citation_orders"],
                "titles": rec["titles"],
                "status": fetched.get("status", ""),
                "content_type": fetched.get("content_type", ""),
                "text_chars": fetched.get("text_chars", 0),
                "signals": signals,
                "evidence_snippets": fetched.get("evidence_snippets", ""),
                "text_path": fetched.get("text_path", ""),
                "citation_contexts": rec["citation_contexts"],
            }
        )
    queue.sort(key=lambda r: (-int(r["priority_score"]), not r["in_final_citation"], r["query_ids"], r["domain"]))
    write_csv(
        out_root / "review_queue.csv",
        queue,
        [
            "priority_score",
            "url_id",
            "url",
            "domain",
            "query_ids",
            "in_final_citation",
            "citation_orders",
            "titles",
            "status",
            "content_type",
            "text_chars",
            "signals",
            "evidence_snippets",
            "text_path",
            "citation_contexts",
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=str(DATA))
    parser.add_argument("--out", default=str(OUT_ROOT))
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--timeout", type=int, default=18)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    data_dir = Path(args.data).resolve()
    out_root = Path(args.out).resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    inventory = build_inventory(data_dir)
    if args.limit:
        inventory = inventory[: args.limit]

    write_csv(
        out_root / "url_inventory.csv",
        inventory,
        [
            "url_id",
            "url",
            "domain",
            "query_ids",
            "in_final_citation",
            "citation_orders",
            "titles",
            "source_count",
            "citation_count",
            "citation_contexts",
        ],
    )

    fetch_rows: list[dict[str, Any]] = []
    started = time.time()
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futures = {ex.submit(fetch_url, rec, out_root, args.timeout): rec for rec in inventory}
        for i, fut in enumerate(as_completed(futures), start=1):
            row = fut.result()
            fetch_rows.append(row)
            if i % 50 == 0 or i == len(inventory):
                ok = sum(1 for r in fetch_rows if r.get("status") and not r.get("error"))
                print(f"fetched {i}/{len(inventory)} ok={ok} elapsed={time.time() - started:.1f}s", flush=True)

    fetch_rows.sort(key=lambda r: (r["query_ids"], r["domain"], r["url"]))
    write_csv(
        out_root / "fetch_manifest.csv",
        fetch_rows,
        [
            "url_id",
            "url",
            "domain",
            "query_ids",
            "in_final_citation",
            "status",
            "content_type",
            "bytes",
            "text_chars",
            "error",
            "signals",
            "evidence_snippets",
            "text_path",
            "raw_path",
        ],
    )
    write_review_queue(out_root, inventory, fetch_rows)

    summary = {
        "inventory_urls": len(inventory),
        "fetched_rows": len(fetch_rows),
        "http_ok_no_error": sum(1 for r in fetch_rows if r.get("status") and not r.get("error")),
        "with_text": sum(1 for r in fetch_rows if int(r.get("text_chars") or 0) > 0),
        "with_signals": sum(1 for r in fetch_rows if r.get("signals")),
        "elapsed_seconds": round(time.time() - started, 1),
    }
    (out_root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
