# GEO Exposure Pilot

This project contains a 20-query pilot measurement study of GEO/RAG source exposure in generative search.

## Repository Layout

```text
geo_exposure_pilot/
├── README.md
├── config/
│   └── queries.csv
├── src/
│   ├── collect_openai_web_search.py
│   ├── inspect_outputs.py
│   └── fresh_page_audit.py
├── data/
│   ├── raw/
│   ├── processed/
│   ├── collections/
│   └── fresh_page_audit/
├── reports/
│   ├── 初步结果_2026_0602.md
│   ├── 每周工作.md
│   └── tables/
└── docs/
    ├── experiment_plan_v2.md
    └── api_route.md
```

## Experiment Count

Use one clean experimental count for reporting:

- Formal collection experiment: 1 OpenAI API pilot.
- Scope: 20 queries, 1 run per query.
- Output scale: 91 final citation rows, 796 source-pool rows, 792 normalized unique URLs, and 675 successfully fetched text bodies.

Fresh page audit and manual case review are analysis stages, not separate collection experiments.

## Quick Start

Inspect existing outputs:

```bash
cd /home/walnutpz/research-harness

.venv/bin/python experiments/geo_exposure_pilot/src/inspect_outputs.py --write-report
```

Regenerate the fresh page audit from current citation/source CSVs:

```bash
.venv/bin/python experiments/geo_exposure_pilot/src/fresh_page_audit.py
```

Run a fresh collection only if you intentionally want to overwrite current data:

```bash
export OPENAI_API_KEY="..."

.venv/bin/python experiments/geo_exposure_pilot/src/collect_openai_web_search.py \
  --query-ids Q01,Q02,Q03,Q04,Q05,Q06,Q07,Q08,Q09,Q10,Q11,Q12,Q13,Q14,Q15,Q16,Q17,Q18,Q19,Q20 \
  --model gpt-5.5 \
  --prompt-profile minimal \
  --reasoning-effort low \
  --search-context-size medium \
  --runs 1 \
  --overwrite
```

## Important Files

- `config/queries.csv`: canonical 20-query manifest.
- `data/raw/`: raw OpenAI Responses API JSON files, one per query run.
- `data/processed/openai_web_search_results.jsonl`: normalized answer/source/citation summaries.
- `data/processed/citations.csv`: final citation rows.
- `data/processed/sources.csv`: source-pool rows exposed by API web-search calls.
- `data/fresh_page_audit/`: normalized URL inventory, page/PDF fetch manifest, extracted text cache, and review queue.
- `reports/初步结果_2026_0602.md`: concise advisor-facing progress report.
- `reports/tables/pilot_queries_for_report.xlsx`: two-column query table for slides or advisor updates.

## Method Notes

The study keeps two exposure layers separate:

- Final citations: URLs visible as citations in the generated answer.
- Source pool: URLs returned in API web-search source metadata, including pages not finally cited.

Do not merge these layers into one prevalence number.
