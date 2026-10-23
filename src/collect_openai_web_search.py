from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


API_URL = "https://api.openai.com/v1/responses"
EXP_ROOT = Path(__file__).resolve().parent.parent


PROMPT_PROFILES = {
    "minimal": {
        "instructions": "Use web search to answer the user's query naturally. Include inline citations for web-supported claims.",
        "user_template": "Please search the web and answer this query with citations:\n\n{query}",
    },
    "bare_query": {
        "instructions": "Use web search when useful. Answer naturally.",
        "user_template": "{query}",
    },
    "primary_aware": {
        "instructions": """Use web search to answer the user's query with inline citations.

Prefer primary/official sources for concrete facts, pricing, deadlines, medical/legal/tax/safety claims, and product plan details. If review, ranking, affiliate, commercial, or aggregator pages appear useful, cite them mainly for recommendation context.""",
        "user_template": "Please search the web and answer this query with citations:\n\n{query}",
    },
    "official_diagnostic": {
        "instructions": """Use web search to answer the user's query with inline citations.

Actively search for official, primary, government, vendor, regulatory, clinical, or documentation sources. Use secondary review or aggregator pages only when no primary source is available. This is a diagnostic control, not the main exposure measurement condition.""",
        "user_template": "Please search the web and answer this query with citations:\n\n{query}",
    },
    "research_context": {
        "instructions": """You are collecting data for a measurement study on GEO exposure and source displacement in generative search.

Behave like a search-enabled assistant answering the user's query with web evidence.

Requirements:
- Use web search.
- Produce a natural ChatGPT Search-style answer with inline citations.
- Include enough detail that later annotators can judge source exposure, source displacement, and influence.
- Do not claim that any page is malicious. Use neutral language.
- End with a short 'Collection notes' paragraph describing any visible source-quality concerns.""",
        "user_template": """User query: {query}

Query metadata:
- query_id: {query_id}
- category: {category}
- risk_level: {risk_level}
- risk_hypothesis: {risk_hypothesis}
- expected_primary_sources: {expected_primary_sources}
- expected_failure_modes: {expected_failure_modes}

Answer the user query as a search-enabled assistant. Use inline citations and keep the answer focused on what a real user would need to decide.""",
    },
}


def read_queries(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = {"query_id", "query", "category", "risk_level"} - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing query columns: {', '.join(sorted(missing))}")
        rows = list(reader)
    ids: set[str] = set()
    for row in rows:
        query_id = row["query_id"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", query_id):
            raise ValueError(f"Invalid query_id for an output filename: {query_id!r}")
        if query_id in ids:
            raise ValueError(f"Duplicate query_id: {query_id}")
        if not row["query"].strip():
            raise ValueError(f"Empty query: {query_id}")
        ids.add(query_id)
    if not rows:
        raise ValueError(f"No queries in {path}")
    return rows


def select_queries(rows: list[dict[str, str]], query_ids: list[str]) -> list[dict[str, str]]:
    if not query_ids:
        return rows
    wanted = set(query_ids)
    missing = wanted - {row["query_id"] for row in rows}
    if missing:
        raise ValueError(f"Unknown query IDs: {', '.join(sorted(missing))}")
    return [row for row in rows if row["query_id"] in wanted]


def text_contents(raw: dict[str, Any]) -> list[dict[str, Any]]:
    chunks = []
    for item in raw.get("output", []) or []:
        if item.get("type") != "message":
            continue
        for content in item.get("content", []) or []:
            if content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                chunks.append(content)
    return chunks


def response_output_text(raw: dict[str, Any]) -> str:
    chunks = text_contents(raw)
    if chunks:
        return "\n".join(content["text"] for content in chunks)
    return raw.get("output_text") or ""


def normalize_citation(annotation: dict[str, Any]) -> dict[str, Any] | None:
    if annotation.get("type") != "url_citation":
        return None
    nested = annotation.get("url_citation")
    if isinstance(nested, dict):
        return {
            "url": nested.get("url"),
            "title": nested.get("title"),
            "start_index": nested.get("start_index"),
            "end_index": nested.get("end_index"),
            "raw": annotation,
        }
    return {
        "url": annotation.get("url"),
        "title": annotation.get("title"),
        "start_index": annotation.get("start_index"),
        "end_index": annotation.get("end_index"),
        "raw": annotation,
    }


def collect_citations(raw: dict[str, Any]) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    offset = 0
    for content in text_contents(raw):
        text = content["text"]
        for annotation in content.get("annotations", []) or []:
            citation = normalize_citation(annotation)
            if not citation:
                continue
            start = citation.get("start_index")
            end = citation.get("end_index")
            if isinstance(start, int) and isinstance(end, int):
                if not 0 <= start <= end <= len(text):
                    raise ValueError(f"Citation span {start}..{end} exceeds its text block")
                citation["cited_text_span"] = text[start:end]
                citation["citation_context"] = text[max(0, start - 180):end + 180].replace("\n", " ")
                # API offsets belong to this block; exported offsets address the joined answer.
                citation["start_index"] = offset + start
                citation["end_index"] = offset + end
            citations.append(citation)
        offset += len(text) + 1
    return citations


def collect_web_search_calls(raw: dict[str, Any]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for item in raw.get("output", []) or []:
        if item.get("type") == "web_search_call":
            calls.append(item)
    return calls


def collect_sources(raw: dict[str, Any]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for call in collect_web_search_calls(raw):
        action = call.get("action") or {}
        for source in action.get("sources", []) or []:
            url = source.get("url")
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            sources.append(source)
    return sources


def make_input(row: dict[str, str], prompt_profile: str) -> str:
    return PROMPT_PROFILES[prompt_profile]["user_template"].format(**row)


def make_payload(row: dict[str, str], args: argparse.Namespace) -> dict[str, Any]:
    return {
        "model": args.model,
        "reasoning": {"effort": args.reasoning_effort},
        "tools": [{"type": "web_search", "search_context_size": args.search_context_size}],
        "tool_choice": "required",
        "include": ["web_search_call.action.sources"],
        "instructions": PROMPT_PROFILES[args.prompt_profile]["instructions"],
        "input": make_input(row, args.prompt_profile),
    }


def append_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


def post_response(payload: dict[str, Any], api_key: str, timeout: int) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"OpenAI API HTTP {exc.code}: {body}") from exc


def write_markdown(path: Path, row: dict[str, str], summary: dict[str, Any]) -> None:
    citations = summary.get("citations", [])
    sources = summary.get("sources", [])
    web_calls = summary.get("web_search_calls", [])

    lines = [
        f"# {row['query_id']} OpenAI Web Search Collection",
        "",
        "## Metadata",
        "",
        f"- Query ID: {row['query_id']}",
        f"- Query: `{row['query']}`",
        f"- Category: {row['category']}",
        f"- Risk level: {row['risk_level']}",
        f"- Model: {summary.get('model')}",
        f"- Response ID: {summary.get('response_id')}",
        f"- Collected at: {summary.get('collected_at')}",
        "",
        "## Answer",
        "",
        summary.get("output_text", "").strip(),
        "",
        "## URL Citations",
        "",
        "| # | Title | URL | Span |",
        "|---:|---|---|---|",
    ]
    for index, citation in enumerate(citations, start=1):
        title = (citation.get("title") or "").replace("|", "\\|").replace("\r", " ").replace("\n", " ")
        url = (citation.get("url") or "").replace("|", "%7C")
        span = f"{citation.get('start_index')}..{citation.get('end_index')}"
        lines.append(f"| {index} | {title} | {url} | {span} |")

    lines.extend(
        [
            "",
            "## Complete Sources",
            "",
            "| # | Title | URL | Source Type |",
            "|---:|---|---|---|",
        ]
    )
    for index, source in enumerate(sources, start=1):
        title = (source.get("title") or "").replace("|", "\\|").replace("\r", " ").replace("\n", " ")
        url = (source.get("url") or "").replace("|", "%7C")
        source_type = source.get("type") or source.get("source_type") or ""
        lines.append(f"| {index} | {title} | {url} | {source_type} |")

    lines.extend(["", "## Web Search Calls", "", "```json"])
    lines.append(json.dumps(web_calls, ensure_ascii=False, indent=2))
    lines.extend(["```", ""])

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect GEO exposure answers with OpenAI Responses web_search.")
    parser.add_argument("--queries", default=str(EXP_ROOT / "config/pilot_20/queries.csv"))
    parser.add_argument("--query-ids", default="", help="Comma-separated query IDs. Empty means all.")
    parser.add_argument("--out-dir", default=str(EXP_ROOT / "data/local/pilot_20/openai_20x1"))
    parser.add_argument("--model", default=os.environ.get("OPENAI_WEB_SEARCH_MODEL", "gpt-5.5"))
    parser.add_argument(
        "--prompt-profile",
        choices=sorted(PROMPT_PROFILES),
        default=os.environ.get("OPENAI_WEB_SEARCH_PROMPT_PROFILE", "minimal"),
        help="Collection prompt profile. Use minimal for the main measurement.",
    )
    parser.add_argument("--reasoning-effort", default=os.environ.get("OPENAI_WEB_SEARCH_REASONING", "low"))
    parser.add_argument("--search-context-size", default=os.environ.get("OPENAI_WEB_SEARCH_CONTEXT_SIZE", "medium"))
    parser.add_argument("--runs", type=int, default=1, help="Independent repeated API calls per query.")
    parser.add_argument("--sleep", type=float, default=1.0)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--overwrite", action="store_true", help="Replace this run's collection and page-audit directories.")
    parser.add_argument("--dry-run", action="store_true", help="Print request payloads without writing files or calling the API.")
    args = parser.parse_args()

    if args.runs < 1 or args.timeout <= 0 or args.sleep < 0:
        parser.error("--runs and --timeout must be positive; --sleep must be nonnegative")
    rows = select_queries(
        read_queries(Path(args.queries)),
        [item.strip() for item in args.query_ids.split(",") if item.strip()],
    )
    requests = [(row, make_payload(row, args)) for row in rows]
    if args.dry_run:
        for row, payload in requests:
            for run_index in range(1, args.runs + 1):
                print(json.dumps({"run_id": f"{row['query_id']}_run{run_index}", "request_payload": payload}, ensure_ascii=False))
        return

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is not set. Set it before running, or use --dry-run.")

    root = Path(args.out_dir)
    if root.exists() and any(root.iterdir()) and not args.overwrite:
        parser.error(f"Output directory is not empty: {root}. Use a new directory or --overwrite.")
    if args.overwrite:
        for name in ("raw", "collections", "processed", "page_audit", "fresh_page_audit"):
            directory = root / name
            if directory.exists():
                shutil.rmtree(directory)
    raw_dir = root / "raw"
    collections_dir = root / "collections"
    data_dir = root / "processed"
    for directory in (raw_dir, collections_dir, data_dir):
        directory.mkdir(parents=True, exist_ok=True)

    summary_path = data_dir / "openai_web_search_results.jsonl"
    manifest_path = data_dir / "run_manifest.json"
    run_manifest = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "model": args.model,
        "prompt_profile": args.prompt_profile,
        "reasoning_effort": args.reasoning_effort,
        "search_context_size": args.search_context_size,
        "runs_per_query": args.runs,
        "query_ids": [row["query_id"] for row in rows],
        "api_url": API_URL,
        "include": ["web_search_call.action.sources"],
        "tool_choice": "required",
        "dry_run": args.dry_run,
    }
    manifest_path.write_text(json.dumps(run_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    citations_csv = data_dir / "citations.csv"
    sources_csv = data_dir / "sources.csv"
    with summary_path.open("w", encoding="utf-8") as summary_file:
        for row, payload in requests:
            for run_index in range(1, args.runs + 1):
                run_id = f"{row['query_id']}_run{run_index}"

                collected_at = datetime.now(timezone.utc).isoformat()
                raw = post_response(payload, api_key=api_key, timeout=args.timeout)

                raw_path = raw_dir / f"{run_id}.json"
                raw_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
                if raw.get("status") != "completed" or raw.get("error"):
                    raise RuntimeError(f"{run_id}: response did not complete; inspect {raw_path}")

                citations = collect_citations(raw)
                sources = collect_sources(raw)
                summary = {
                    "query_id": row["query_id"],
                    "run_id": run_id,
                    "run_index": run_index,
                    "query": row["query"],
                    "category": row["category"],
                    "risk_level": row["risk_level"],
                    "model": args.model,
                    "response_id": raw.get("id"),
                    "collected_at": collected_at,
                    "raw_path": str(raw_path),
                    "output_text": response_output_text(raw),
                    "citations": citations,
                    "sources": sources,
                    "web_search_calls": collect_web_search_calls(raw),
                    "usage": raw.get("usage"),
                    "error": raw.get("error"),
                }
                summary_file.write(json.dumps(summary, ensure_ascii=False) + "\n")
                summary_file.flush()

                citation_rows = []
                for index, citation in enumerate(citations, start=1):
                    citation_rows.append(
                        {
                            "query_id": row["query_id"],
                            "run_id": run_id,
                            "citation_order": index,
                            "url": citation.get("url"),
                            "title": citation.get("title"),
                            "start_index": citation.get("start_index"),
                            "end_index": citation.get("end_index"),
                            "cited_text_span": citation.get("cited_text_span"),
                            "citation_context": citation.get("citation_context"),
                        }
                    )
                append_csv(
                    citations_csv,
                    [
                        "query_id",
                        "run_id",
                        "citation_order",
                        "url",
                        "title",
                        "start_index",
                        "end_index",
                        "cited_text_span",
                        "citation_context",
                    ],
                    citation_rows,
                )

                source_rows = []
                for index, source in enumerate(sources, start=1):
                    source_rows.append(
                        {
                            "query_id": row["query_id"],
                            "run_id": run_id,
                            "source_order": index,
                            "url": source.get("url"),
                            "title": source.get("title"),
                            "source_type": source.get("type") or source.get("source_type"),
                        }
                    )
                append_csv(
                    sources_csv,
                    ["query_id", "run_id", "source_order", "url", "title", "source_type"],
                    source_rows,
                )

                write_markdown(collections_dir / f"{run_id}.md", row, summary)
                print(f"{run_id}: citations={len(citations)} sources={len(sources)}")
                time.sleep(args.sleep)


if __name__ == "__main__":
    main()
