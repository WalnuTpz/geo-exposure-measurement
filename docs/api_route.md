# OpenAI API 采集路线

这里记录的是目前实际使用的 API 采集方式。核心思路很简单：把 query 发给带 web search 的 OpenAI Responses API，然后保存 raw response，再从里面拆出回答、final citation 和 source pool。

## 采集脚本会保存什么

`src/collect_openai_web_search.py` 会保存这些内容：

- 模型最终回答；
- 回答里展示给用户的 citation URL；
- `web_search_call` 里能看到的 source URL；
- 每个 query 的 raw JSON；
- 整理后的 JSONL 和 CSV；
- 方便人工阅读的 Markdown collection。

## 运行前准备

需要先设置 API key：

```bash
export OPENAI_API_KEY="..."
```

如果只想看请求格式，可以加 `--dry-run`，这样不会真正调用 API。

## 跑 20-query

```bash
cd /home/walnutpz/research-harness

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

## 跑 100-query

```bash
cd /home/walnutpz/research-harness

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

## 检查输出

20-query：

```bash
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

检查报告会写到对应 run 的 `processed/inspection_report.md`。

## Prompt profile

目前正式实验用 `minimal`。这个 profile 只要求模型正常搜索并用 citation 回答，不会把研究背景暴露给模型。

脚本里还保留了几个辅助 profile：

- `bare_query`：更接近直接把 query 丢给搜索系统；
- `primary_aware`：更偏向官方/一手来源，适合做对照；
- `official_diagnostic`：专门检查官方源是否容易被找到；
- `research_context`：早期版本，不建议作为正式实验主设置。
