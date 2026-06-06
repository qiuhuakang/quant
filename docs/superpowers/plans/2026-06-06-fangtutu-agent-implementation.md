# Fangtutu Agent Native Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use $superpower-subagents (recommended) or $superpower-executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking via update_plan.

**Goal:** Build a git-portable Fangtutu analysis layer that Claude/DeepSeek agents can load natively and use automatically for stock and market questions.

**Architecture:** Repository instructions and a Claude skill define mandatory agent behavior. Standard-library Python tools build and retrieve local Fangtutu knowledge from committed transcripts. Durable prompt docs let a Linux-side Claude load the workflow with one sentence even if project skills are unavailable.

**Tech Stack:** Python standard library (`pathlib`, `json`, `sqlite3`, `argparse`, `hashlib`, `re`, `unittest`), Claude project instructions (`CLAUDE.md`), project-local skill files, markdown docs, SQLite FTS5 with JSONL fallback.

---

### Task 1: Fangtutu Knowledge Build Tool

**Files:**
- Create: `tools/build_fangtutu_kb.py`
- Create: `tools/__init__.py`
- Test: `tests/test_fangtutu_tools.py`

- [ ] **Step 1: Write build tests**

Create `tests/test_fangtutu_tools.py` with tests that create temporary transcript folders, call `build_kb()`, and assert empty files are skipped, manifest/chunks/manual are generated, and source paths are relative.

- [ ] **Step 2: Run tests and verify they fail**

Run: `python -m unittest tests.test_fangtutu_tools -v`

Expected: import failure because `tools.build_fangtutu_kb` does not exist.

- [ ] **Step 3: Implement build tool**

Create `tools/build_fangtutu_kb.py` with:

```python
SOURCE_DIRS = (
    Path("价格心理学入门") / "价格心理学入门",
    Path("专题课") / "专题课",
)
DEFAULT_KB_DIR = Path("data") / "knowledge"
DEFAULT_MANUAL_PATH = Path("docs") / "fangtutu" / "distilled_manual.md"

def build_kb(project_root: Path | None = None, kb_dir: Path | None = None) -> dict:
    ...
```

The tool resolves the repository root, scans UTF-8 transcript files, skips zero-byte/blank files, writes `fangtutu_manifest.json`, `fangtutu_chunks.jsonl`, `fangtutu_index.sqlite`, and `docs/fangtutu/distilled_manual.md`.

- [ ] **Step 4: Run build tests**

Run: `python -m unittest tests.test_fangtutu_tools -v`

Expected: build tests pass.

### Task 2: Fangtutu Retrieval Tool

**Files:**
- Modify: `tools/build_fangtutu_kb.py`
- Create: `tools/fangtutu_context.py`
- Modify: `tests/test_fangtutu_tools.py`

- [ ] **Step 1: Write retrieval tests**

Extend the test file with checks that `get_context()` returns relevant snippets for `EMA20 回踩` and `仓位管理`, and that JSON-safe fields are present.

- [ ] **Step 2: Run tests and verify they fail**

Run: `python -m unittest tests.test_fangtutu_tools -v`

Expected: import failure because `tools.fangtutu_context` does not exist.

- [ ] **Step 3: Implement retrieval tool**

Create `tools/fangtutu_context.py` with:

```python
def get_context(question: str, project_root: Path | None = None, top_k: int = 6) -> dict:
    ...
```

The tool auto-builds missing KB files, queries SQLite FTS5 when possible, falls back to JSONL keyword scoring, returns manual summary, matched topics, snippets, and answer guidance.

- [ ] **Step 4: Run retrieval tests**

Run: `python -m unittest tests.test_fangtutu_tools -v`

Expected: all tool tests pass.

### Task 3: Agent-Native Loading Artifacts

**Files:**
- Create: `.claude/skills/fangtutu-stock-analysis/SKILL.md`
- Create: `docs/fangtutu/prompt_contract.md`
- Create: `docs/fangtutu/LOAD_FOR_AGENT.md`
- Modify: `CLAUDE.md`
- Modify: `.gitignore`

- [ ] **Step 1: Add skill**

Create a skill that triggers for stock, index, K-line, screening-result, buy/sell, stop-loss, position-sizing, and market-direction questions. It must require the agent to call `python tools/fangtutu_context.py --question "<user question>" --format json` internally before answering whenever possible.

- [ ] **Step 2: Add prompt contract and one-line load doc**

Create `docs/fangtutu/prompt_contract.md` with the mandatory workflow and answer format. Create `docs/fangtutu/LOAD_FOR_AGENT.md` with a one-line instruction a Linux-side Claude can be given:

```text
请读取本仓库的 CLAUDE.md 和 docs/fangtutu/prompt_contract.md；之后凡是股票/大盘/K线/买卖点/止损/仓位问题，都按 Fangtutu Stock Analysis 工作流先调用 tools/fangtutu_context.py 再回答。
```

- [ ] **Step 3: Update repository instructions**

Add a Fangtutu section to `CLAUDE.md` telling Claude Code to use the skill/workflow and retrieval tool automatically for market questions.

- [ ] **Step 4: Update gitignore**

Allow `.claude/skills/**` to be committed while keeping local `.claude` settings ignored. Ignore rebuildable `data/knowledge/fangtutu_index.sqlite`.

### Task 4: Verification And Commit

**Files:**
- Verify all created/modified files and transcript sources.

- [ ] **Step 1: Build real KB**

Run: `python tools/build_fangtutu_kb.py`

Expected: manifest/chunks/manual/index generated from the repository transcript folders.

- [ ] **Step 2: Query real KB**

Run: `python tools/fangtutu_context.py --question "分析一下上证指数，重点看EMA20和突破确认" --format json`

Expected: JSON output with manual summary, matched topics, snippets, and answer guidance.

- [ ] **Step 3: Run tests**

Run: `python -m unittest tests.test_fangtutu_tools -v`

Expected: all tests pass.

- [ ] **Step 4: Scan hardcoded paths**

Run: `rg -n "D:\\\\quant|/home/admin/claude/quant" tools docs .claude CLAUDE.md`

Expected: no runtime hardcoded project path results.

- [ ] **Step 5: Commit**

Stage implementation files, generated durable docs, manifest/chunks, and transcript directories. Do not stage unrelated `AGENTS.md`. Commit with:

```bash
git commit -m "feat: add fangtutu agent integration"
```

