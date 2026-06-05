# GEO Exposure Measurement

这个仓库记录的是一个生成式搜索 source exposure 的测量实验。实验从一组用户式 query 出发，调用带 web search 的模型，保存最终引用链接和 API 返回的 source pool；随后重新抓取这些 URL，整理成后续人工复核可用的 page audit 队列。

当前重点不是直接判断网页是否“恶意”，而是先观察真实生成式搜索回答会接触到哪些来源，以及这些来源中是否存在值得进一步检查的 GEO-compatible 页面。

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
processed/    citation/source CSV 和运行设置
page_audit/   或 fresh_page_audit/，只保留 URL inventory 和 summary
```

仓库公开部分只保留 metadata。公开 CSV 中的 URL 已去掉 query string；citation/source 文件只保留 query、run、order、URL、domain、title 等结构化字段，不包含模型回答片段或网页正文。原始 API response、collection Markdown、完整模型回答、检查报告、网页/PDF 原文、网页正文缓存，以及带网页片段的 audit manifest/review queue 都保留在本地，不提交到 Git。

## 当前数据

| run | query 数 | final citation rows | source-pool rows | 规范化 URL | 本地抽取到正文 |
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

网页和 PDF 原文缓存没有提交到 Git，主要是体积大，也不适合公开放第三方原文。`fetch_manifest.csv` 和 `review_queue.csv` 里包含网页片段，也只保留在本地。公开仓库里主要保留 `citations.csv`、`sources.csv`、`url_inventory.csv` 和 `summary.json`。
