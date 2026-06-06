# Fangtutu-Native Stock Analysis Agent Design

Date: 2026-06-06
Project: `quant` repository

## Summary

The goal is to make the existing stock-analysis agent answer stock, index, market, K-line, buy/sell, and risk-management questions through Fangtutu's trading framework by default. The user should not have to manually query a separate knowledge base. Fangtutu knowledge must become part of the agent's native behavior through a combination of repository instructions, a reusable skill, and an internal retrieval context tool.

The design uses a hybrid approach:

1. A distilled Fangtutu trading manual gives the agent stable long-term judgment rules.
2. A local searchable transcript index gives the agent traceable source support.
3. Agent-facing instructions require the workflow whenever the user asks market-analysis questions.
4. All paths and generated state are portable from Windows to Linux through the git repository.

## Goals

- Make Fangtutu's price-action framework an automatic part of the agent's stock and market answers.
- Keep the integration usable on a separate Linux machine after pulling this git project.
- Preserve traceability: important judgments should be grounded in the distilled manual or retrieved transcript snippets.
- Keep the user experience natural: the user asks ordinary questions, and the agent handles retrieval and framing internally.
- Support the existing quant project context: screening results, K-line data, reports, SQLite data, and current analysis functions should remain available as factual inputs.

## Non-Goals

- Do not train or fine-tune a model.
- Do not require a hosted vector database.
- Do not require the user to manually run a retrieval command for each question.
- Do not turn Fangtutu's content into mechanical trading signals without market-data validation.
- Do not provide definitive investment advice or position-sizing instructions for the user's real account.

## Source Material

The source transcripts are repository-local and should be transferred through git:

- `价格心理学入门/价格心理学入门/*.txt`
- `专题课/专题课/*.txt`

Observed characteristics:

- Around 1.08 MB of transcript text.
- Some files may be empty and should be excluded from indexing.
- Content is UTF-8 readable when decoded explicitly.
- The content contains recurring trading concepts: EMA20, trend versus trading range, double top/bottom, wedge, signal bar, follow-through, measure move, risk control, small size, stop loss, wide stop, adding positions, and probability/expectancy.

## Chosen Approach

Use a native-agent hybrid design:

- `CLAUDE.md` and/or the agent system prompt define when Fangtutu analysis must be used.
- A repository skill defines the exact analysis procedure and answer shape.
- A local retrieval tool is available for the agent to call before answering. It is not a user-facing step.
- A build tool creates the manual, manifest, chunks, and local index from transcript files.

This wins over prompt-only integration because the transcript corpus is too large and detailed to keep entirely in a prompt. It wins over retrieval-only integration because the agent needs stable interpretive habits, not just snippets.

## Architecture

```text
User asks stock / market question
        |
        v
Agent instruction layer
CLAUDE.md / system prompt detects Fangtutu-triggering question
        |
        v
Fangtutu skill workflow
Defines analysis order and required output sections
        |
        v
Internal context gathering
1. Current quant project data, if relevant
2. Fangtutu distilled manual
3. Retrieved transcript snippets
        |
        v
Agent answer
Conclusion + price-action read + Fangtutu basis + plan + risk control
```

## Proposed Repository Structure

```text
.claude/
  skills/
    fangtutu-stock-analysis/
      SKILL.md

docs/
  fangtutu/
    distilled_manual.md
    prompt_contract.md

tools/
  build_fangtutu_kb.py
  fangtutu_context.py

data/
  knowledge/
    fangtutu_manifest.json
    fangtutu_chunks.jsonl
    fangtutu_index.sqlite        # generated cache, ignored or rebuildable

价格心理学入门/
  价格心理学入门/
    transcript_*.txt

专题课/
  专题课/
    transcript_*.txt
```

Generated cache files should be rebuildable on Linux. The raw transcripts and durable distilled docs should be committed. The SQLite index may be ignored if repeatable generation is reliable.

## Agent Integration

### CLAUDE.md / System Prompt Contract

The root repository instructions should include a section similar to:

```text
When the user asks about stocks, A-share indexes, market direction, K-line structure,
screening results, buy/sell points, stop loss, trend, consolidation, breakout,
or trading risk, you must use the Fangtutu stock-analysis workflow.

Before answering:
1. Gather relevant project data when available.
2. Load Fangtutu context by using the local Fangtutu context tool or the skill's
   documented fallback.
3. Answer using: conclusion, price-action read, Fangtutu basis, trading plan,
   invalidation/risk control.

Do not present Fangtutu context as a separate user action. Treat it as internal
agent preparation.
```

If the Linux agent does not honor `CLAUDE.md`, the same contract should be copied into the agent's explicit system prompt.

### Skill Contract

Add a skill under `.claude/skills/fangtutu-stock-analysis/SKILL.md`. The skill is triggered when the user asks about:

- Individual stocks
- A-share indexes or broad market direction
- K-line patterns
- Buy points, sell points, stop loss, position sizing, or risk control
- Existing quant screening reports and candidates

The skill should require this workflow:

1. Determine the user's target: stock, index, market, strategy, or report.
2. Gather current project data when available.
3. Retrieve Fangtutu context internally.
4. Classify the market structure:
   - trend
   - trading range
   - breakout
   - failed breakout
   - pullback to EMA20
   - double top/bottom
   - wedge
   - measure move area
5. Convert the structure into a conditional plan:
   - what would confirm the bullish case
   - what would confirm the bearish case
   - what invalidates the setup
   - where risk should be controlled
6. Mention uncertainty and avoid heavy-position language.

### Internal Retrieval Tool

`tools/fangtutu_context.py` is an agent-facing command, not a user workflow.

Example internal call:

```bash
python tools/fangtutu_context.py --question "分析一下上证指数"
```

Expected output can be JSON or markdown. JSON is preferred for stable parsing:

```json
{
  "manual_summary": "...",
  "matched_topics": ["趋势与震荡", "EMA20", "突破确认"],
  "snippets": [
    {
      "source": "专题课/专题课/transcript_01_20260606_144708.txt",
      "chunk_id": "fangtutu-00012",
      "summary": "...",
      "quote": "short compliant excerpt",
      "relevance": 0.84
    }
  ],
  "answer_guidance": [
    "先判断趋势还是震荡",
    "突破需要看 follow-through",
    "止损和仓位先于入场"
  ]
}
```

The agent should use the returned context silently, then write a natural answer.

## Knowledge Build Pipeline

`tools/build_fangtutu_kb.py` should:

1. Resolve the project root without Windows-only paths.
2. Scan the two transcript source directories.
3. Skip empty files.
4. Normalize UTF-8 text and whitespace.
5. Create a manifest with file path, byte length, content hash, and detected topic hints.
6. Split transcripts into chunks sized for retrieval.
7. Generate or update a distilled manual.
8. Build a local searchable index.

The initial implementation should use SQLite FTS5 when available and fall back to JSONL keyword scoring if FTS5 is unavailable. This avoids requiring embeddings or external services on the Linux machine.

## Distilled Manual Shape

`docs/fangtutu/distilled_manual.md` should be concise enough to fit into prompts and stable enough to guide answers:

- Core philosophy
  - Market movement is probabilistic.
  - Do not over-explain single failures as manipulation.
  - Survival and risk control come before making money.
- Market-state checklist
  - trend, trading range, breakout, failed breakout, pullback, climax
- Pattern vocabulary
  - EMA20, signal bar, follow-through, double top/bottom, wedge, measure move
- Decision sequence
  - context first, pattern second, confirmation third, risk fourth
- Risk rules
  - I don't care size
  - small position for wide stop
  - define invalidation before entry
  - avoid urgent adding
- Answer style
  - conditional, structured, not overconfident

## Answer Format

For stock or market questions, the agent should normally answer in this structure:

```text
结论：
偏多 / 偏空 / 震荡 / 观察，并说明条件。

价格行为：
趋势、震荡、突破、失败突破、EMA20、形态和 follow-through。

方土土框架依据：
概括相关方法论，必要时给短引用或来源文件。

交易计划：
如果走强看什么；如果走弱看什么；无效条件是什么。

风险控制：
止损、仓位、不要重仓、不要把单次失败情绪化。
```

The answer may be shorter for simple questions, but it should not skip risk control when discussing trades.

## Interaction With Existing Quant System

The Fangtutu layer should not replace the existing `二板涨停 N 型战法` screener. It should sit above it as an interpretation layer.

When the user asks about a screened stock:

1. Use existing stored analysis and scores as factual inputs.
2. Use Fangtutu context to interpret price behavior and risk.
3. Clearly separate:
   - mechanical screener result
   - price-action interpretation
   - conditional trading plan

When the user asks about the broad market:

1. Use available index/K-line data if the project has it.
2. If data is missing, say what cannot be verified from local data.
3. Still answer with the Fangtutu framework, but mark data assumptions clearly.

## Linux Portability

The Linux agent machine should be able to use this after pulling the git repository.

Required properties:

- No code depends on a machine-specific absolute project path.
- All source paths are relative to the repository root.
- Tools use `pathlib.Path`.
- Text is read as UTF-8.
- Generated files are reproducible.
- The build command works on both Windows and Linux:

```bash
python tools/build_fangtutu_kb.py
```

Optional environment variables:

```text
QUANT_PROJECT_ROOT        # override project root if needed
FANGTUTU_KB_DIR           # override generated knowledge dir
```

## Git Strategy

Commit:

- Raw transcript files, unless the user chooses to keep them private outside git.
- `CLAUDE.md` updates.
- Skill files.
- Build and retrieval tools.
- Durable docs such as `distilled_manual.md` and `prompt_contract.md`.
- Manifest/chunks if useful for review.

Do not commit by default:

- Rebuildable SQLite search index.
- Runtime logs.
- Local machine settings.

`.gitignore` should include generated cache patterns if the index is not committed.

## Error Handling

- If transcripts are missing, the agent should still answer using the distilled manual and say the raw knowledge index is unavailable.
- If the index is missing, the retrieval tool should either rebuild or fall back to direct JSONL/file search.
- If no snippets match, the agent should use the general manual and avoid pretending it has a specific Fangtutu source.
- If project market data is missing or stale, the agent should label that explicitly.
- If the user asks for direct investment advice, the agent should convert the response into conditional analysis and risk planning.

## Testing And Acceptance Criteria

Build tests:

- Running `python tools/build_fangtutu_kb.py` on Windows succeeds.
- Running the same command on Linux succeeds after git pull.
- Empty transcript files are skipped.
- Manifest includes all non-empty source transcript files.

Retrieval tests:

- Query `EMA20 回踩` returns EMA/pullback-related snippets.
- Query `仓位管理` returns risk and position-sizing snippets.
- Query `突破确认 follow through` returns breakout confirmation snippets.
- Retrieval still works if SQLite FTS5 is unavailable.

Agent behavior tests:

- Asking `分析一下上证指数` triggers Fangtutu workflow without user manually invoking a tool.
- Asking `分析一下 000839` combines quant data, if available, with Fangtutu price-action framing.
- Asking `这个票可以买么` produces conditional analysis, invalidation, and risk control rather than a direct all-in recommendation.
- Asking a non-market question does not force Fangtutu analysis.

Portability tests:

- No committed runtime code contains hardcoded Windows or Linux absolute project paths.
- Fresh Linux checkout can rebuild the knowledge index.
- The agent can answer after index rebuild using only repository files and installed Python dependencies.

## Open Risks

- Different Claude Code or DeepSeek wrapper environments may handle skills differently. The design mitigates this by duplicating the critical behavior in `CLAUDE.md` and system prompt text.
- The transcript content may contain recognition errors. The build pipeline should preserve source traceability so bad chunks can be identified and fixed.
- Prompt-only enforcement can be bypassed by model behavior. The skill and system prompt should make context gathering mandatory for market questions.
- Current project data may not include all market/index data required for broad-market analysis. The agent should clearly separate verified local data from framework-based interpretation.

## Approval Gate

After this design is reviewed and approved, the next step is to create an implementation plan using `$superpower-writing-plans`. Implementation should not begin until that plan is approved.
