# Load Fangtutu Workflow For Agent

After pulling this repository on the Linux agent machine, run the one-time build command from the repository root:

```bash
python tools/build_fangtutu_kb.py
```

Then tell Claude or the DeepSeek-backed agent this one sentence:

```text
请读取本仓库的 CLAUDE.md 和 docs/fangtutu/prompt_contract.md；之后凡是股票/大盘/K线/买卖点/止损/仓位问题，都按 Fangtutu Stock Analysis 工作流先调用 tools/fangtutu_context.py 再回答。
```

If the agent supports project-local skills, it can also use:

```text
请加载本仓库的 fangtutu-stock-analysis skill，并在股票/大盘问题中自动使用它。
```

Expected internal command for each market question:

```bash
python tools/fangtutu_context.py --question "<用户原问题>" --format json
```

The user should not need to run this retrieval command manually during normal chat. The agent runs it as preparation, then answers naturally in Chinese.

