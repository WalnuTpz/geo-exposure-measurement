# 运行指南

[项目首页](../README.md) · [数据格式](data_format.md) · [研究设计](experiment_plan_v2.md)

一轮来源测量由查询准备、搜索采集、输出检查和页面审计组成。下面说明各阶段的配置方法，并给出查询抽样、Excel 导出与元数据整理的用法。完整入门示例见[快速上手](../README.md#快速上手)。

## 运行环境

所有脚本通过 Python 3.10+ 运行。采集、结果检查、元数据整理、Excel 导出和测试使用 Python 标准库。

采集器通过 HTTPS 调用 OpenAI Responses API。设置 API key 和模型 ID：

```bash
export OPENAI_API_KEY="YOUR_API_KEY"
export OPENAI_WEB_SEARCH_MODEL="YOUR_MODEL_ID"
```

页面审计通过 HTTP 获取来源内容，使用标准库解析 HTML，使用 Poppler 的 `pdftotext` 提取 PDF 文本。在 Debian、Ubuntu 或 WSL Ubuntu 中安装 PDF 工具：

```bash
sudo apt install poppler-utils
```

使用 benchmark 抽样器时，安装 `datasets`：

```bash
python3 -m pip install datasets
```

下文命令在仓库根目录执行。脚本的默认路径以仓库为基准；命令行传入的相对路径以当前工作目录为基准。

## 搜索采集

采集器读取[查询 CSV](data_format.md#查询输入)，对每条查询发送独立请求，保存回答、引用和搜索来源。用 `--runs` 设置重复次数，用 `--query-ids` 选择 CSV 中的查询：

```bash
python3 src/collect_openai_web_search.py \
  --queries config/local/queries.csv \
  --query-ids demo_001 \
  --out-dir data/local/demo/repeated_01 \
  --prompt-profile minimal \
  --runs 3
```

这条命令依次生成 `demo_001_run1`、`demo_001_run2` 和 `demo_001_run3`。多条查询按 CSV 中的顺序处理，每条查询完成全部重复后再进入下一条。

### 请求与提示词

请求发送到 `https://api.openai.com/v1/responses`，配置 `web_search` 工具、`tool_choice="required"` 和 `include=["web_search_call.action.sources"]`。每个 profile 都执行搜索；profile 决定回答指令和用户输入的组织方式。

### Prompt profile

| 配置 | 提示内容 | 适用实验条件 |
|---|---|---|
| `minimal` | 自然回答查询，并为网页支持的内容添加引用 | 默认来源暴露测量 |
| `bare_query` | 用户输入直接使用查询文本，系统指令要求自然回答 | 查询提示措辞对照 |
| `primary_aware` | 对具体事实和建议优先采用官方或一手来源，评测页面用于推荐背景 | 一手来源偏好对照 |
| `official_diagnostic` | 主动寻找官方、政府、厂商、监管、临床或文档来源 | 官方来源发现实验 |
| `research_context` | 将查询类别、风险假设和预期来源写入提示，并要求采集备注 | 包含研究背景的提示条件 |

为每个提示条件指定独立输出目录，便于按相同查询比较引用与来源。

### 预览请求

在采集命令中加入 `--dry-run`，可在本地生成请求预览：

```bash
python3 src/collect_openai_web_search.py \
  --queries config/local/queries.csv \
  --prompt-profile primary_aware \
  --runs 3 \
  --dry-run
```

每个预期响应对应一行 JSON，包含 `run_id` 和 `request_payload`。预览在文件写入与 API 调用之前结束，适合核对输入、模型设置和提示词。

### 采集参数

| 参数 | 默认值 | 含义 |
|---|---|---|
| `--queries` | `config/pilot_20/queries.csv` | 查询 CSV 路径 |
| `--query-ids` | 空 | 逗号分隔的已有查询 ID；空值选择全部查询 |
| `--out-dir` | `data/local/pilot_20/openai_20x1` | 采集根目录，见[文件布局](data_format.md#文件布局) |
| `--model` | 环境变量或 `gpt-5.5` | 请求的模型 ID |
| `--prompt-profile` | 环境变量或 `minimal` | 提示词配置 |
| `--reasoning-effort` | 环境变量或 `low` | 请求中的 `reasoning.effort` |
| `--search-context-size` | 环境变量或 `medium` | 搜索工具的 `search_context_size` |
| `--runs` | `1` | 每条查询的请求次数，正整数 |
| `--sleep` | `1.0` | 每次成功处理后等待的秒数，大于或等于零 |
| `--timeout` | `180` | HTTP 请求超时秒数，正整数 |
| `--dry-run` | 关闭 | 打印本地请求预览并结束 |
| `--overwrite` | 关闭 | 清理指定产物目录后重新采集 |

命令行参数优先于环境变量，环境变量优先于代码默认值。四个配置变量分别为：

| 参数 | 环境变量 |
|---|---|
| `--model` | `OPENAI_WEB_SEARCH_MODEL` |
| `--prompt-profile` | `OPENAI_WEB_SEARCH_PROMPT_PROFILE` |
| `--reasoning-effort` | `OPENAI_WEB_SEARCH_REASONING` |
| `--search-context-size` | `OPENAI_WEB_SEARCH_CONTEXT_SIZE` |

### 输出目录与运行状态

新一轮采集使用空目录。采集器先写入 `run_manifest.json`，记录查询列表和运行设置；每次收到响应后，先保存原始 JSON，再将 `completed` 且 `error` 为空的响应提取为汇总、CSV 和 Markdown。

请求或解析失败时，采集器停止并报告错误。已经写入的原始响应和汇总记录保存在本次目录中。运行输出检查器可对照清单查看各次响应的状态。

要替换一轮采集，使用 `--overwrite`。它会删除输出根目录下的 `raw/`、`collections/`、`processed/`、`page_audit/` 和 `fresh_page_audit/`，然后写入新结果。`--dry-run` 优先进入本地预览流程。

## 输出检查

```bash
python3 src/inspect_outputs.py \
  --outputs data/local/demo/run_01 \
  --write-report
```

`--outputs` 指向采集根目录，默认是 `data/local/pilot_20/openai_20x1`。检查器读取其中的 `processed/citations.csv` 和 `processed/sources.csv`，结合运行清单、汇总 JSONL 和原始响应生成报告。`--write-report` 将终端中的报告保存为 `processed/inspection_report.md`。

报告按运行列出响应状态、回答长度、引用与来源数量，并统计域名频次。引用检查包括 URL、引用上下文，以及同次响应中引用 URL 与来源表的对应关系。JSONL 中的汇总用于填写回答长度和对应计数，缺少汇总的条目标为 `N/A`。

检查器还包含两个固定查询的官方域名对照：`Q15` 对应 `studentaid.gov`、`ed.gov`、`usa.gov`，`Q16` 对应 `irs.gov`。该检查将域名本身及其子域名计入官方来源，并在官方引用占比达到 50% 时标为 `OK`。

## 页面审计

页面审计将采集器的引用表与来源表合并成 URL 清单，抓取每页内容，提取文本并生成复核队列：

```bash
python3 src/fresh_page_audit.py \
  --data data/local/demo/run_01/processed \
  --out data/local/demo/run_01/page_audit \
  --workers 4 \
  --timeout 18 \
  --limit 5
```

| 参数 | 默认值 | 含义 |
|---|---|---|
| `--data` | `data/local/pilot_20/openai_20x1/processed` | 保留完整 URL 与 `citation_context` 列的采集 CSV 目录 |
| `--out` | `data/local/pilot_20/openai_20x1/fresh_page_audit` | 审计输出目录 |
| `--workers` | `12` | 并发工作线程数，正整数 |
| `--timeout` | `18` | HTTP 抓取超时秒数，正整数 |
| `--limit` | `0` | URL 数量上限；零表示全部，正数选择清单前若干项 |

URL 清单按“已被引用的页面优先、查询 ID、域名、URL”排序。设置 `--limit` 后，清单、抓取记录和摘要都对应选中的页面。

HTML 提取读取 HTTP 返回的文本和 meta 内容，跳过脚本、样式、noscript 与 SVG 元素；PDF 通过 `pdftotext -layout` 转为文本。单页原始内容上限为 8,000,000 字节，文本保留前 180,000 字符，PDF 转换超时为 30 秒。

页面获取或提取错误记录在 `fetch_manifest.csv` 的 `error` 字段，其他页面继续处理。超过字节上限的响应保留截取后的原始内容，错误标记为 `truncated_at_max_bytes`。PDF 工具安装完成后即可处理 PDF 来源。

复核队列按规则分数排序，便于先阅读含有模型指令、GEO 术语或商业导流片段的页面。规则与分值见[复核队列](data_format.md#复核队列)。为每轮页面抓取选择独立输出目录，可保留各轮内容；重复使用同一目录会更新表格和同名缓存文件。本轮缓存文件由 `fetch_manifest.csv` 索引。

## 查询抽样

```bash
python3 src/sample_benchmark_queries.py
```

抽样器流式读取公开数据集的指定前缀，对查询进行文本去重、长度筛选和类别筛选，再用种子 `20260602` 打乱候选，选出十类、每类十条查询。抽样设置与筛选规则位于 `src/sample_benchmark_queries.py`。

| 查询类别 | 候选数据集 |
|---|---|
| 产品推荐 | `khanmu2003/amazon-shopping-queries-dataset` |
| 商业与法律服务 | `BeIR/msmarco` |
| 医疗健康建议 | `BeIR/nfcorpus` |
| 心理健康与治疗 | `BeIR/quora`、`BeIR/msmarco` |
| 财务税务 | `BeIR/fiqa` |
| 技术排障 | `BeIR/msmarco`、`BeIR/quora` |
| 事实与官方信息对照 | `BeIR/nq`、`BeIR/msmarco` |
| 多跳事实问答 | `BeIR/hotpotqa` |
| 辩论观点 | `BeIR/webis-touche2020` |
| 社区问答 | `BeIR/quora` |

数据读取上限分别为：购物数据 20,000 行、FiQA 6,500 行、NFCorpus 3,500 行、MS MARCO 30,000 行、NQ 3,500 行、HotpotQA 3,000 行、Touché 100 行、Quora 12,000 行。每个类别从相应候选池抽样。

抽样结果写入以下文件，每次运行更新这些路径：

| 文件 | 内容 |
|---|---|
| `config/benchmark_100/queries.csv` | 查询文本、研究分组和数据集条目 ID |
| `config/benchmark_100/sampling_manifest.json` | 随机种子、类别数量和抽样方法 |
| `data/benchmark_100/benchmark_samples/sampled_rows.jsonl` | 入选查询及其原始数据集记录 |

将生成的 `queries.csv` 传给采集器的 `--queries` 参数即可开展搜索采集；也可以继续导出 Excel，浏览查询及其出处。

## Excel 导出

```bash
python3 src/build_query_excel.py
```

导出器读取 `config/benchmark_100/queries.csv`，写入 `reports/benchmark_100/benchmark_100_queries.xlsx`。工作表包含“种类”“具体问题”“问题来源”三列，冻结首行以便浏览。

输入使用 `query_id`、`category`、`query`、`source_dataset`、`source_split` 和 `source_item_id`。来源列将数据集、split 和条目 ID 合并展示，便于核对抽样出处。重新运行会更新同名工作簿。

## 元数据整理

在[元数据副本](data_format.md#元数据副本)规定的目录中准备六张 CSV，然后运行：

```bash
python3 src/sanitize_public_metadata.py --data-root data/export_copy
```

`--data-root` 默认为仓库下的 `data/`。整理器依次重写两组引用表、来源表和 URL 清单，保留页面标识、标题、域名、运行关联和计数，移除回答片段与 URL 查询参数。整理后的表格适合分享来源分布和引用关系。

## 定位运行问题

| 现象 | 处理方法 |
|---|---|
| `Missing query columns` | 补齐 `query_id`、`query`、`category` 和 `risk_level` 四列 |
| `Unknown query IDs` | 使用输入 CSV 中已有的 `query_id` |
| `OPENAI_API_KEY is not set` | 在当前终端设置 `OPENAI_API_KEY` |
| `Output directory is not empty` | 为本轮采集指定新目录，或用 `--overwrite` 替换原有产物 |
| API 返回 HTTP 错误 | 根据响应正文检查认证、模型 ID，用 `--dry-run` 查看请求参数 |
| 响应状态为 `incomplete` 或带有 `error` | 查看 `raw/<run_id>.json` 中的状态与错误详情 |
| 页面审计要求原始 CSV | 将 `--data` 指向采集器生成的 `processed/` 目录 |
| PDF 提取失败 | 检查 `pdftotext` 安装及 `fetch_manifest.csv` 中的错误详情 |
| 复核队列的正文路径为空 | 按 `url_id` 查看抓取记录中的 HTTP 状态和提取错误 |
