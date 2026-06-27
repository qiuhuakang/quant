import unittest

from src.html_reporter import _render_doji_row


class HtmlReporterDojiTests(unittest.TestCase):
    def test_renders_third_day_doji_with_separate_volume_state(self):
        html = _render_doji_row(
            {
                "doji_type": "third_day_doji",
                "doji_label": "二板后第三天十字星",
                "doji_volume_state": "连续缩量",
                "doji_note": "第1/2/3天量能递减，缩量只是附加解释。",
            }
        )

        self.assertIn("二板后第三天十字星", html)
        self.assertIn("量能状态：连续缩量", html)
        self.assertNotIn("二板后第三天十字星｜连续缩量", html)

    def test_returns_empty_html_without_doji_label(self):
        self.assertEqual(_render_doji_row({"doji_type": "none"}), "")


if __name__ == "__main__":
    unittest.main()

