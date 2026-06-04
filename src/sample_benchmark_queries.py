#!/usr/bin/env python3
"""Sample a 100-query benchmark-derived query set for GEO exposure measurement.

The sampler intentionally avoids using the previous pilot labels or examples.
It pulls query rows from public benchmark tables and keeps source IDs for
provenance. Some categories are keyword-filtered within broad benchmarks because
there is no dedicated public benchmark for that exact risk category.
"""

from __future__ import annotations

import csv
import json
import random
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from datasets import load_dataset


SEED = 20260602
OUT_DIR = Path("experiments/geo_exposure_benchmark_100")
CONFIG_DIR = OUT_DIR / "config"
RAW_DIR = OUT_DIR / "data" / "benchmark_samples"


@dataclass(frozen=True)
class Row:
    dataset: str
    split: str
    source_item_id: str
    text: str
    raw: dict


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def useful_query(text: str, min_words: int = 3, max_words: int = 18) -> bool:
    text = clean_text(text)
    if not text:
        return False
    if len(text) > 180:
        return False
    words = text.split()
    if len(words) < min_words or len(words) > max_words:
        return False
    if sum(ch.isalpha() for ch in text) < 8:
        return False
    return True


def keyword_filter(keywords: Iterable[str]) -> Callable[[Row], bool]:
    patterns = []
    for keyword in keywords:
        escaped = re.escape(keyword.lower())
        if re.fullmatch(r"[a-z0-9 ]+", keyword.lower()):
            escaped = escaped.replace(r"\ ", r"\s+")
            patterns.append(re.compile(rf"\b{escaped}\b"))
        else:
            patterns.append(re.compile(escaped))

    def _keep(row: Row) -> bool:
        low = row.text.lower()
        return any(pattern.search(low) for pattern in patterns)

    return _keep


def and_filter(*filters: Callable[[Row], bool]) -> Callable[[Row], bool]:
    return lambda row: all(f(row) for f in filters)


def hf_rows(dataset: str, config: str, split: str, offset: int, length: int) -> dict:
    params = urllib.parse.urlencode(
        {
            "dataset": dataset,
            "config": config,
            "split": split,
            "offset": offset,
            "length": length,
        }
    )
    url = f"https://datasets-server.huggingface.co/rows?{params}"
    last_error: Exception | None = None
    for attempt in range(6):
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in {429, 500, 502, 503, 504}:
                raise
            time.sleep(2.0 * (attempt + 1))
        except urllib.error.URLError as exc:
            last_error = exc
            time.sleep(1.0 * (attempt + 1))
    raise RuntimeError(f"failed to fetch {url}: {last_error}")


def beir_row(dataset_name: str, item: dict) -> Row:
    row = item["row"]
    return Row(
        dataset=f"BeIR/{dataset_name}",
        split="queries",
        source_item_id=str(row.get("_id", item.get("row_idx"))),
        text=clean_text(row.get("text", "")),
        raw=item,
    )


def amazon_row(item: dict) -> Row:
    row = item["row"]
    query_id = row.get("query_id", item.get("row_idx"))
    example_id = row.get("example_id", item.get("row_idx"))
    return Row(
        dataset="amazon-science/esci-data",
        split=str(row.get("split", "train")),
        source_item_id=f"query_id={query_id};example_id={example_id}",
        text=clean_text(row.get("query", "")),
        raw=item,
    )


def fetch_sequential(
    dataset: str,
    config: str,
    split: str,
    converter: Callable[[dict], Row],
    limit: int,
    page_size: int = 100,
) -> list[Row]:
    rows: list[Row] = []
    offset = 0
    total = None
    while total is None or offset < total:
        data = hf_rows(dataset, config, split, offset, page_size)
        total = int(data.get("num_rows_total", 0))
        for item in data.get("rows", []):
            rows.append(converter(item))
        offset += page_size
        if len(rows) >= limit:
            break
        time.sleep(0.25)
    return rows


def fetch_random_pages(
    dataset: str,
    config: str,
    split: str,
    converter: Callable[[dict], Row],
    rng: random.Random,
    pages: int = 80,
    page_size: int = 100,
) -> list[Row]:
    first = hf_rows(dataset, config, split, 0, 1)
    total = int(first.get("num_rows_total", 0))
    offsets = sorted({rng.randrange(0, max(1, total - page_size)) for _ in range(pages)})
    if 0 not in offsets:
        offsets.insert(0, 0)
    rows: list[Row] = []
    for offset in offsets:
        data = hf_rows(dataset, config, split, offset, page_size)
        for item in data.get("rows", []):
            rows.append(converter(item))
        time.sleep(0.25)
    return rows


def fetch_first_50(
    dataset: str,
    config: str,
    split: str,
    converter: Callable[[dict], Row],
) -> list[Row]:
    data = hf_rows(dataset, config, split, 0, 50)
    return [converter(item) for item in data.get("rows", [])]


def fetch_first_unique_queries(
    dataset: str,
    config: str,
    split: str,
    converter: Callable[[dict], Row],
    target_unique: int = 50,
    page_size: int = 100,
) -> list[Row]:
    rows: list[Row] = []
    seen: set[str] = set()
    offset = 0
    total = None
    while len(rows) < target_unique and (total is None or offset < total):
        data = hf_rows(dataset, config, split, offset, page_size)
        total = int(data.get("num_rows_total", 0))
        for item in data.get("rows", []):
            row = converter(item)
            key = row.text.lower()
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
            if len(rows) >= target_unique:
                break
        offset += page_size
        time.sleep(0.25)
    return rows


def stream_rows(
    dataset: str,
    config: str | None,
    split: str,
    converter: Callable[[dict, int], Row],
    max_scan: int,
) -> list[Row]:
    if config:
        ds = load_dataset(dataset, config, split=split, streaming=True)
    else:
        ds = load_dataset(dataset, split=split, streaming=True)
    rows: list[Row] = []
    for index, item in enumerate(ds):
        if index >= max_scan:
            break
        rows.append(converter(item, index))
    return rows


def beir_stream_row(dataset_name: str, item: dict, index: int) -> Row:
    return Row(
        dataset=f"BeIR/{dataset_name}",
        split="queries",
        source_item_id=str(item.get("_id", index)),
        text=clean_text(item.get("text", "")),
        raw={"row_idx": index, "row": item},
    )


def amazon_stream_row(item: dict, index: int) -> Row:
    return Row(
        dataset="amazon-science/esci-data",
        split=str(item.get("split", "train")),
        source_item_id=f"query_id={item.get('query_id', index)};example_id={item.get('example_id', index)}",
        text=clean_text(item.get("query", "")),
        raw={"row_idx": index, "row": item},
    )


def clean_product_query(row: Row) -> bool:
    text = row.text.strip()
    if not useful_query(text, min_words=1, max_words=10):
        return False
    if text[0] in "#!):;,.?*-":
        return False
    if sum(ch.isalpha() for ch in text) < 5:
        return False
    if any(ord(ch) > 127 for ch in text):
        return False
    low = text.lower()
    product_terms = [
        "phone",
        "iphone",
        "laptop",
        "headphone",
        "camera",
        "vacuum",
        "battery",
        "charger",
        "monitor",
        "keyboard",
        "mouse",
        "chair",
        "mattress",
        "shoes",
        "boots",
        "alternator",
        "headlight",
        "bulb",
        "syringe",
        "hose",
        "envelope",
        "router",
        "speaker",
        "watch",
        "bag",
        "box",
    ]
    product_matcher = keyword_filter(product_terms)
    if not product_matcher(row):
        return False
    bad_terms = ["return--", "does not need", "not giving", "ring theory", "womanizer", "do not watch"]
    if any(term in low for term in bad_terms):
        return False
    return True


def mental_health_query(row: Row) -> bool:
    low = row.text.lower()
    include = keyword_filter(
        [
            "anxiety",
            "depression",
            "therapy",
            "therapist",
            "panic",
            "mental",
            "counseling",
            "psychologist",
        ]
    )(row)
    exclude_terms = [
        "suicide squad",
        "suicide terrorism",
        "stress fracture",
        "nuclear stress",
        "differential stress",
        "deprivation therapy",
        "occupational therapist",
        "occupational therapy",
        "physical therapy",
        "physical therapist",
        "therapy dog",
        "fascial stretch",
        "great depression",
        "epics of india",
    ]
    return include and not any(term in low for term in exclude_terms)


def technical_troubleshooting_query(row: Row) -> bool:
    low = row.text.lower()
    include_terms = [
        "fix",
        "repair",
        "infected",
        "slow",
        "crash",
        "not working",
        "error",
        "download",
        "install",
        "android",
        "iphone",
        "chrome",
        "windows",
        "printer",
        "wifi",
    ]
    include = keyword_filter(include_terms)(row)
    exclude_terms = [
        "bachelor",
        "programming language",
        "software development companies",
        "email marketing",
        "designing logos",
        "gas fireplace",
        "telephone code",
        "phone number",
        "percentage of terrorists",
    ]
    return include and not any(term in low for term in exclude_terms)


def dedupe_rows(rows: Iterable[Row]) -> list[Row]:
    seen_text: set[str] = set()
    seen_id: set[tuple[str, str]] = set()
    out: list[Row] = []
    for row in rows:
        key_text = row.text.lower()
        key_id = (row.dataset, row.source_item_id)
        if key_text in seen_text or key_id in seen_id:
            continue
        seen_text.add(key_text)
        seen_id.add(key_id)
        out.append(row)
    return out


CATEGORY_META = {
    "product_recommendation": {
        "risk_level": "high",
        "risk_hypothesis": "Product-search queries may surface affiliate comparison, marketplace, or PR pages instead of primary product documentation.",
        "expected_primary_sources": "Manufacturer specs; retailer product pages; independent testing sources",
        "expected_failure_modes": "affiliate comparison; commercial listicle; feature misrepresentation",
        "control_type": "exposure",
    },
    "business_legal_service": {
        "risk_level": "high",
        "risk_hypothesis": "Business/legal queries may cite law-firm SEO, lead-generation, or commercial service pages instead of official or neutral guidance.",
        "expected_primary_sources": "Government agency pages; state filing offices; legal aid or bar association guidance",
        "expected_failure_modes": "law-firm SEO; lead generation; primary-source displacement",
        "control_type": "exposure",
    },
    "health_medical_advice": {
        "risk_level": "high",
        "risk_hypothesis": "Medical advice queries may cite low-authority health pages or commercial wellness content instead of clinical or public-health sources.",
        "expected_primary_sources": "NIH/MedlinePlus; CDC; FDA; clinical or medical association guidance",
        "expected_failure_modes": "weak medical source; commercial health framing; risk disclosure weakening",
        "control_type": "exposure",
    },
    "mental_health_therapy": {
        "risk_level": "high",
        "risk_hypothesis": "Mental-health queries may surface platform marketing, affiliate therapy rankings, forums, or low-quality advice pages.",
        "expected_primary_sources": "NIMH/APA guidance; clinical guidance; platform privacy and safety policies",
        "expected_failure_modes": "affiliate therapy ranking; platform marketing; unsafe reassurance",
        "control_type": "exposure",
    },
    "finance_tax_software": {
        "risk_level": "high",
        "risk_hypothesis": "Finance and tax queries may cite commercial tools or affiliate rankings while underusing official compliance sources.",
        "expected_primary_sources": "IRS/SEC/CFPB guidance; vendor pricing/privacy pages; official forms and instructions",
        "expected_failure_modes": "affiliate finance; compliance-risk underdisclosure; primary-source displacement",
        "control_type": "exposure",
    },
    "technical_troubleshooting": {
        "risk_level": "medium",
        "risk_hypothesis": "Troubleshooting queries may surface content farms, software upsells, or unsafe instructions instead of official support pages.",
        "expected_primary_sources": "Official vendor support; product documentation; security guidance",
        "expected_failure_modes": "content farm; software upsell; unsafe troubleshooting",
        "control_type": "exposure",
    },
    "factual_official_control": {
        "risk_level": "low",
        "risk_hypothesis": "Official factual queries should prefer primary or high-authority sources; commercial or stale pages indicate source displacement.",
        "expected_primary_sources": "Government, institutional, official documentation, or high-authority reference sources",
        "expected_failure_modes": "primary-source displacement; stale aggregator; unnecessary commercial citation",
        "control_type": "control",
    },
    "multi_hop_factual": {
        "risk_level": "low",
        "risk_hypothesis": "Multi-hop factual queries increase retrieval breadth and may reveal source-pool noise or citation mismatch.",
        "expected_primary_sources": "Official pages; reliable encyclopedic or institutional sources",
        "expected_failure_modes": "source-pool noise; weak summary source; citation mismatch",
        "control_type": "control",
    },
    "debate_opinion": {
        "risk_level": "medium",
        "risk_hypothesis": "Debate/opinion queries may cite advocacy or ideologically tilted sources that shape answer framing.",
        "expected_primary_sources": "Policy documents; academic studies; reputable reporting; transparent advocacy sources",
        "expected_failure_modes": "biased framing; advocacy-source dominance; selective evidence",
        "control_type": "exposure",
    },
    "social_community_qa": {
        "risk_level": "medium",
        "risk_hypothesis": "Community-style queries may overuse forum/social content or low-authority explanations.",
        "expected_primary_sources": "Authoritative guidance when applicable; high-quality explanatory sources",
        "expected_failure_modes": "forum overreliance; weak authority; anecdotal framing",
        "control_type": "exposure",
    },
}


def sample_category(
    category: str,
    pool: list[Row],
    n: int,
    rng: random.Random,
    keep: Callable[[Row], bool] | None = None,
    min_words: int = 3,
    max_words: int = 18,
) -> list[Row]:
    candidates = [row for row in dedupe_rows(pool) if useful_query(row.text, min_words=min_words, max_words=max_words)]
    if keep:
        candidates = [row for row in candidates if keep(row)]
    rng.shuffle(candidates)
    if len(candidates) < n:
        raise RuntimeError(f"{category}: only {len(candidates)} candidates for n={n}")
    return candidates[:n]


def write_outputs(samples: dict[str, list[Row]]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "query_id",
        "category",
        "query",
        "source_type",
        "source_dataset",
        "source_split",
        "source_item_id",
        "risk_level",
        "risk_hypothesis",
        "expected_primary_sources",
        "expected_failure_modes",
        "control_type",
    ]

    rows: list[dict[str, str]] = []
    raw_lines: list[str] = []
    counter = 1
    for category, category_rows in samples.items():
        meta = CATEGORY_META[category]
        for row in category_rows:
            query_id = f"B100Q{counter:03d}"
            rows.append(
                {
                    "query_id": query_id,
                    "category": category,
                    "query": row.text,
                    "source_type": "benchmark_original_query",
                    "source_dataset": row.dataset,
                    "source_split": row.split,
                    "source_item_id": row.source_item_id,
                    **meta,
                }
            )
            raw_lines.append(
                json.dumps(
                    {
                        "query_id": query_id,
                        "category": category,
                        "dataset": row.dataset,
                        "split": row.split,
                        "source_item_id": row.source_item_id,
                        "text": row.text,
                        "raw": row.raw,
                    },
                    ensure_ascii=False,
                )
            )
            counter += 1

    with (CONFIG_DIR / "queries.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    (RAW_DIR / "sampled_rows.jsonl").write_text("\n".join(raw_lines) + "\n", encoding="utf-8")

    manifest = {
        "seed": SEED,
        "n_queries": len(rows),
        "categories": {category: len(items) for category, items in samples.items()},
        "method": "stratified benchmark-original query sampling; keyword-filtered within broad benchmarks where no dedicated category benchmark exists",
        "note": "The query text is copied from benchmark query rows. No prior pilot annotations are used.",
    }
    (CONFIG_DIR / "sampling_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> None:
    rng = random.Random(SEED)

    amazon = stream_rows(
        "khanmu2003/amazon-shopping-queries-dataset",
        None,
        "train",
        amazon_stream_row,
        max_scan=20000,
    )
    fiqa = stream_rows(
        "BeIR/fiqa", "queries", "queries", lambda item, index: beir_stream_row("fiqa", item, index), 6500
    )
    nfcorpus = stream_rows(
        "BeIR/nfcorpus", "queries", "queries", lambda item, index: beir_stream_row("nfcorpus", item, index), 3500
    )
    msmarco = stream_rows(
        "BeIR/msmarco", "queries", "queries", lambda item, index: beir_stream_row("msmarco", item, index), 30000
    )
    nq = stream_rows(
        "BeIR/nq", "queries", "queries", lambda item, index: beir_stream_row("nq", item, index), 3500
    )
    hotpotqa = stream_rows(
        "BeIR/hotpotqa",
        "queries",
        "queries",
        lambda item, index: beir_stream_row("hotpotqa", item, index),
        3000,
    )
    touche = stream_rows(
        "BeIR/webis-touche2020",
        "queries",
        "queries",
        lambda item, index: beir_stream_row("webis-touche2020", item, index),
        100,
    )
    quora = stream_rows(
        "BeIR/quora", "queries", "queries", lambda item, index: beir_stream_row("quora", item, index), 12000
    )

    samples = {
        "product_recommendation": sample_category(
            "product_recommendation",
            amazon,
            10,
            rng,
            clean_product_query,
            min_words=1,
            max_words=10,
        ),
        "business_legal_service": sample_category(
            "business_legal_service",
            msmarco,
            10,
            rng,
            keyword_filter(
                [
                    "lawyer",
                    "attorney",
                    "legal",
                    "llc",
                    "business license",
                    "trademark",
                    "insurance",
                    "corporation",
                    "payroll",
                    "tax id",
                    "contractor",
                ]
            ),
        ),
        "health_medical_advice": sample_category(
            "health_medical_advice",
            nfcorpus,
            10,
            rng,
            keyword_filter(
                [
                    "safe",
                    "side effect",
                    "treatment",
                    "disease",
                    "cancer",
                    "diabetes",
                    "blood",
                    "cholesterol",
                    "vitamin",
                    "drug",
                    "diet",
                    "heart",
                ]
            ),
        ),
        "mental_health_therapy": sample_category(
            "mental_health_therapy",
            quora + msmarco,
            10,
            rng,
            mental_health_query,
        ),
        "finance_tax_software": sample_category(
            "finance_tax_software",
            fiqa,
            10,
            rng,
            keyword_filter(
                [
                    "tax",
                    "business",
                    "loan",
                    "debt",
                    "mortgage",
                    "credit",
                    "investment",
                    "expense",
                    "insurance",
                    "retirement",
                ]
            ),
        ),
        "technical_troubleshooting": sample_category(
            "technical_troubleshooting",
            msmarco + quora,
            10,
            rng,
            technical_troubleshooting_query,
        ),
        "factual_official_control": sample_category(
            "factual_official_control",
            nq + msmarco,
            10,
            rng,
            None,
        ),
        "multi_hop_factual": sample_category("multi_hop_factual", hotpotqa, 10, rng),
        "debate_opinion": sample_category("debate_opinion", touche, 10, rng),
        "social_community_qa": sample_category(
            "social_community_qa",
            quora,
            10,
            rng,
            lambda row: row.text.endswith("?") and useful_query(row.text, min_words=5, max_words=20),
        ),
    }

    write_outputs(samples)

    for category, rows in samples.items():
        datasets = sorted({row.dataset for row in rows})
        print(f"{category}: {len(rows)} rows from {', '.join(datasets)}")


if __name__ == "__main__":
    main()
