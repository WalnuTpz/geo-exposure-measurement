from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse


OFFICIAL_HINTS = {
    "Q15": ["studentaid.gov", "ed.gov"],
    "Q16": ["irs.gov"],
}


def domain(url: str | None) -> str:
    if not url:
        return ""
    return urlparse(url).netloc.lower().removeprefix("www.")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def raw_status(root: Path, run_ids: list[str]) -> list[str]:
    lines = ["## Raw Responses", ""]
    for run_id in run_ids:
        path = root / "raw" / f"{run_id}.json"
        if not path.exists():
            lines.append(f"- `{run_id}`: MISSING raw file")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        dry = data.get("dry_run")
        response_id = data.get("id")
        model = data.get("model")
        output_count = len(data.get("output", []) or [])
        usage = data.get("usage")
        status = "OK" if response_id and not dry else "CHECK"
        lines.append(
            f"- `{run_id}`: {status}; dry_run={dry}; id={response_id}; "
            f"model={model}; output_items={output_count}; usage={usage}"
        )
    lines.append("")
    return lines


def per_run_counts(summaries: list[dict], citations: list[dict[str, str]], sources: list[dict[str, str]]) -> list[str]:
    lines = ["## Per-Run Counts", "", "| run_id | query_id | citations_jsonl | citations_csv | sources_jsonl | sources_csv | answer_chars |", "|---|---|---:|---:|---:|---:|---:|"]
    citation_counts = Counter(row["run_id"] for row in citations)
    source_counts = Counter(row["run_id"] for row in sources)
    for summary in summaries:
        run_id = summary.get("run_id", "")
        query_id = summary.get("query_id", "")
        answer = summary.get("output_text") or ""
        lines.append(
            f"| {run_id} | {query_id} | {len(summary.get('citations', []) or [])} | "
            f"{citation_counts[run_id]} | {len(summary.get('sources', []) or [])} | "
            f"{source_counts[run_id]} | {len(answer)} |"
        )
    lines.append("")
    return lines


def citation_quality(citations: list[dict[str, str]]) -> list[str]:
    lines = ["## Citation Rows", ""]
    if not citations:
        return lines + ["No citation rows found.", ""]
    missing_url = sum(1 for row in citations if not row.get("url"))
    missing_context = sum(1 for row in citations if not row.get("citation_context"))
    lines.append(f"- Rows: {len(citations)}")
    lines.append(f"- Missing URL: {missing_url}")
    lines.append(f"- Missing citation context: {missing_context}")
    lines.append("")
    lines.append("| run_id | order | domain | title | context_preview |")
    lines.append("|---|---:|---|---|---|")
    for row in citations[:30]:
        context = (row.get("citation_context") or "").replace("|", " ")[:160]
        title = (row.get("title") or "").replace("|", " ")[:80]
        lines.append(f"| {row.get('run_id')} | {row.get('citation_order')} | {domain(row.get('url'))} | {title} | {context} |")
    lines.append("")
    return lines


def domain_summary(rows: list[dict[str, str]], label: str, url_field: str = "url") -> list[str]:
    by_run: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        by_run[row.get("run_id", "")][domain(row.get(url_field))] += 1
    lines = [f"## {label} Domain Summary", ""]
    for run_id, counter in sorted(by_run.items()):
        top = ", ".join(f"{dom} ({count})" for dom, count in counter.most_common(12))
        lines.append(f"- `{run_id}`: {top}")
    lines.append("")
    return lines


def control_checks(citations: list[dict[str, str]], sources: list[dict[str, str]]) -> list[str]:
    lines = ["## Control Checks", ""]
    for query_id, official_domains in OFFICIAL_HINTS.items():
        citation_rows = [row for row in citations if row.get("query_id") == query_id]
        source_rows = [row for row in sources if row.get("query_id") == query_id]
        if not citation_rows and not source_rows:
            continue

        citation_domains = Counter(domain(row.get("url")) for row in citation_rows)
        source_domains = Counter(domain(row.get("url")) for row in source_rows)
        citation_official = sum(
            count for dom, count in citation_domains.items() if any(hint in dom for hint in official_domains)
        )
        source_official = sum(
            count for dom, count in source_domains.items() if any(hint in dom for hint in official_domains)
        )
        citation_total = sum(citation_domains.values())
        source_total = sum(source_domains.values())
        citation_ratio = citation_official / citation_total if citation_total else 0.0
        source_ratio = source_official / source_total if source_total else 0.0
        citation_status = "OK" if citation_ratio >= 0.5 else "CHECK"
        lines.append(
            f"- `{query_id}` citations: {citation_status}; official-like={citation_official}/{citation_total} "
            f"({citation_ratio:.1%}); expected={official_domains}; top={citation_domains.most_common(8)}"
        )
        lines.append(
            f"- `{query_id}` complete sources: INFO; official-like={source_official}/{source_total} "
            f"({source_ratio:.1%}); expected={official_domains}; top={source_domains.most_common(8)}"
        )
    if len(lines) == 2:
        return []
    lines.append("")
    return lines


def recommendations(summaries: list[dict], citations: list[dict[str, str]], sources: list[dict[str, str]]) -> list[str]:
    lines = ["## Recommendations", ""]
    if not summaries:
        lines.append("- No JSONL summaries found. Check whether the selected run has `processed/openai_web_search_results.jsonl`.")
    if citations and any(not row.get("citation_context") for row in citations):
        lines.append("- Some citation rows lack context; inspect raw annotations before annotation.")
    if sources and len(sources) <= len(citations):
        lines.append("- Source rows are not larger than citation rows; complete source capture may not be working.")
    q01_sources = [row for row in sources if row.get("query_id") == "Q01"]
    if q01_sources:
        q01_domains = Counter(domain(row.get("url")) for row in q01_sources)
        lines.append(f"- Q01 has {len(q01_sources)} source rows across {len(q01_domains)} domains; this is enough for exposure analysis.")
    q15_citations = [row for row in citations if row.get("query_id") == "Q15"]
    if q15_citations:
        q15_domains = [domain(row.get("url")) for row in q15_citations]
        if not any("studentaid.gov" in dom or "ed.gov" in dom for dom in q15_domains):
            lines.append("- Q15 citations do not visibly include `studentaid.gov`/`ed.gov`; inspect for source displacement or query ambiguity.")
        else:
            lines.append("- Q15 citations include official/government domains; this is a good control signal.")
    q15_sources = [row for row in sources if row.get("query_id") == "Q15"]
    if q15_sources:
        q15_source_domains = Counter(domain(row.get("url")) for row in q15_sources)
        if q15_source_domains.get("reddit.com", 0) > 0:
            lines.append(
                "- Q15 complete sources include Reddit/non-official pages while final citations are official. "
                "Keep citations and complete source exposure separate in analysis."
            )
    if not lines[-1].startswith("-"):
        lines.append("- No obvious structural issues detected.")
    lines.append("")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outputs", default="experiments/geo_exposure_pilot/data/pilot_20/openai_20x1")
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()

    root = Path(args.outputs)
    data = root / "processed"
    summaries = read_jsonl(data / "openai_web_search_results.jsonl")
    citations = read_csv(data / "citations.csv")
    sources = read_csv(data / "sources.csv")
    run_ids = [row.get("run_id", "") for row in summaries]

    lines: list[str] = ["# OpenAI Web Search Output Inspection", ""]
    lines += raw_status(root, run_ids)
    lines += per_run_counts(summaries, citations, sources)
    lines += citation_quality(citations)
    lines += domain_summary(citations, "Citation")
    lines += domain_summary(sources, "Source")
    lines += control_checks(citations, sources)
    lines += recommendations(summaries, citations, sources)

    report = "\n".join(lines)
    print(report)
    if args.write_report:
        path = data / "inspection_report.md"
        path.write_text(report, encoding="utf-8")
        print(f"\nWrote {path}")


if __name__ == "__main__":
    main()
