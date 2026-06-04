# GEO Exposure 实验计划 v2

## 1. 目标

这个实验想看的不是“网页是不是一定恶意”，而是更现实的问题：真实生成式搜索回答里，会不会引用或接触到一些容易被 GEO 利用的页面；这些页面更常出现在哪类 query；它们有没有替代更好的来源；如果后续能做影响实验，再看它们是否会改变回答。

因此这里尽量不判断网页作者的主观 intent。核心对象先定义成：

> GEO-compatible source exposure: generated answers citing or surfacing pages that have structural features useful for GEO manipulation, such as commercial incentives, affiliate ranking, low originality, freshness bait, authority-style packaging, or selective framing.

也就是说，重点不是直接说“这是恶意网页”，而是看它是否具备可能影响生成式搜索引用、排序或回答 framing 的结构性特征。

## 2. Research Questions

### RQ1: Prevalence

In real generative search answers, how frequently do GEO-compatible pages appear?

Do not prove malicious intent. Instead, annotate whether cited/source-panel pages have manipulation-compatible features.

Evidence to collect:

- full answer text;
- inline citation URLs;
- visible source-panel URLs or API source URLs;
- citation/source order;
- citation span and context;
- repeated runs.

### RQ2: Query Risk

Which query types are most exposed?

High-risk categories:

- product recommendation;
- medical/health advice;
- financial advice;
- legal advice;
- business/local services;
- travel/insurance;
- software troubleshooting;
- software/tool comparison;
- controversial issues;
- long-tail niche questions.

Control categories:

- official deadline or official rate queries;
- fact lookup queries where primary sources should be obvious.

### RQ3: Platform Failure Modes

Do platforms differ in failure mode, not just total exposure?

Possible platform-specific patterns:

- one platform cites SEO aggregators more often;
- one platform cites affiliate/commercial review pages more often;
- one platform has fewer citations but more primary-source substitution;
- one platform uses more decorative citations;
- one platform overweights freshness-bait pages.

### RQ4: Source Displacement

Do cited GEO-compatible pages replace better primary or official sources?

This is the central harm definition. The study should ask:

> When official documentation, government pages, product pages, papers, medical labels, or other primary sources exist, does the system cite a secondary commercial, aggregator, or low-originality page instead?

### RQ5: Influence

Do suspect pages actually affect answers?

Use surrogate RAG ablation on selected high-risk cases:

1. Full source set.
2. Remove suspect page.
3. Replace suspect page with primary source.

Measure whether the answer changes in:

- recommendation target;
- recommendation order;
- risk disclosure;
- stance/framing;
- refusal/answering behavior;
- citation attribution.

## 3. Severity Metrics

Keep severity compact. The study should use three metrics rather than a large multi-objective benchmark.

### 3.1 Exposure

Does a suspect page become visible to the user or model?

Operational measures:

- suspect citation rate;
- suspect source-panel/source-call rate;
- citation position;
- cited suspect pages per answer;
- percentage of queries with at least one suspect page;
- repeated-run stability.

### 3.2 Source Displacement

Does a suspect page replace a better source?

Operational measures:

- primary source availability;
- displacement among central-claim citations;
- official/primary source easy-to-find flag;
- source type mismatch.

Severity:

- S0: no better source found;
- S1: better editorial source exists;
- S2: official or primary source exists;
- S3: official/primary source is easy to find but suspect source is cited.

### 3.3 Influence

Does removing or replacing the suspect page change the answer?

Operational measures:

- recommendation change;
- risk-disclosure change;
- framing/stance change;
- refusal/answering change;
- citation-attribution change;
- user-action recommendation change.

Severity:

- I0: no observable change;
- I1: citation-only change;
- I2: wording/framing change;
- I3: recommendation, risk, refusal, or user-action change.

## 4. Page Taxonomy

Annotation should focus on page type and manipulation-compatible signals, not intent.

Core source types:

- primary / official source;
- government or public institution;
- academic paper or technical report;
- high-authority editorial source;
- company/vendor source;
- low-originality aggregator;
- commercial review page;
- affiliate page;
- freshness-bait page;
- authority-spoofing page;
- instruction-like carrier;
- truthful-but-biased framing page;
- forum/social page;
- unknown or inaccessible.

Most valuable categories for this study:

- low-originality aggregator;
- commercial / affiliate page;
- freshness bait;
- authority spoofing;
- truthful-but-biased framing.

These categories avoid simply repeating indirect prompt-injection work and sit in the gap between GEO, citation quality, and RAG security.

## 5. Literature-Informed Design Choices

### From GEO/GSEO studies

Do not only judge answer correctness. Measure source visibility.

Implementation:

- record which URLs become visible;
- preserve source/citation order;
- compare visibility across repeated runs;
- record commercial/recommendation query categories.

### From C-SEO, SAGEO, and SourceBench-style benchmarks

Do not use an unstructured query list.

Implementation:

- keep query category, risk level, and risk hypothesis;
- compare high-risk categories against official-source controls;
- preserve source quality labels and answer-source mapping.

### From citation and attribution studies

A URL alone is insufficient.

Implementation:

- save citation spans and surrounding context;
- label citation role: central claim, minor claim, decorative, weak/unrelated, contradicts answer;
- distinguish cited pages from complete source-panel/API source pages.

### From RAG poisoning and defense studies

Exposure is not influence.

Implementation:

- first measure exposure and displacement;
- then select high-risk cases for surrogate RAG ablation;
- do not claim causality from citation alone.

## 6. Query Set

Pilot size: 20 queries.

Manifest:

- 20-query: `experiments/geo_exposure_pilot/config/pilot_20/queries.csv`
- 100-query: `experiments/geo_exposure_pilot/config/benchmark_100/queries.csv`

Design:

- high-risk commercial/advice/recommendation queries;
- medium-risk troubleshooting and public-health queries;
- low-risk official-source controls.

Important controls:

- Q15: official FAFSA deadline;
- Q16: IRS standard mileage rate.

If these controls cite commercial SEO pages instead of government pages, that is strong displacement evidence. If they mostly cite official sources, they validate that the protocol can distinguish low-risk from high-risk queries.

## 7. Data Collection Routes

### Route A: OpenAI API Route

Directory:

`experiments/geo_exposure_pilot/src/`

Use when API access is available.

Recommended full pilot:

```bash
cd /home/walnutpz/research-harness
export OPENAI_API_KEY="..."

.venv/bin/python experiments/geo_exposure_pilot/src/collect_openai_web_search.py \
  --query-ids Q01,Q02,Q03,Q04,Q05,Q06,Q07,Q08,Q09,Q10,Q11,Q12,Q13,Q14,Q15,Q16,Q17,Q18,Q19,Q20 \
  --model gpt-5.5 \
  --prompt-profile minimal \
  --reasoning-effort low \
  --search-context-size medium \
  --runs 3 \
  --overwrite
```

Collected outputs:

- raw API responses;
- final answer text;
- URL citation annotations;
- complete API source lists when available;
- citation spans and contexts;
- normalized JSONL;
- `citations.csv`;
- `sources.csv`;
- per-run Markdown collection files.

Prompt condition:

- Use `--prompt-profile minimal` for the main measurement so the prompt does not expose research metadata or artificially force official-source citation.
- Use `bare_query` as a sensitivity check for the closest user-query condition.
- Use `primary_aware`, `official_diagnostic`, or `research_context` only as secondary diagnostic conditions.

### Route B: Manual ChatGPT Pro UI Route

Protocol:

`experiments/geo_exposure_pilot/docs/protocols/manual_chatgpt_search_collection.md`

Use when API access is unavailable or when measuring visible UI behavior.

Collect:

- full answer text;
- all inline citation URLs;
- all visible Sources panel URLs;
- screenshots of answer and Sources panel;
- timestamp;
- model/search mode;
- browser/location/language;
- fresh-chat status;
- repeated runs.

Limitation:

This route captures user-visible source exposure but not internal candidate pools or search-call traces.

## 8. Annotation Protocol

Each unique URL should be annotated using:

- source type;
- manipulation-compatible signals;
- citation role;
- source displacement severity;
- risk label;
- influence priority;
- short rationale.

Suggested manipulation-compatible signals:

- commercial incentive;
- affiliate links;
- low originality;
- freshness bait;
- authority spoofing;
- excessive listicle/ranking structure;
- citation stuffing;
- expert tone without clear credentials;
- selective framing;
- instruction-like content;
- generated-content signals.

Consensus:

- three annotators when feasible;
- majority vote for categorical labels;
- conservative adjudication for source displacement and central-claim citation;
- preserve disagreement notes.

## 9. Analysis Plan

### For RQ1

Compute:

- suspect citation rate;
- suspect source rate;
- per-query and per-run exposure;
- top suspect domains;
- repeated-run overlap.

### For RQ2

Compare exposure by query category:

- high-risk recommendation/advice queries;
- medium-risk troubleshooting/public-health queries;
- low-risk official-source controls.

Expected pattern:

> Exposure is concentrated in commercial-intent and advice-seeking queries, not uniformly distributed.

### For RQ3

If multiple platforms are collected, compare failure modes:

- commercial/affiliate citation rate;
- aggregator citation rate;
- source displacement severity;
- decorative citation rate;
- source diversity.

Expected pattern:

> Platform difference may be about failure mode, not just total risk.

### For RQ4

Focus on central-claim citations:

- identify available primary sources;
- label displacement severity;
- count S2/S3 cases;
- analyze which query types produce the strongest displacement.

Expected pattern:

> Primary-source substitution may be a stronger and more defensible finding than "malicious page prevalence."

### For RQ5

Select S2/S3 high-risk cases for ablation.

Compare:

- full source set;
- remove suspect;
- replace suspect with primary source.

Expected pattern:

> Some suspect pages are decorative, while others shift framing, recommendation, risk disclosure, or citation attribution.

## 10. Pre-Registered Findings to Look For

The pilot should be designed around these possible findings:

1. High-risk exposure is concentrated in advice-seeking and commercial-intent queries.
2. The dominant risk is "correct answer + weak/commercial/aggregated source," not explicit prompt injection.
3. Primary-source substitution is common and measurable.
4. Platforms differ by failure mode rather than a single total-risk number.
5. Citation and influence diverge: some citations are decorative, some affect framing or recommendation.
6. High-risk pages often look high-quality: dates, headings, citations, expert tone, comparison tables, and FAQ structure.

## 11. Pilot Gate

After 20 queries and repeated runs, expand only if at least two conditions hold:

1. High-risk query categories show higher suspect exposure than controls.
2. Source displacement appears in central-claim citations.
3. Commercial/review/aggregator pages recur across runs.
4. Q15/Q16 controls mostly cite official sources.
5. At least 5-10 cases have S2/S3 displacement and are suitable for influence ablation.

Revise or stop if:

- citations are too sparse;
- source data is insufficient for annotation;
- suspect pages only appear as decorative citations;
- repeated runs are too unstable to interpret;
- high-risk and control categories do not differ.

## 12. Full Study Extension

If the pilot passes:

- expand to 100 queries;
- keep 8-10 query categories;
- keep low-risk official-source controls;
- run at least 3 repetitions per query;
- add a second platform if feasible;
- annotate all cited URLs and sampled source-panel URLs;
- run influence ablation on high-risk displaced cases.

## 13. 当前实现状态

这个计划最早是为 20-query pilot 写的。现在仓库里已经把 20-query 和 100-query 两批数据分开放在 `data/` 下面。

已经完成：

- 20-query pilot 的 query list 和 API 采集结果；
- 100-query benchmark-style query list 和 API 采集结果；
- OpenAI web search 采集脚本；
- 输出检查脚本；
- 根据 `citations.csv` 和 `sources.csv` 重建 URL inventory / review queue 的 page audit 脚本；
- 两批实验各自独立的 raw、processed、collections 和 page audit 目录。

当前数据：

1. `pilot_20/openai_20x1`：20 个 query，91 条 final citation，796 条 source-pool row。
2. `benchmark_100/openai_100x1`：100 个 query，386 条 final citation，3630 条 source-pool row。

下一步：

1. 先从 100-query 的 page audit queue 里挑优先级高的页面人工复核。
2. 按 query 类别比较 final citation 和 source pool 的暴露差异。
3. 挑出少量真正有说服力的 suspicious case，用来和导师讨论后续是否值得做影响实验。
