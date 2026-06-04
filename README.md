# GEO Exposure Measurement

这个仓库用来保存 GEO exposure 实验的数据和脚本。目前主要有两批数据，二者分开存放：

- `pilot_20/openai_20x1`：早期 20 个 query 的 pilot；
- `benchmark_100/openai_100x1`：后来扩展的 100 个 benchmark-style query 实验。

我没有把两批数据混在一起。脚本是共用的，但 query 文件、raw response、整理后的 CSV、collection Markdown 和 page audit 结果都放在各自目录下。

## 目录

```text
geo_exposure_pilot/
├── config/
│   ├── pilot_20/
│   │   └── queries.csv
│   └── benchmark_100/
│       ├── queries.csv
│       └── sampling_manifest.json
├── src/
│   ├── collect_openai_web_search.py
│   ├── inspect_outputs.py
│   ├── fresh_page_audit.py
│   ├── sample_benchmark_queries.py
│   └── build_query_excel.py
├── data/
│   ├── pilot_20/
│   │   └── openai_20x1/
│   └── benchmark_100/
│       └── openai_100x1/
└── docs/
```

每个 run 下面基本都是这几类文件：

```text
raw/          原始 API response
processed/    整理后的 JSONL、CSV 和检查报告
collections/  方便人工阅读的 Markdown
page_audit/   或 fresh_page_audit/，网页抓取和复核队列
```

## 当前数据

| run | query 数 | final citation rows | source-pool rows | 规范化 URL | 抽取到正文 |
|---|---:|---:|---:|---:|---:|
| `pilot_20/openai_20x1` | 20 | 91 | 796 | 792 | 675 |
| `benchmark_100/openai_100x1` | 100 | 386 | 3630 | 3548 | 2956 |

这里的 `final citation` 指模型最终回答里展示给用户的引用链接；`source pool` 指 API raw response 里能看到的搜索来源。两者后续分析时要分开看。

## 检查数据

20-query：

```bash
cd /home/walnutpz/research-harness

.venv/bin/python experiments/geo_exposure_pilot/src/inspect_outputs.py \
  --outputs experiments/geo_exposure_pilot/data/pilot_20/openai_20x1 \
  --write-report
```

100-query：

```bash
.venv/bin/python experiments/geo_exposure_pilot/src/inspect_outputs.py \
  --outputs experiments/geo_exposure_pilot/data/benchmark_100/openai_100x1 \
  --write-report
```

## 重新采集

如果需要重新跑 20-query：

```bash
export OPENAI_API_KEY="..."

.venv/bin/python experiments/geo_exposure_pilot/src/collect_openai_web_search.py \
  --queries experiments/geo_exposure_pilot/config/pilot_20/queries.csv \
  --out-dir experiments/geo_exposure_pilot/data/pilot_20/openai_20x1 \
  --model gpt-5.5 \
  --prompt-profile minimal \
  --reasoning-effort low \
  --search-context-size medium \
  --runs 1 \
  --overwrite
```

如果需要重新跑 100-query：

```bash
.venv/bin/python experiments/geo_exposure_pilot/src/collect_openai_web_search.py \
  --queries experiments/geo_exposure_pilot/config/benchmark_100/queries.csv \
  --out-dir experiments/geo_exposure_pilot/data/benchmark_100/openai_100x1 \
  --model gpt-5.5 \
  --prompt-profile minimal \
  --reasoning-effort low \
  --search-context-size medium \
  --runs 1 \
  --overwrite
```

## Page Audit

20-query 默认路径已经写在脚本里：

```bash
.venv/bin/python experiments/geo_exposure_pilot/src/fresh_page_audit.py
```

100-query 需要显式指定目录：

```bash
.venv/bin/python experiments/geo_exposure_pilot/src/fresh_page_audit.py \
  --data experiments/geo_exposure_pilot/data/benchmark_100/openai_100x1/processed \
  --out experiments/geo_exposure_pilot/data/benchmark_100/openai_100x1/page_audit
```

网页和 PDF 原文缓存没有提交到 Git，主要是体积大，也不适合公开放第三方原文。后续复核主要看 `url_inventory.csv`、`fetch_manifest.csv`、`review_queue.csv` 和 `summary.json`。
