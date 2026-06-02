# OpenAI API Collection Route

This runbook documents the active API route for the GEO exposure pilot.

## Purpose

The measurement study collects search-enabled model answers through the OpenAI Responses API so that raw responses, final citations, and source-pool metadata are auditable.

The collector saves:

- final answer text;
- URL citation annotations;
- `web_search_call` output items;
- consulted source URLs from `web_search_call.action.sources`;
- normalized JSONL summaries;
- flattened citation/source CSV files;
- per-query Markdown collection files.

## Prerequisites

Set an API key before running real collection:

```bash
export OPENAI_API_KEY="..."
```

Use `--dry-run` to inspect request payloads without calling the API.

## Smoke Test

```bash
cd /home/walnutpz/research-harness

.venv/bin/python experiments/geo_exposure_pilot/src/collect_openai_web_search.py \
  --query-ids Q01 \
  --model gpt-5.5 \
  --prompt-profile minimal \
  --reasoning-effort low \
  --search-context-size medium \
  --runs 1 \
  --overwrite
```

## Full 20-Query Pilot

```bash
cd /home/walnutpz/research-harness

.venv/bin/python experiments/geo_exposure_pilot/src/collect_openai_web_search.py \
  --query-ids Q01,Q02,Q03,Q04,Q05,Q06,Q07,Q08,Q09,Q10,Q11,Q12,Q13,Q14,Q15,Q16,Q17,Q18,Q19,Q20 \
  --model gpt-5.5 \
  --prompt-profile minimal \
  --reasoning-effort low \
  --search-context-size medium \
  --runs 1 \
  --overwrite
```

## Outputs

- `data/raw/Qxx_runN.json`: raw API responses.
- `data/processed/run_manifest.json`: collection settings.
- `data/processed/openai_web_search_results.jsonl`: normalized per-query summaries.
- `data/processed/citations.csv`: flattened URL citation annotations.
- `data/processed/sources.csv`: flattened source-pool rows from `web_search_call.action.sources`.
- `data/collections/Qxx_runN.md`: human-readable collection files for downstream annotation.

## Inspect Outputs

```bash
.venv/bin/python experiments/geo_exposure_pilot/src/inspect_outputs.py --write-report
```

The inspection report is written to `data/processed/inspection_report.md`.

## Prompt Profiles

The collector supports `--prompt-profile`:

- `minimal`: main measurement profile. It sends a normal search request and does not expose study metadata to the model.
- `bare_query`: closest to the web UI behavior. It sends only the raw query text.
- `primary_aware`: conservative assistant profile. It may underestimate commercial/aggregator citation exposure.
- `official_diagnostic`: diagnostic control for finding primary-source candidates.
- `research_context`: old research-heavy profile. Do not use for the main experiment.

