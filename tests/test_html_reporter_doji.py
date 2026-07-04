import unittest

import pandas as pd

from src.html_reporter import _build_html, _render_doji_row


THIRD_DAY_DOJI = "\u4e8c\u677f\u540e\u7b2c\u4e09\u5929\u5341\u5b57\u661f"


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2026-06-25",
                "open": 10.0,
                "close": 11.0,
                "low": 9.8,
                "high": 11.0,
                "volume": 1000,
            },
            {
                "trade_date": "2026-06-26",
                "open": 11.1,
                "close": 11.08,
                "low": 10.9,
                "high": 11.3,
                "volume": 800,
            },
        ]
    )


def _sample_result() -> dict:
    return {
        "symbol": "000001",
        "name": "\u5e73\u5b89\u94f6\u884c",
        "meets_criteria": True,
        "score": 61.8,
        "uptrend_stage": "early",
        "adj_days": 1,
        "adj_vol_ratio": 0.8,
        "buy_price": 11.2,
        "protect_price": 10.7,
        "doji_type": "third_day_doji",
        "doji_label": THIRD_DAY_DOJI,
        "doji_volume_state": "\u8fde\u7eed\u7f29\u91cf",
        "doji_note": "\u8fd9\u6bb5\u8bf4\u660e\u4e0d\u5e94\u8be5\u51fa\u73b0",
    }


def _result(symbol: str, name: str, *, meets_criteria: bool, doji_label: str = THIRD_DAY_DOJI,
            board_type: str = "two", vol_shrinking: bool = True,
            uptrend_stage: str = "early", adj_days: int = 2,
            broke_fib_618: bool = False) -> dict:
    return {
        "symbol": symbol,
        "name": name,
        "meets_criteria": meets_criteria,
        "score": 60.0,
        "uptrend_stage": uptrend_stage,
        "adj_days": adj_days,
        "adj_vol_ratio": 0.8 if vol_shrinking else 1.2,
        "vol_shrinking": vol_shrinking,
        "broke_fib_618": broke_fib_618,
        "buy_price": 11.2,
        "protect_price": 10.7,
        "doji_type": "third_day_doji" if doji_label else "none",
        "doji_label": doji_label,
        "board_type": board_type,
    }


class HtmlReporterDojiTests(unittest.TestCase):
    def test_renders_only_the_doji_tag_without_extra_words(self):
        html = _render_doji_row(_sample_result())

        self.assertEqual(
            html.strip(),
            f'<span class="doji-tag third-day">{THIRD_DAY_DOJI}</span>',
        )
        self.assertNotIn("doji-row", html)
        self.assertNotIn("\u5341\u5b57\u661f\u5206\u7c7b", html)
        self.assertNotIn("\u91cf\u80fd\u72b6\u6001", html)
        self.assertNotIn("\u8fde\u7eed\u7f29\u91cf", html)
        self.assertNotIn("doji-note", html)

    def test_places_doji_tag_at_header_right_before_expand_icon(self):
        result = _sample_result()
        html = _build_html(
            results=[result],
            dfs={"000001": _sample_df()},
            passed=[result],
            screen_date="2026-06-26",
        )

        self.assertIn(".card-header > .doji-tag { margin-left: auto; }", html)
        self.assertNotIn(".doji-row", html)

        card_start = html.index('data-symbol="000001"')
        card_body_start = html.index('<div class="card-body"', card_start)
        header_html = html[card_start:card_body_start]
        tag_html = f'<span class="doji-tag third-day">{THIRD_DAY_DOJI}</span>'

        self.assertLess(header_html.index('<div class="card-meta">'), header_html.index(tag_html))
        self.assertLess(header_html.index(tag_html), header_html.index('<span class="expand-icon">'))

    def test_returns_empty_html_without_doji_label(self):
        self.assertEqual(_render_doji_row({"doji_type": "none"}), "")

    def test_builds_standalone_doji_tab_from_passed_and_relaxed_only(self):
        two_passed = _result("000001", "\u4e8c\u677f\u5165\u9009", meets_criteria=True)
        two_relaxed = _result(
            "000002",
            "\u4e8c\u677f\u653e\u5bbd",
            meets_criteria=False,
            vol_shrinking=False,
        )
        two_excluded = _result(
            "000003",
            "\u4e8c\u677f\u672a\u8fbe\u6807",
            meets_criteria=False,
            uptrend_stage="late",
            vol_shrinking=False,
            adj_days=8,
        )
        multi_relaxed = _result(
            "000004",
            "\u4e09\u677f\u653e\u5bbd",
            meets_criteria=False,
            board_type="multi",
            vol_shrinking=False,
        )
        multi_excluded = _result(
            "000005",
            "\u4e09\u677f\u672a\u8fbe\u6807",
            meets_criteria=False,
            board_type="multi",
            uptrend_stage="late",
            vol_shrinking=False,
            adj_days=8,
        )

        html = _build_html(
            results=[two_passed, two_relaxed, two_excluded],
            dfs={r["symbol"]: _sample_df() for r in [two_passed, two_relaxed, two_excluded, multi_relaxed, multi_excluded]},
            passed=[two_passed],
            screen_date="2026-06-26",
            multi_results=[multi_relaxed, multi_excluded],
        )

        self.assertIn('class="tab-btn doji" onclick="switchTab(\'doji\')"', html)
        self.assertIn('<div id="tab-doji" class="tab-content">', html)
        self.assertIn("function buildDojiTab()", html)
        self.assertIn("{ selector: '#tab-passed > .stock-card.passed', tabId: 'tab-passed', label: '2板入选', accent: 'two-pass' }", html)
        self.assertIn("{ selector: '#tab-passed .stock-card.relaxed', tabId: 'tab-passed', label: '2板放宽', accent: 'two-relaxed' }", html)
        self.assertIn("{ selector: '#tab-multi-passed .stock-card.multi-relaxed', tabId: 'tab-multi-passed', label: '三板放宽', accent: 'three-relaxed' }", html)
        self.assertNotIn("#tab-excluded .stock-card", html)
        self.assertNotIn("#tab-multi-excluded .stock-card", html)
        self.assertNotIn("card.onclick = function() { locateStock(symbol, item.source.tabId); };", html)
        self.assertIn("header.onclick = function() { toggleCard(header); };", html)
        self.assertIn("const dojiChartId = 'chart_doji_' + symbol + '_' + item.chartId;", html)
        self.assertIn("body.className = 'card-body';", html)
        self.assertIn("chart.className = 'chart-container';", html)
        self.assertIn("card.appendChild(body);", html)
        self.assertIn("containerId.startsWith('chart_doji_')", html)

    def test_doji_tab_button_is_leftmost(self):
        result = _sample_result()
        html = _build_html(
            results=[result],
            dfs={"000001": _sample_df()},
            passed=[result],
            screen_date="2026-06-26",
        )

        tabs_start = html.index('<div class="tabs">')
        tabs_end = html.index('</div>', tabs_start)
        tabs_html = html[tabs_start:tabs_end]

        self.assertLess(
            tabs_html.index("switchTab('doji')"),
            tabs_html.index("switchTab('passed')"),
        )
        self.assertIn("'doji': { btn: 1, content: 'tab-doji' }", html)
        self.assertIn("'passed': { btn: 3, content: 'tab-passed' }", html)

    def test_builds_hold_second_tab_from_selected_and_relaxed_only(self):
        two_passed = _result("000001", "\u4e8c\u677f\u5165\u9009", meets_criteria=True)
        two_relaxed = _result(
            "000002",
            "\u4e8c\u677f\u653e\u5bbd",
            meets_criteria=False,
            vol_shrinking=False,
        )
        two_excluded = _result(
            "000003",
            "\u4e8c\u677f\u672a\u8fbe\u6807",
            meets_criteria=False,
            uptrend_stage="late",
            vol_shrinking=False,
            adj_days=8,
        )
        multi_passed = _result(
            "000004",
            "\u591a\u677f\u5165\u9009",
            meets_criteria=True,
            board_type="multi",
        )
        multi_relaxed = _result(
            "000005",
            "\u591a\u677f\u653e\u5bbd",
            meets_criteria=False,
            board_type="multi",
            vol_shrinking=False,
        )
        multi_excluded = _result(
            "000006",
            "\u591a\u677f\u672a\u8fbe\u6807",
            meets_criteria=False,
            board_type="multi",
            uptrend_stage="late",
            vol_shrinking=False,
            adj_days=8,
        )

        html = _build_html(
            results=[two_passed, two_relaxed, two_excluded],
            dfs={r["symbol"]: _sample_df() for r in [two_passed, two_relaxed, two_excluded, multi_passed, multi_relaxed, multi_excluded]},
            passed=[two_passed],
            screen_date="2026-06-26",
            multi_results=[multi_passed, multi_relaxed, multi_excluded],
        )

        self.assertIn('class="tab-btn hold" onclick="switchTab(\'hold-second\')"', html)
        self.assertIn('<div id="tab-hold-second" class="tab-content">', html)
        self.assertIn("function buildHoldSecondTab()", html)
        self.assertIn("{ selector: '#tab-passed > .stock-card.passed', label:", html)
        self.assertIn("{ selector: '#tab-passed .stock-card.relaxed', label:", html)
        self.assertIn("{ selector: '#tab-multi-passed > .stock-card.multi', label:", html)
        self.assertIn("{ selector: '#tab-multi-passed .stock-card.multi-relaxed', label:", html)
        self.assertNotIn("{ selector: '#tab-excluded .stock-card.excluded', label:", html)
        self.assertNotIn("{ selector: '#tab-multi-excluded .stock-card.multi-excluded', label:", html)
        self.assertIn("const checkIdx = boardIdx + 2;", html)
        self.assertIn("if (boardClose == null || checkClose == null || checkClose < boardClose) return;", html)
        hold_js = html[html.index("function buildHoldSecondTab()"):html.index("function buildDojiTab()")]
        self.assertNotIn("const sourceMeta = sourceCard.querySelector('.card-meta');", hold_js)
        self.assertNotIn("if (sourceMeta) meta.innerHTML = sourceMeta.innerHTML;", hold_js)
        self.assertNotIn("item.checkDate ? '<span>", hold_js)
        self.assertIn("containerId.startsWith('chart_hold_')", html)
        self.assertIn("buildHoldSecondTab();", html)
        self.assertIn("'hold-second': { btn: 2, content: 'tab-hold-second' }", html)

    def test_report_uses_readable_stock_name_and_normal_hold_styles(self):
        result = _sample_result()
        html = _build_html(
            results=[result],
            dfs={"000001": _sample_df()},
            passed=[result],
            screen_date="2026-06-26",
        )

        snippets = [
            ".stock-card .symbol, .doji-list-card .symbol, .hold-list-card .symbol { color: #1f2d3d; font-size: 15px; font-weight: 900; letter-spacing: 0; }",
            ".stock-card .name, .doji-list-card .name, .hold-list-card .name { color: #2c3e50; font-size: 14px; font-weight: 800; }",
            ".tab-btn.hold { background: #f5f6fa; color: #2c3e50; }",
            ".tab-btn.hold.active { background: #2c3e50; color: white; }",
            ".hold-tab-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 16px; background: white; border-left: 4px solid #27ae60;",
            ".hold-tab-title b { color: #27ae60; font-size: 18px; }",
            ".hold-list-card { background: white; border-left: 4px solid #27ae60; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.05); overflow: hidden; transition: box-shadow 0.2s; }",
            ".hold-list-card:hover { box-shadow: 0 2px 12px rgba(0,0,0,0.1); }",
            ".hold-list-card .card-header:hover { background: #f8f9fa; }",
            ".hold-list-card .card-left { min-width: 240px; }",
            ".hold-badge, .hold-source-badge { display: inline-flex; align-items: center; min-height: 22px; padding: 2px 8px; border-radius: 5px; font-size: 12px; line-height: 1.3; font-weight: 700; white-space: nowrap; color: #52616f; background: #edf1f5; border: 1px solid #d7dee6; }",
            ".hold-metric b { color: #2c3e50; }",
        ]
        for snippet in snippets:
            self.assertIn(snippet, html)

        old_hold_snippets = [
            ".hold-list-card .card-header { cursor: pointer; background: linear-gradient(90deg, #f1fbf8 0%, #ffffff 62%); }",
            ".hold-list-card .rank { color: #117864;",
            ".hold-list-card .score-badge {",
            ".hold-list-card .hold-badge, .hold-list-card .hold-source-badge { font-size: 12px; padding: 3px 8px; }",
            "rgba(17,120,100",
        ]
        for snippet in old_hold_snippets:
            self.assertNotIn(snippet, html)

    def test_tab_order_places_multi_passed_before_two_board_excluded(self):
        result = _sample_result()
        html = _build_html(
            results=[result],
            dfs={"000001": _sample_df()},
            passed=[result],
            screen_date="2026-06-26",
        )

        tabs_start = html.index('<div class="tabs">')
        tabs_end = html.index('</div>', tabs_start)
        tabs_html = html[tabs_start:tabs_end]
        expected_order = [
            "switchTab('doji')",
            "switchTab('hold-second')",
            "switchTab('passed')",
            "switchTab('multi-passed')",
            "switchTab('excluded')",
            "switchTab('multi-excluded')",
        ]

        positions = [tabs_html.index(item) for item in expected_order]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("'multi-passed': { btn: 4, content: 'tab-multi-passed' }", html)
        self.assertIn("'excluded': { btn: 5, content: 'tab-excluded' }", html)

    def test_report_has_mobile_layout_guards(self):
        result = _sample_result()

        html = _build_html(
            results=[result],
            dfs={"000001": _sample_df()},
            passed=[result],
            screen_date="2026-06-26",
        )

        snippets = [
            "@media (max-width: 768px)",
            ".tabs-wrapper { flex-direction: column; align-items: stretch; }",
            ".tabs { width: 100%; overflow-x: auto;",
            ".tab-btn { flex: 0 0 auto;",
            ".search-box { width: 100%; }",
            ".card-header { align-items: flex-start; flex-wrap: wrap;",
            ".card-left { min-width: 0; width: 100%; flex-wrap: wrap;",
            ".card-meta { width: 100%; flex: 0 0 100%;",
            ".card-header > .doji-tag, .doji-list-card .card-header > .doji-tag { margin-left: 0;",
            ".doji-tab-toolbar { flex-direction: column; align-items: stretch;",
            ".hold-tab-toolbar { flex-direction: column; align-items: stretch;",
            ".chart-container { height: clamp(320px, 70vh, 520px);",
            "function resizeVisibleCharts()",
            "setTimeout(resizeVisibleCharts, 60);",
            "window.addEventListener('resize', resizeVisibleCharts);",
        ]
        for snippet in snippets:
            self.assertIn(snippet, html)


if __name__ == "__main__":
    unittest.main()
