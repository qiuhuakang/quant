# Theme Logic Master Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use $superpower-subagents (recommended) or $superpower-executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking via update_plan.

**Goal:** Add a Theme Logic Master workflow that delegates current A-share theme/sector validation to DeepSeek web research and returns structured conclusions that can be combined with Fangtutu K-line analysis.

**Architecture:** This is an agent-orchestration feature, not a local market-data pipeline. The repository will add a project-local skill, prompt contract, lightweight decision graph, Linux loading guide, and `CLAUDE.md` routing rules. Automated tests validate local artifacts without making web calls.

**Tech Stack:** Markdown prompt contracts, Claude project-local skills, JSON decision graph, Python standard-library `unittest` and `json`.

---

## File Structure

- Create `.claude/skills/theme-logic-master/SKILL.md`: project-local skill that triggers on A-share theme, sector, hot-topic, concept, catalyst, and stock-position questions.
- Create `docs/theme_logic/prompt_contract.md`: reusable behavior contract for runtimes that do not load project-local skills.
- Create `docs/theme_logic/decision_graph.json`: lightweight reasoning rules for common A-share theme states.
- Create `docs/theme_logic/LOAD_FOR_AGENT.md`: one-sentence Linux-side loading guide.
- Modify `CLAUDE.md`: add routing rules for Theme Logic Master and the combined Fangtutu + theme decision matrix.
- Create `tests/test_theme_logic_workflow.py`: artifact-level tests for decision graph structure and prompt guardrails.

---

### Task 1: Add Failing Artifact Tests

**Files:**
- Create: `tests/test_theme_logic_workflow.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_theme_logic_workflow.py`:

```python
import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ThemeLogicWorkflowTests(unittest.TestCase):
    def test_decision_graph_has_required_rule_fields(self):
        graph_path = PROJECT_ROOT / "docs" / "theme_logic" / "decision_graph.json"
        graph = json.loads(graph_path.read_text(encoding="utf-8"))

        self.assertEqual(graph["name"], "theme_logic_master_decision_graph")
        self.assertGreaterEqual(len(graph["rules"]), 6)

        required_fields = {"id", "name", "conditions", "implication", "risk_action"}
        for rule in graph["rules"]:
            self.assertTrue(required_fields.issubset(rule), rule)
            self.assertIsInstance(rule["conditions"], list)
            self.assertTrue(rule["conditions"], rule)

    def test_skill_requires_web_research_and_evidence_fallback(self):
        skill_path = PROJECT_ROOT / ".claude" / "skills" / "theme-logic-master" / "SKILL.md"
        text = skill_path.read_text(encoding="utf-8")

        required_phrases = [
            "联网",
            "DeepSeek",
            "来源",
            "日期",
            "证据不足",
            "不要编造",
            "方土土",
        ]
        for phrase in required_phrases:
            self.assertIn(phrase, text)

    def test_prompt_contract_defines_output_sections(self):
        prompt_path = PROJECT_ROOT / "docs" / "theme_logic" / "prompt_contract.md"
        text = prompt_path.read_text(encoding="utf-8")

        for heading in [
            "题材结论",
            "所属方向",
            "个股地位",
            "当前值得关注",
            "验证依据",
            "风险",
            "与方土土合并",
        ]:
            self.assertIn(heading, text)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m unittest tests.test_theme_logic_workflow -v
```

Expected: FAIL because `docs/theme_logic/decision_graph.json`, `.claude/skills/theme-logic-master/SKILL.md`, and `docs/theme_logic/prompt_contract.md` do not exist yet.

---

### Task 2: Add Decision Graph

**Files:**
- Create: `docs/theme_logic/decision_graph.json`
- Test: `tests/test_theme_logic_workflow.py`

- [ ] **Step 1: Create the JSON decision graph**

Create `docs/theme_logic/decision_graph.json` with:

```json
{
  "name": "theme_logic_master_decision_graph",
  "version": 1,
  "description": "Lightweight reasoning rules for A-share theme heat, stock position inside a theme, and risk actions. This is not a trading signal or a full knowledge graph.",
  "rules": [
    {
      "id": "hot_theme_front_row",
      "name": "热门题材前排",
      "conditions": [
        "The theme has fresh policy, industry, news, or event catalysts.",
        "Multiple same-theme stocks show strong price response, such as limit-up clusters, sector ranking strength, or consecutive-board leadership.",
        "The target stock is among the strongest or most recognized names in the theme."
      ],
      "implication": "The stock has both theme heat and relative position. It can be placed on a priority watch list, then checked by Fangtutu K-line location before any trade plan.",
      "risk_action": "Avoid chasing after climax acceleration. Require invalidation level, position control, and follow-through confirmation."
    },
    {
      "id": "hot_theme_back_row",
      "name": "热门题材后排",
      "conditions": [
        "The theme is currently hot.",
        "Same-theme leaders or front-row stocks are clearly stronger than the target.",
        "The target reacts late, weakly, or mainly follows the sector without independent recognition."
      ],
      "implication": "Theme heat exists, but the target's position is weak. Treat it as a secondary candidate rather than the preferred expression of the theme.",
      "risk_action": "Do not upgrade the conclusion only because the concept is hot. Prefer front-row peers or wait for stronger confirmation."
    },
    {
      "id": "theme_fading",
      "name": "题材退潮",
      "conditions": [
        "Previous leaders diverge, fail to continue, or show large drawdowns.",
        "Limit-up density falls or late followers start to weaken.",
        "Market discussion shifts from expansion to risk, correction, or rotation."
      ],
      "implication": "The theme may be leaving its high-probability window. Strong K-lines in back-row stocks deserve skepticism.",
      "risk_action": "Lower expectation, avoid late chasing, and require stricter Fangtutu invalidation rules."
    },
    {
      "id": "concept_only",
      "name": "仅有概念标签",
      "conditions": [
        "The stock has a concept label in databases or media lists.",
        "There is no current catalyst, no same-theme spread, or no meaningful price response.",
        "Sources cannot prove that market funds are currently trading this stock for that theme."
      ],
      "implication": "The stock should not be treated as a current hot-theme candidate just because it has a static concept label.",
      "risk_action": "Classify as concept-only or unverified. Do not combine it with Fangtutu as a strong theme case."
    },
    {
      "id": "policy_catalyst_confirmed",
      "name": "政策或产业催化被市场确认",
      "conditions": [
        "A current policy, industry, earnings, event, or news catalyst is found from dated sources.",
        "The catalyst has visible market spread across sector peers or industry-chain nodes.",
        "The catalyst is connected to the target stock by business exposure, announcement, or recognized market narrative."
      ],
      "implication": "The theme logic is more credible because both narrative and market response are present.",
      "risk_action": "Still separate fact from inference. Watch whether front-row names continue and whether the target keeps relative strength."
    },
    {
      "id": "news_without_market_response",
      "name": "有消息但无市场响应",
      "conditions": [
        "A news item or catalyst exists.",
        "Sector peers, limit-up structure, or the target stock show weak or no response.",
        "The catalyst has not become a current market mainline or visible branch theme."
      ],
      "implication": "The narrative exists but has not been confirmed by market behavior.",
      "risk_action": "Do not call it a hot theme. Mark it as watch-only until market response appears."
    },
    {
      "id": "unknown_due_to_search_gap",
      "name": "联网证据不足",
      "conditions": [
        "Web search is unavailable, delayed, contradictory, or insufficient.",
        "Important claims cannot be cross-checked with dated sources.",
        "The target's theme membership or current heat cannot be verified."
      ],
      "implication": "The current theme conclusion is unknown rather than bullish or bearish.",
      "risk_action": "Say the evidence is insufficient, do not fabricate current hot themes, and avoid a confident trade conclusion."
    }
  ]
}
```

- [ ] **Step 2: Run tests**

Run:

```bash
python -m unittest tests.test_theme_logic_workflow -v
```

Expected: remaining failures only for missing skill and prompt contract.

---

### Task 3: Add Skill And Prompt Contract

**Files:**
- Create: `.claude/skills/theme-logic-master/SKILL.md`
- Create: `docs/theme_logic/prompt_contract.md`
- Create: `docs/theme_logic/LOAD_FOR_AGENT.md`
- Test: `tests/test_theme_logic_workflow.py`

- [ ] **Step 1: Create the skill**

Create `.claude/skills/theme-logic-master/SKILL.md` with frontmatter:

```markdown
---
name: theme-logic-master
description: Use when the user asks whether an A-share stock belongs to a current hot theme, which themes/sectors/industry chains are worth watching, whether a stock is a leader/front-row/catch-up/back-row concept stock, or how current theme logic should combine with Fangtutu K-line analysis.
---
```

The body must instruct the agent to:

- use DeepSeek or Claude Code web search before answering
- verify current date and trading date
- search current hot themes, sector movers, limit-up clusters, consecutive-board structure, target stock concepts, latest catalysts, and same-theme peers
- cross-check important claims with dated sources
- say "证据不足，暂无法验证" when search is unavailable or evidence is weak
- avoid fabricating hot themes
- output the seven required Chinese sections
- combine with Fangtutu only after theme conclusion is made

- [ ] **Step 2: Create the prompt contract**

Create `docs/theme_logic/prompt_contract.md` with the same mandatory workflow, output format, decision graph usage, and guardrails. Include a reusable prompt block that the main agent can pass to DeepSeek.

- [ ] **Step 3: Create Linux loading guide**

Create `docs/theme_logic/LOAD_FOR_AGENT.md` with the one-sentence loading instruction from the spec and a short explanation that no local API/database setup is required.

- [ ] **Step 4: Run tests**

Run:

```bash
python -m unittest tests.test_theme_logic_workflow -v
```

Expected: PASS for the new theme-logic tests.

---

### Task 4: Wire Main Agent Routing

**Files:**
- Modify: `CLAUDE.md`
- Test: `tests/test_theme_logic_workflow.py`

- [ ] **Step 1: Add Theme Logic Master section to `CLAUDE.md`**

Insert a new section after the existing Fangtutu workflow explaining:

- when Theme Logic Master should be used
- it must rely on DeepSeek/Claude Code web search for current theme validation
- it must not pretend local data can verify current theme heat
- it uses `docs/theme_logic/prompt_contract.md` and `docs/theme_logic/decision_graph.json`
- it combines with Fangtutu using the strong/weak matrix

- [ ] **Step 2: Run all relevant tests**

Run:

```bash
python -m unittest tests.test_theme_logic_workflow tests.test_fangtutu_tools -v
```

Expected: all tests pass.

- [ ] **Step 3: Check paths are portable**

Run:

```bash
rg -n "D:\\\\quant|/home/admin|C:\\\\Users" .claude docs/theme_logic CLAUDE.md tests/test_theme_logic_workflow.py
```

Expected: no matches.

---

### Task 5: Final Verification And Commit

**Files:**
- Stage and commit all feature artifacts.

- [ ] **Step 1: Inspect git status**

Run:

```bash
git status --short
```

Expected: only intended files are modified or created, plus any pre-existing untracked `AGENTS.md` remains unstaged.

- [ ] **Step 2: Commit implementation**

Run:

```bash
git add .claude/skills/theme-logic-master/SKILL.md docs/theme_logic docs/superpowers/plans/2026-06-18-theme-logic-master-implementation.md tests/test_theme_logic_workflow.py CLAUDE.md
git commit -m "feat: add theme logic master workflow"
```

Expected: commit succeeds.

- [ ] **Step 3: Push branch**

Run:

```bash
git push -u origin codex/theme-logic-master
```

Expected: branch is available on origin for the Linux machine to pull or merge.

---

## Verification

Run before final response:

```bash
python -m unittest tests.test_theme_logic_workflow tests.test_fangtutu_tools -v
rg -n "D:\\\\quant|/home/admin|C:\\\\Users" .claude docs/theme_logic CLAUDE.md tests/test_theme_logic_workflow.py
git status --short --branch
```

## Next skill

$superpower-executing-plans

