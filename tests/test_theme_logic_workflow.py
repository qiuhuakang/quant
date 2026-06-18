import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ThemeLogicWorkflowTests(unittest.TestCase):
    def test_decision_graph_has_required_rule_fields(self):
        graph_path = PROJECT_ROOT / "docs" / "theme_logic" / "decision_graph.json"
        self.assertTrue(graph_path.exists(), graph_path)
        graph = json.loads(graph_path.read_text(encoding="utf-8"))

        self.assertEqual(graph["name"], "theme_logic_master_decision_graph")
        self.assertGreaterEqual(len(graph["rules"]), 6)

        required_fields = {"id", "name", "conditions", "implication", "risk_action"}
        for rule in graph["rules"]:
            self.assertTrue(required_fields.issubset(rule), rule)
            self.assertIsInstance(rule["conditions"], list)
            self.assertTrue(rule["conditions"], rule)

    def test_skill_requires_web_research_and_evidence_fallback(self):
        skill_path = (
            PROJECT_ROOT
            / ".claude"
            / "skills"
            / "theme-logic-master"
            / "SKILL.md"
        )
        self.assertTrue(skill_path.exists(), skill_path)
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
        self.assertTrue(prompt_path.exists(), prompt_path)
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


if __name__ == "__main__":
    unittest.main()
