#!/usr/bin/env python3
"""Reduce collected outputs to public metadata-only CSVs.

The collection and page-audit scripts keep richer local artifacts for review.
Before publishing the repository, this script strips answer snippets and URL
query strings from the tracked CSVs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import urllib.parse
from collections import defaultdict
from pathlib import Path
from typing import Any


RUNS = [
    ("pilot_20/openai_20x1", "fresh_page_audit"),
    ("benchmark_100/openai_100x1", "page_audit"),
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def public_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url.strip())
    if not parsed.scheme or not parsed.netloc:
        return url.strip().split("?", 1)[0].split("#", 1)[0]
    return urllib.parse.urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower().removeprefix("www."),
            parsed.path or "/",
            "",
            "",
        )
    )


def domain(url: str) -> str:
    return urllib.parse.urlsplit(url).netloc.lower().removeprefix("www.")


def url_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def split_semicolon(value: str) -> list[str]:
    return [part for part in value.split(";") if part]


def sanitize_citations(path: Path) -> None:
    rows = []
    for row in read_csv(path):
        url = public_url(row["url"])
        rows.append(
            {
                "query_id": row["query_id"],
                "run_id": row["run_id"],
                "citation_order": row["citation_order"],
                "url": url,
                "domain": domain(url),
                "title": row.get("title", ""),
            }
        )
    write_csv(path, rows, ["query_id", "run_id", "citation_order", "url", "domain", "title"])


def sanitize_sources(path: Path) -> None:
    rows = []
    for row in read_csv(path):
        url = public_url(row["url"])
        rows.append(
            {
                "query_id": row["query_id"],
                "run_id": row["run_id"],
                "source_order": row["source_order"],
                "url": url,
                "domain": domain(url),
                "title": row.get("title", ""),
                "source_type": row.get("source_type", ""),
            }
        )
    write_csv(path, rows, ["query_id", "run_id", "source_order", "url", "domain", "title", "source_type"])


def sanitize_inventory(path: Path) -> None:
    grouped: dict[str, dict[str, Any]] = {}
    query_ids: dict[str, set[str]] = defaultdict(set)
    citation_orders: dict[str, list[str]] = defaultdict(list)
    titles: dict[str, set[str]] = defaultdict(set)

    for row in read_csv(path):
        url = public_url(row["url"])
        if url not in grouped:
            grouped[url] = {
                "url_id": url_id(url),
                "url": url,
                "domain": domain(url),
                "in_final_citation": False,
                "source_count": 0,
                "citation_count": 0,
            }
        rec = grouped[url]
        rec["in_final_citation"] = rec["in_final_citation"] or row.get("in_final_citation") == "True"
        rec["source_count"] += int(row.get("source_count") or 0)
        rec["citation_count"] += int(row.get("citation_count") or 0)
        query_ids[url].update(split_semicolon(row.get("query_ids", "")))
        citation_orders[url].extend(split_semicolon(row.get("citation_orders", "")))
        if row.get("titles"):
            titles[url].add(row["titles"])

    rows = []
    for url, rec in grouped.items():
        rows.append(
            {
                **rec,
                "in_final_citation": str(rec["in_final_citation"]),
                "query_ids": ";".join(sorted(query_ids[url])),
                "citation_orders": ";".join(citation_orders[url]),
                "titles": " | ".join(sorted(titles[url]))[:500],
            }
        )
    rows.sort(key=lambda r: (r["in_final_citation"] != "True", r["query_ids"], r["domain"], r["url"]))
    write_csv(
        path,
        rows,
        ["url_id", "url", "domain", "query_ids", "in_final_citation", "citation_orders", "titles", "source_count", "citation_count"],
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default="data")
    args = parser.parse_args()

    data_root = Path(args.data_root)
    for run, audit_dir in RUNS:
        run_root = data_root / run
        sanitize_citations(run_root / "processed" / "citations.csv")
        sanitize_sources(run_root / "processed" / "sources.csv")
        sanitize_inventory(run_root / audit_dir / "url_inventory.csv")


if __name__ == "__main__":
    main()
