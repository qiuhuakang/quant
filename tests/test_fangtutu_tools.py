from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.build_fangtutu_kb import build_kb
from tools.fangtutu_context import get_context


class FangtutuToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.project_root = Path(self.tmp.name)

        price_dir = self.project_root / "价格心理学入门" / "价格心理学入门"
        special_dir = self.project_root / "专题课" / "专题课"
        price_dir.mkdir(parents=True)
        special_dir.mkdir(parents=True)

        (price_dir / "transcript_01.txt").write_text(
            "仓位管理是交易里最重要的事情之一。要用 I don't care size，"
            "每笔交易先定义止损，宽止损时必须减少仓位，避免重仓和着急加仓。",
            encoding="utf-8",
        )
        (special_dir / "transcript_01.txt").write_text(
            "高开低开之后要先判断趋势还是震荡。价格回踩 EMA20 附近，"
            "出现双底、信号K和 follow through 后，才更像有效突破。"
            "如果突破没有确认，就要防止失败突破。",
            encoding="utf-8",
        )
        (special_dir / "empty.txt").write_text("", encoding="utf-8")
        live_dir = self.project_root / "实战"
        live_dir.mkdir(parents=True)
        (live_dir / "live_trade.txt").write_text(
            "实战交易中出现 Bear Surprise 大阴线时，先离场保护利润。"
            "大跌大涨之后通常更像震荡行情，后面要降低预期，不要急着追单。",
            encoding="utf-8",
        )
        graph_dir = self.project_root / "docs" / "fangtutu"
        graph_dir.mkdir(parents=True)
        (graph_dir / "decision_graph.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "rules": [
                        {
                            "id": "bear_surprise_profit_protection",
                            "title": "Bear Surprise 后先保护利润",
                            "triggers": ["Bear Surprise", "大阴线", "保护利润", "实盘"],
                            "topics": ["实战复盘", "风险控制"],
                            "condition": "已有利润后突然出现 Bear Surprise 或快速大阴线。",
                            "implies": ["优先保护利润", "降低趋势延续信心", "观察是否转入震荡"],
                            "risk_actions": ["市价离场或收紧止损", "不要急着追单"],
                            "source_tags": ["实战", "风险控制"],
                        },
                        {
                            "id": "breakout_without_followthrough",
                            "title": "突破没有跟随后防失败突破",
                            "triggers": ["突破", "follow through", "没有跟随", "失败突破"],
                            "topics": ["突破确认", "趋势与震荡"],
                            "condition": "突破后没有持续 follow-through。",
                            "implies": ["可能是假突破", "可能回到震荡区间"],
                            "risk_actions": ["不要追单", "等待再次确认"],
                            "source_tags": ["专题课", "价格行为"],
                        },
                        {
                            "id": "ema20_pullback_needs_signal_bar",
                            "title": "EMA20 回踩需要信号K和背景支持",
                            "triggers": ["EMA20", "EMA", "回踩", "信号K"],
                            "topics": ["EMA20", "信号K", "趋势与震荡"],
                            "condition": "价格回踩或反弹到 EMA20 附近。",
                            "implies": ["EMA20 是决策区不是自动买卖点"],
                            "risk_actions": ["信号K差或背景不支持时不要勉强入场"],
                            "source_tags": ["专题课"],
                        },
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_build_kb_skips_empty_files_and_writes_portable_outputs(self) -> None:
        result = build_kb(project_root=self.project_root)

        self.assertEqual(result["source_file_count"], 3)
        self.assertEqual(result["chunk_count"], 3)
        self.assertTrue((self.project_root / "data" / "knowledge" / "fangtutu_manifest.json").exists())
        self.assertTrue((self.project_root / "data" / "knowledge" / "fangtutu_chunks.jsonl").exists())
        self.assertTrue((self.project_root / "docs" / "fangtutu" / "distilled_manual.md").exists())

        manifest_path = self.project_root / "data" / "knowledge" / "fangtutu_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        sources = [item["source"] for item in manifest["files"]]

        self.assertNotIn("empty.txt", "".join(sources))
        self.assertTrue(all(not Path(source).is_absolute() for source in sources))
        self.assertTrue(any("价格心理学入门" in source for source in sources))
        self.assertTrue(any("专题课" in source for source in sources))
        self.assertTrue(any("实战" in source for source in sources))

    def test_get_context_returns_ema_and_breakout_guidance(self) -> None:
        build_kb(project_root=self.project_root)

        context = get_context("EMA20 回踩后怎么判断突破确认", project_root=self.project_root, top_k=3)

        self.assertIn("manual_summary", context)
        self.assertIn("snippets", context)
        self.assertGreaterEqual(len(context["snippets"]), 1)
        joined = " ".join(snippet["summary"] + " " + snippet["quote"] for snippet in context["snippets"])
        self.assertIn("EMA20", joined)
        self.assertTrue(any(topic in context["matched_topics"] for topic in ["EMA20", "突破确认", "趋势与震荡"]))

    def test_get_context_returns_position_sizing_guidance(self) -> None:
        build_kb(project_root=self.project_root)

        context = get_context("仓位管理和宽止损应该怎么做", project_root=self.project_root, top_k=3)

        self.assertGreaterEqual(len(context["snippets"]), 1)
        joined = " ".join(snippet["summary"] + " " + snippet["quote"] for snippet in context["snippets"])
        self.assertIn("仓位", joined)
        self.assertTrue(any(topic in context["matched_topics"] for topic in ["仓位管理", "风险控制"]))
        self.assertTrue(any("止损" in item or "仓位" in item for item in context["answer_guidance"]))

    def test_get_context_returns_live_trade_guidance(self) -> None:
        build_kb(project_root=self.project_root)

        context = get_context("实盘里出现 Bear Surprise 以后怎么处理", project_root=self.project_root, top_k=3)

        self.assertGreaterEqual(len(context["snippets"]), 1)
        joined = " ".join(snippet["summary"] + " " + snippet["quote"] for snippet in context["snippets"])
        self.assertIn("Bear Surprise", joined)
        self.assertTrue(any(topic in context["matched_topics"] for topic in ["实战复盘", "风险控制", "趋势与震荡"]))

    def test_get_context_returns_decision_rule_for_bear_surprise(self) -> None:
        build_kb(project_root=self.project_root)

        context = get_context("实盘里出现 Bear Surprise 以后怎么保护利润", project_root=self.project_root, top_k=3)

        rules = context["decision_rules"]
        self.assertGreaterEqual(len(rules), 1)
        self.assertEqual(rules[0]["id"], "bear_surprise_profit_protection")
        self.assertIn("优先保护利润", rules[0]["implies"])
        self.assertIn("市价离场或收紧止损", rules[0]["risk_actions"])

    def test_get_context_returns_decision_rule_for_breakout_without_followthrough(self) -> None:
        build_kb(project_root=self.project_root)

        context = get_context("突破以后没有 follow through 应该怎么办", project_root=self.project_root, top_k=3)

        rule_ids = [rule["id"] for rule in context["decision_rules"]]
        self.assertIn("breakout_without_followthrough", rule_ids)
        self.assertEqual(context["decision_rules"][0]["id"], "breakout_without_followthrough")
        matched_rule = next(rule for rule in context["decision_rules"] if rule["id"] == "breakout_without_followthrough")
        self.assertIn("可能是假突破", matched_rule["implies"])
        self.assertIn("不要追单", matched_rule["risk_actions"])


if __name__ == "__main__":
    unittest.main()
