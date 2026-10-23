# 数据格式

[项目首页](../README.md) · [运行指南](api_route.md) · [研究设计](experiment_plan_v2.md)

采集结果围绕查询、响应、引用事件和页面组织。查询 ID 连接输入与回答，运行 ID 区分重复采集，页面 ID 连接抓取内容与复核记录。

| 对象 | 标识 | 对应文件 |
|---|---|---|
| 查询 | `query_id` | 输入 CSV、汇总 JSONL、引用表与来源表 |
| 一次响应 | `run_id`，格式为 `<query_id>_run<N>` | 原始响应、回答 Markdown、汇总 JSONL |
| 一次引用 | `run_id` + `citation_order` | `citations.csv` |
| 一条来源记录 | `run_id` + `source_order` | `sources.csv` |
| 页面 | `url_id` | URL 清单、抓取记录、复核队列 |

所有 CSV 使用 UTF-8 编码并包含表头。文本字段中的逗号和换行采用 CSV 引号转义，读取与计数使用 CSV 解析器。

## 查询输入

采集器通过 `--queries` 读取本地 CSV。基础输入包含四列：

| 字段 | 格式与用途 |
|---|---|
| `query_id` | 文件内唯一，匹配 `[A-Za-z0-9_-]+`；用于运行 ID 和文件名 |
| `query` | 查询文本，至少包含一个非空白字符 |
| `category` | 研究者定义的查询类别，例如 `product_recommendation` |
| `risk_level` | 研究者定义的风险分组，例如 `high`、`medium`、`low` |

例如：

```csv
query_id,query,category,risk_level
demo_001,What should I look for in a monitor for programming?,product_recommendation,high
```

采集摘要保留 `category` 和 `risk_level`，用于按研究分组汇总结果。`research_context` 提示配置还将以下三列写入用户输入：

| 字段 | 内容 |
|---|---|
| `risk_hypothesis` | 该查询的研究假设 |
| `expected_primary_sources` | 预期相关的一手来源 |
| `expected_failure_modes` | 准备考察的来源选择或回答问题 |

benchmark 抽样器输出完整的十二列查询表：基础四列、上述三列，以及 `source_type`、`source_dataset`、`source_split`、`source_item_id`、`control_type`。其中 `source_type` 为 `benchmark_original_query`，`control_type` 为 `exposure` 或 `control`。来源字段用于追溯数据集中的原始条目。

## 文件布局

以采集目录 `data/local/demo/run_01/` 为例：

```text
run_01/
├── raw/
│   └── demo_001_run1.json
├── collections/
│   └── demo_001_run1.md
├── processed/
│   ├── run_manifest.json
│   ├── openai_web_search_results.jsonl
│   ├── citations.csv
│   ├── sources.csv
│   └── inspection_report.md
└── page_audit/
    ├── url_inventory.csv
    ├── fetch_manifest.csv
    ├── review_queue.csv
    ├── summary.json
    ├── raw/
    └── texts/
```

采集器生成 `raw/`、`collections/` 和 `processed/` 中的采集文件；检查器通过 `--write-report` 生成报告；页面审计器通过 `--out` 指定审计目录。

`run_01` 是一轮采集的目录名，`demo_001_run1` 是该轮中一次查询响应的标识。合并多轮采集时，将实验目录名或自定义实验 ID 与 `run_id` 组合使用。

## 采集文件

### 原始响应与运行清单

`raw/<run_id>.json` 保存 API 原始响应，包括响应状态、输出项、搜索调用、引用注释和用量。采集器收到 JSON 后立即保存这个文件，随后检查完成状态并提取内容。

`processed/run_manifest.json` 在发送请求前写入，记录本轮的运行配置：

| 字段 | 内容 |
|---|---|
| `collected_at` | 本轮采集开始时间，UTC ISO 8601 格式 |
| `model`、`prompt_profile` | 模型 ID 与提示词配置 |
| `reasoning_effort`、`search_context_size` | 推理和搜索上下文设置 |
| `query_ids`、`runs_per_query` | 查询 ID 列表与每条查询的重复次数 |
| `api_url`、`include`、`tool_choice` | API 地址与搜索来源返回设置 |
| `dry_run` | 写入采集文件时为 `false` |

用 `query_ids × runs_per_query` 展开预期运行列表，再与实际响应和汇总逐项对应。输出检查器按这一方式列出运行状态。

### 汇总与可读回答

`processed/openai_web_search_results.jsonl` 每行保存一次完成状态检查和内容提取后的响应：

| 字段组 | 字段 |
|---|---|
| 查询与运行 | `query_id`、`run_id`、`run_index`、`query`、`category`、`risk_level` |
| 请求与响应 | `model`、`response_id`、`collected_at`、`raw_path` |
| 回答与来源 | `output_text`、`citations`、`sources`、`web_search_calls` |
| API 附加信息 | `usage`、`error` |

`output_text` 按响应顺序用换行连接各文本块，并保留块内空白。`model` 保存请求的模型 ID，`collected_at` 保存该次请求开始前的 UTC 时间。原始响应中的模型信息保存在 `raw/<run_id>.json`。

`collections/<run_id>.md` 将查询信息、回答、引用表、来源表和搜索调用排成可读文档，适合逐条检查回答。

### 引用表

`processed/citations.csv` 一行对应回答中的一次 URL 引用：

| 字段 | 含义 |
|---|---|
| `query_id`、`run_id` | 查询与响应标识 |
| `citation_order` | 本次响应内的引用提取顺序，从 1 开始 |
| `url`、`title` | API 引用注释中的 URL 和标题 |
| `start_index`、`end_index` | 引用在拼接后回答中的字符范围，采用 Python 切片的半开区间 |
| `cited_text_span` | 注释位置对应的文本 |
| `citation_context` | 引用片段及其前后各最多 180 个字符，换行转为空格 |

同一页面在回答中出现三次引用，就保留三条事件。API 注释提供整数位置时，可用 `output_text[start_index:end_index]` 定位对应文本。上下文从该注释所属的原始文本块提取；位置字段缺失时保留空值。

### 来源表

`processed/sources.csv` 记录 API 响应中各个 `web_search_call.action.sources` 的来源：

| 字段 | 含义 |
|---|---|
| `query_id`、`run_id` | 查询与响应标识 |
| `source_order` | 合并来源列表后首次出现的顺序，从 1 开始 |
| `url`、`title`、`source_type` | API 返回的来源地址、标题和类型 |

同次响应中，带 URL 的记录按原始 URL 字符串去重，保留首次出现项；空 URL 的来源记录逐条保留。按 `run_id` 与 URL 连接引用表和来源表，可以查看搜索返回的页面在回答中的引用情况。

## 页面审计文件

### URL 清单

`url_inventory.csv` 汇总引用表和来源表中的页面，并保留它们与查询、引用事件的关联：

| 字段 | 含义 |
|---|---|
| `url_id` | 页面标识；取规范化 URL 的 SHA-256 前 16 个十六进制字符，输入已有 ID 时沿用 |
| `url` | 用于抓取的规范化 URL |
| `domain` | URL 的 `netloc` 部分转为小写并去掉 `www.` 前缀，用于域名统计 |
| `query_ids` | 关联查询 ID，去重、排序后以分号连接 |
| `in_final_citation` | 至少被引用一次时为 `True`，其余为 `False` |
| `citation_orders` | `run_id#citation_order` 列表，以分号连接 |
| `source_count` | 汇总到该页面的来源表记录数 |
| `citation_count` | 汇总到该页面的引用事件数 |
| `titles` | 去重、排序并以 ` \| ` 连接的标题，保留前 500 个字符 |
| `citation_contexts` | 前三个引用上下文，以换行和 `---` 分隔 |

URL 规范化将协议和主机部分转为小写，为空路径补上 `/`，移除 fragment 和 `utm_` 参数，保留其他查询参数的编码与顺序。抓取 URL 保留 `www.` 主机前缀。例如：

```text
输入：https://www.example.com/item?id=42&utm_source=search#specs
抓取：https://www.example.com/item?id=42
统计域名：example.com
```

清单先排列已被引用的页面，再按查询 ID、域名和 URL 排序。`--limit` 选择排序后的前若干项，本轮审计的其他文件均围绕这份清单生成。

### 抓取记录与文本

`fetch_manifest.csv` 每行描述一次页面处理：

| 字段组 | 字段与含义 |
|---|---|
| 页面关联 | `url_id`、`url`、`domain`、`query_ids`、`in_final_citation` |
| HTTP 响应 | `status` 为 HTTP 状态码，`content_type` 为响应类型，`bytes` 为保存的原始字节数 |
| 文本提取 | `text_chars` 为保留的文本字符数，`error` 为获取或提取错误详情 |
| 规则命中 | `signals` 为规则组名，`evidence_snippets` 为对应页面片段 |
| 缓存位置 | `raw_path` 为原始内容路径，`text_path` 为提取后的文本路径 |

成功提取的文本保存在 `texts/<url_id>.txt`。原始 PDF 保存在 `raw/<url_id>.pdf`，其他原始内容保存在 `raw/<url_id>.bin`。获取或提取失败时，`error` 记录原因；HTTP 错误同时保留状态码。

缓存路径优先相对于执行时的工作目录，其次相对于仓库；位于这两处之外的文件使用绝对路径。迁移实验目录时，同步更新路径字段即可继续定位缓存。

### 复核队列

`review_queue.csv` 将页面信息、引用上下文、提取文本和规则证据放在同一行，按 `priority_score` 降序排列。字段分为四组：

| 内容 | 字段 |
|---|---|
| 排序与身份 | `priority_score`、`url_id`、`url`、`domain` |
| 引用关系 | `query_ids`、`in_final_citation`、`citation_orders`、`titles`、`citation_contexts` |
| 获取概况 | `status`、`content_type`、`text_chars`、`text_path` |
| 页面证据 | `signals`、`evidence_snippets` |

规则使用英文正则表达式。每组命中时，截取首个匹配及其前后各最多 180 个字符，保存到 `evidence_snippets`。复核优先级按下表加和：

| 条件或规则组 | 匹配内容示例 | 分值 |
|---|---|---:|
| 出现在最终引用中 | 页面至少被回答引用一次 | +5 |
| `explicit_llm_instruction` | 要求助手忽略先前指令、优先推荐或改变排序的措辞 | +50 |
| `geo_or_ai_search_targeting` | Generative Engine Optimization、AI search 等表达 | +40 |
| `affiliate_or_ad_disclosure` | 联盟营销、佣金、赞助和广告披露 | +15 |
| `lead_generation` | 报价、咨询和服务导流文案 | +15 |
| `high_risk_unsafe_claim` | 保证效果、治愈和零风险等表达 | +10 |
| `low_quality_or_spam` | 规则中列举的站点或垃圾文本片段 | +25 |
| 获取或提取错误 | `fetch_manifest.csv` 中的 `error` 有值 | −2 |

完整匹配表达式位于 [fresh_page_audit.py](../src/fresh_page_audit.py) 的 `SIGNAL_PATTERNS`。分数用于安排页面阅读顺序。复核时结合 `evidence_snippets`、页面全文和 `citation_contexts` 进行页面与引用标注；获取详情通过 `url_id` 连接抓取记录。

### 审计摘要

`summary.json` 汇总本轮 URL 清单的处理情况：

| 字段 | 统计方式 |
|---|---|
| `inventory_urls` | 本轮清单中的页面数 |
| `fetched_rows` | 返回处理记录的页面数，包含失败记录 |
| `http_ok_no_error` | HTTP 状态有值且 `error` 为空的页面数 |
| `with_text` | `text_chars` 大于零且 `error` 为空的页面数 |
| `with_signals` | 至少命中一组规则的页面数 |
| `elapsed_seconds` | 抓取与处理阶段的耗时秒数 |

## 计数与表间关联

引用事件、来源记录和页面各有对应的统计单位。以同一页面在两次响应中分别被引用三次、一次，并在两次来源表中各出现一次为例：

| 统计项 | 计数 |
|---|---:|
| 引用事件 | 4 |
| 包含该页面的响应 | 2 |
| 来源表记录 | 2 |
| URL 清单中的页面 | 1 |

该页面的 `citation_count` 为 4，`source_count` 为 2。分析回答中的引用频次时使用引用事件；分析页面覆盖时按 `url_id` 去重；分析查询覆盖时按 `query_id` 聚合。

关联人工标签时，以 `url_id` 连接页面清单和页面标签，再通过 `citation_orders` 中的运行 ID 与引用序号回到具体回答。跨轮分析同时保留实验 ID。研究指标的计算方法见[暴露分析](experiment_plan_v2.md#暴露分析)。

## 元数据副本

元数据整理器保留来源分布与引用关系，移除回答片段和 URL 查询参数。先将六张 CSV 复制到独立导出目录，按以下结构放置；两组目录名是整理器的读取约定：

```text
export_copy/
├── pilot_20/openai_20x1/
│   ├── processed/citations.csv
│   ├── processed/sources.csv
│   └── fresh_page_audit/url_inventory.csv
└── benchmark_100/openai_100x1/
    ├── processed/citations.csv
    ├── processed/sources.csv
    └── page_audit/url_inventory.csv
```

运行整理器，依次重写这六张副本表：

```bash
python3 src/sanitize_public_metadata.py --data-root data/export_copy
```

整理后的字段为：

| 表 | 字段 |
|---|---|
| 引用表 | `query_id`、`run_id`、`citation_order`、`url_id`、`url`、`domain`、`title` |
| 来源表 | `query_id`、`run_id`、`source_order`、`url_id`、`url`、`domain`、`title`、`source_type` |
| URL 清单 | `url_id`、`url`、`domain`、`query_ids`、`in_final_citation`、`citation_orders`、`titles`、`source_count`、`citation_count` |

展示 URL 去掉查询参数、fragment 和 `www.` 前缀，`url_id` 沿用整理前的页面身份。例如 `/item?id=1` 和 `/item?id=2` 的展示路径都变为 `/item`，两页各自保留原有 ID 和计数。元数据表通过 `url_id` 关联，页面抓取使用采集目录中的原始 URL 表。
