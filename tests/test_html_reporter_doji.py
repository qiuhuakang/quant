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
        self.assertIn("card.onclick = function() { locateStock(symbol, item.source.tabId); };", html)


if __name__ == "__main__":
    unittest.main()
