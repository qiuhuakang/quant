# Load Theme Logic Master For Agent

Theme Logic Master 不需要本地行情 API、向量库、数据库或知识图谱。它依赖 DeepSeek 或 Claude Code 的联网搜索能力来核验当前 A 股题材、板块热度和个股题材地位。

After pulling this repository on the Linux agent machine, tell Claude or the DeepSeek-backed agent this one sentence:

```text
请读取本仓库的 CLAUDE.md、docs/theme_logic/prompt_contract.md、docs/theme_logic/decision_graph.json，并加载 theme-logic-master skill；之后凡是股票题材、热门板块、主线方向、个股题材地位问题，都先按 Theme Logic Master 工作流让 DeepSeek 联网核验，再输出结构化结论；需要交易位置时再结合 Fangtutu Stock Analysis。
```

If the runtime does not support project-local skills, use this fallback sentence:

```text
请把 docs/theme_logic/prompt_contract.md 当成系统级行为契约执行；凡是股票题材、热门板块、主线方向、个股题材地位问题，都必须先联网核验来源和日期，证据不足时说“证据不足，暂无法验证”，不要编造当前热门题材；需要 K 线和交易位置时再结合 Fangtutu Stock Analysis。
```

Expected behavior:

- The user does not manually gather theme data.
- The agent delegates current-market research to DeepSeek or Claude Code web search.
- The answer lists source names and dates where available.
- The answer separates facts from inference.
- The answer can be combined with Fangtutu's K-line framework when trade location matters.

