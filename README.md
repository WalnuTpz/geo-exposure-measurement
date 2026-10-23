# GEO Exposure Measurement

[快速上手](#快速上手) · [运行指南](docs/api_route.md) · [数据格式](docs/data_format.md) · [研究设计](docs/experiment_plan_v2.md)

GEO Exposure Measurement 是用于研究生成式搜索来源暴露的 Python 工具集，记录网页被搜索工具返回、被回答引用的情况。

输入一组查询后，工具通过 OpenAI Responses API 采集搜索回答，将回答中的引用和搜索返回的来源保存为 CSV 与 JSONL，再抓取来源页面，生成包含页面文本、规则命中片段和引用上下文的复核队列。

项目面向 GEO（Generative Engine Optimization，生成式引擎优化）研究，关注商业推荐、面向 AI 搜索的优化内容和指令式内容在来源与引用中的分布。以产品选购为例，你可以沿着回答中的引用阅读厂商规格、评测文章和购物页面，比较这些来源承担的作用；也可以对同一查询重复采集，观察来源选择的稳定性。

## 工作流程

```text
查询 CSV → 搜索回答 → 引用表与来源表 → 页面抓取与文本提取 → 复核队列
```

- 采集回答与来源：保存 API 原始响应、可读回答、引用位置和搜索来源，按查询组织重复运行。
- 检查采集结果：查看运行状态、引用数量、来源域名分布，以及引用与来源表的对应关系。
- 阅读页面证据：抓取 HTML 和 PDF，提取与模型指令、AI 搜索优化、联盟营销等规则匹配的片段，安排复核顺序。
- 准备研究样本：从公开 benchmark 抽取十类查询，保留原始条目 ID，生成带出处的查询清单。

## 快速上手

准备 Python 3.10+、OpenAI API key 和用于搜索采集的模型 ID。采集与结果检查使用 Python 标准库；PDF 文本提取使用 `pdftotext`，安装步骤见[运行环境](docs/api_route.md#运行环境)。以下命令在仓库根目录执行。

```bash
git clone https://github.com/WalnuTpz/geo-exposure-measurement.git
cd geo-exposure-measurement
```

### 1. 写入一条查询

```bash
mkdir -p config/local
cat > config/local/queries.csv <<'CSV'
query_id,query,category,risk_level
demo_001,What should I look for in a monitor for programming?,product_recommendation,high
CSV
```

每行描述一条查询。`query_id` 用于关联回答与输出文件，`category` 和 `risk_level` 用于研究分组。你可以在同一个 CSV 中加入更多查询；完整字段说明见[查询输入](docs/data_format.md#查询输入)。

预览这条查询的请求内容：

```bash
python3 src/collect_openai_web_search.py \
  --queries config/local/queries.csv \
  --dry-run
```

终端会打印一行 JSON，其中 `run_id` 为 `demo_001_run1`，`request_payload` 包含模型设置、提示词和搜索工具配置。这是本地请求预览。

### 2. 采集搜索回答

将下面的占位值替换为自己的 API key 和模型 ID，然后运行采集器：

```bash
export OPENAI_API_KEY="YOUR_API_KEY"
export OPENAI_WEB_SEARCH_MODEL="YOUR_MODEL_ID"

python3 src/collect_openai_web_search.py \
  --queries config/local/queries.csv \
  --out-dir data/local/demo/run_01 \
  --prompt-profile minimal \
  --runs 1
```

采集器逐条调用搜索 API，将结果写入 `data/local/demo/run_01/`。先打开 `collections/demo_001_run1.md` 阅读回答及其引用，再用结构化文件进行分析：

| 文件 | 内容 |
|---|---|
| `raw/demo_001_run1.json` | API 原始响应，包括搜索调用和引用注释 |
| `processed/run_manifest.json` | 运行清单：模型、提示配置、查询列表和重复次数 |
| `processed/openai_web_search_results.jsonl` | 响应汇总：回答文本、引用和来源 |
| `processed/citations.csv` | 引用表：每次引用的 URL、标题、文本位置和上下文 |
| `processed/sources.csv` | 来源表：搜索工具返回的来源 URL、标题和类型 |

`citations.csv` 按引用事件计数：同一页面在回答中被引用两次，就有两行记录。`sources.csv` 按每次响应中的 URL 去重，记录搜索工具返回的来源。比较这两张表，可以观察来源被搜索返回和被回答引用的情况。

### 3. 查看运行报告

```bash
python3 src/inspect_outputs.py \
  --outputs data/local/demo/run_01 \
  --write-report
```

报告显示每次响应的完成状态、回答长度、引用与来源数量，以及出现频次最高的域名。报告同时保存到 `processed/inspection_report.md`。

### 4. 检查来源页面

先抓取 URL 清单中的前五个页面：

```bash
python3 src/fresh_page_audit.py \
  --data data/local/demo/run_01/processed \
  --out data/local/demo/run_01/page_audit \
  --workers 4 \
  --limit 5
```

审计器先合并引用与来源 URL，优先处理被回答引用的页面，再抓取内容、提取文本并匹配规则。省略 `--limit` 可处理完整清单。

打开 `page_audit/review_queue.csv`，按 `priority_score` 排序阅读。[复核队列](docs/data_format.md#复核队列)中，`evidence_snippets` 给出规则命中的页面片段，`citation_contexts` 给出回答中的引用上下文，`text_path` 指向提取后的页面文本。通过这些字段，可以把页面的表述与回答中的使用方式放在一起核查。每页的 HTTP 状态和提取结果保存在 `fetch_manifest.csv`。

## 组织实验

用 `--runs 3` 对每条查询重复采集三次。向 CSV 加入更多查询后，可用 `--query-ids demo_001,demo_002` 选择查询子集。每轮采集使用一个新目录，例如 `data/local/demo/run_02/`，便于比较运行结果。

提示词配置包含自然搜索回答、优先一手来源和主动寻找官方资料等条件，见 [Prompt profile](docs/api_route.md#prompt-profile)。

查询文件、运行结果和导出表格分别保存在 `config/`、`data/`、`reports/`，这些目录由 Git 忽略。

## 开发

处理脚本位于 `src/`，回归测试位于 `tests/test_pipeline.py`。运行测试：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  python3 -m unittest discover -s tests -v
```

测试使用临时合成输入和模拟网络响应，覆盖引用位置、重复引用、URL 规范化、页面提取、元数据整理、抽样和 Excel 导出。
