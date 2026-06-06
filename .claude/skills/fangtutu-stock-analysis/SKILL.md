---
name: fangtutu-stock-analysis
description: Use when the user asks about stocks, A-share indexes, market direction, K-line structure, screening results, buy/sell points, stop loss, position sizing, trend, consolidation, breakout, or trading risk. The answer must use Fangtutu's price-action and risk-control framework with local transcript context.
---

# Fangtutu Stock Analysis

Use this skill whenever the user asks about:

- A specific stock or index
- A-share market direction
- K-line or candlestick structure
- Existing quant screening reports or candidates
- Buy points, sell points, stop loss, protection price, position sizing, or adding positions
- Trend, consolidation, breakout, failed breakout, EMA20, double top/bottom, wedge, measure move, signal bar, or follow-through

## Required Workflow

1. Identify the target and timeframe in the user's question.
2. Gather local project data if relevant:
   - Existing screening CSV/HTML reports in `data/export/`
   - SQLite data in `db/main.db`
   - Project analysis functions when the user asks for a stock already supported by the quant system
3. Retrieve Fangtutu context internally before answering whenever the tool is available:

   ```bash
   python tools/fangtutu_context.py --question "<USER_QUESTION>" --format json
   ```

4. If `data/knowledge/fangtutu_chunks.jsonl` is missing, run:

   ```bash
   python tools/build_fangtutu_kb.py
   ```

   Then retry the context command.

5. If the retrieval tool cannot run, fall back to `docs/fangtutu/distilled_manual.md` and clearly say that raw transcript retrieval was unavailable.

## Analysis Order

Always reason in this order:

1. Market state: trend, trading range, breakout, failed breakout, pullback to EMA20, climax, or unclear.
2. Pattern evidence: signal bar, follow-through, double top/bottom, wedge/three pushes, measure move, support/resistance.
3. Quant project facts: screen score, board type/count, volume, MA/fib/protection levels, if available.
4. Conditional plan: what confirms the bullish case, what confirms the bearish case, and what invalidates the setup.
5. Risk control: stop/invalidation, small size, wide-stop position reduction, avoid urgent adding, avoid heavy-position language.

## Answer Shape

Use Chinese. Prefer this structure unless the user's question is very small:

```text
结论：
偏多 / 偏空 / 震荡 / 观察，并说明条件。

价格行为：
趋势、震荡、突破、失败突破、EMA20、形态和 follow-through。

方土土框架依据：
概括检索到的相关原则，必要时列出来源文件名。

交易计划：
走强看什么；走弱看什么；无效条件是什么。

风险控制：
止损、仓位、不要重仓、不要情绪化加仓。
```

## Guardrails

- Do not give direct all-in, guaranteed-profit, or unconditional buy/sell instructions.
- Do not pretend a transcript source was retrieved if retrieval failed.
- Do not ignore current market data. Fangtutu context is an interpretation framework, not a substitute for price data.
- Do not skip risk control when discussing a trade.
