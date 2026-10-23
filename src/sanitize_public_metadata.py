#!/usr/bin/env python3
"""Reduce collected outputs to public metadata-only CSVs.

The collection and page-audit scripts keep richer local artifacts for review.
This script strips answer snippets and URL query strings from local CSV copies.
Neither the original artifacts nor the sanitized copies belong in Git.
"""

from __future__ import annotations

import argparse
import csv
import urllib.parse
from pathlib import Path
from typing import Any

from fresh_page_audit import domain, norm_url, url_id


EXP_ROOT = Path(__file__).resolve().parent.parent

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


def sanitize_citations(path: Path) -> None:
    rows = []
    for row in read_csv(path):
        url = public_url(row["url"])
        rows.append(
            {
                "query_id": row["query_id"],
                "run_id": row["run_id"],
                "citation_order": row["citation_order"],
                "url_id": row.get("url_id") or url_id(norm_url(row["url"])),
                "url": url,
                "domain": domain(url),
                "title": row.get("title", ""),
            }
        )
    write_csv(path, rows, ["query_id", "run_id", "citation_order", "url_id", "url", "domain", "title"])


def sanitize_sources(path: Path) -> None:
    rows = []
    for row in read_csv(path):
        url = public_url(row["url"])
        rows.append(
            {
                "query_id": row["query_id"],
                "run_id": row["run_id"],
                "source_order": row["source_order"],
                "url_id": row.get("url_id") or url_id(norm_url(row["url"])),
                "url": url,
                "domain": domain(url),
                "title": row.get("title", ""),
                "source_type": row.get("source_type", ""),
            }
        )
    write_csv(path, rows, ["query_id", "run_id", "source_order", "url_id", "url", "domain", "title", "source_type"])


def sanitize_inventory(path: Path) -> None:
    rows = []
    for row in read_csv(path):
        url = public_url(row["url"])
        # Redaction changes the display URL, never the page identity or its counts.
        rows.append({**row, "url": url, "domain": domain(url)})
    rows.sort(key=lambda r: (r["in_final_citation"] != "True", r["query_ids"], r["domain"], r["url"]))
    write_csv(
        path,
        rows,
        ["url_id", "url", "domain", "query_ids", "in_final_citation", "citation_orders", "titles", "source_count", "citation_count"],
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default=str(EXP_ROOT / "data"))
    args = parser.parse_args()

    data_root = Path(args.data_root)
    for run, audit_dir in RUNS:
        run_root = data_root / run
        sanitize_citations(run_root / "processed" / "citations.csv")
        sanitize_sources(run_root / "processed" / "sources.csv")
        sanitize_inventory(run_root / audit_dir / "url_inventory.csv")


if __name__ == "__main__":
    main()
