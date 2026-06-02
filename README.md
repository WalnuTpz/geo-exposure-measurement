# GEO Exposure Pilot

本项目是一个 20 个 query 的 pilot measurement 实验，用来观察生成式搜索系统中的 GEO/RAG source exposure 问题。

实验关注两类来源暴露：

- `final citation`：最终回答中展示给用户的引用链接；
- `source pool`：API raw response 中可见的搜索/来源结果，可能没有进入最终回答。

这两层暴露需要分开分析，不能合并成一个比例。

## 目录结构

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
│   └── tables/
└── docs/
    ├── experiment_plan_v2.md
    └── api_route.md
```

## 实验规模

当前只统计一次正式采集实验：

- 正式采集实验：1 次 OpenAI API pilot；
- query 数量：20 个；
- 每个 query 的运行次数：1 次；
- final citation rows：91；
- source-pool rows：796；
- 规范化后的唯一 URL：792；
- 成功抓取并抽取正文的 URL：675。

`fresh_page_audit` 和人工 case review 属于后续分析阶段，不算新的采集实验。

## 快速开始

检查当前采集输出：

```bash
cd /home/walnutpz/research-harness

.venv/bin/python experiments/geo_exposure_pilot/src/inspect_outputs.py --write-report
```

基于当前 `citations.csv` 和 `sources.csv` 重新生成 fresh page audit：

```bash
.venv/bin/python experiments/geo_exposure_pilot/src/fresh_page_audit.py
```

只有在明确想覆盖当前数据时，才重新运行正式采集：

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

## 重要文件

- `config/queries.csv`：20 个 pilot query 的正式清单。
- `src/collect_openai_web_search.py`：调用 OpenAI web search API，采集回答、final citations、source pool 和 raw response。
- `src/inspect_outputs.py`：检查 raw response、citation/source 数量和基本质量。
- `src/fresh_page_audit.py`：从 citation/source CSV 重建 URL inventory，抓取网页/PDF，抽取正文并生成人工复核队列。
- `data/raw/`：OpenAI Responses API 的原始 JSON，每个 query run 一个文件。
- `data/collections/`：从 raw response 生成的 Markdown 版本，方便人工阅读。
- `data/processed/openai_web_search_results.jsonl`：规范化后的回答、source 和 citation 摘要。
- `data/processed/citations.csv`：final citation 行。
- `data/processed/sources.csv`：API web-search 调用中暴露的 source-pool 行。
- `data/fresh_page_audit/`：规范化 URL inventory、网页/PDF 抓取 manifest、review queue 和抓取摘要。
- `reports/初步结果_2026_0602.md`：给导师汇报用的阶段性结果。
- `reports/tables/pilot_queries_for_report.xlsx`：给汇报材料使用的 20 个 query 表格。

## 方法说明

本实验的主线流程是：

```text
config/queries.csv
  -> src/collect_openai_web_search.py
  -> data/raw + data/processed
  -> src/fresh_page_audit.py
  -> data/fresh_page_audit
  -> reports/初步结果_2026_0602.md
```

需要注意的是，`data/fresh_page_audit/raw/` 和 `data/fresh_page_audit/texts/` 没有提交到 GitHub。它们是抓取到的第三方网页/PDF 原文和正文缓存，体积较大，也不适合直接公开提交。相关结构化信息保留在 `url_inventory.csv`、`fetch_manifest.csv`、`review_queue.csv` 和 `summary.json` 中。
