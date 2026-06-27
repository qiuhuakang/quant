import unittest

import pandas as pd

from src.indicator import classify_doji_pattern


def row(open_, high, low, close, volume):
    return {
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


class DojiClassificationTests(unittest.TestCase):
    def test_first_day_shrink_doji_is_special_category(self):
        adj_df = pd.DataFrame(
            [
                row(10.00, 10.60, 9.40, 10.04, 80),
                row(10.10, 10.40, 9.90, 10.30, 120),
                row(10.30, 10.70, 10.10, 10.60, 130),
            ]
        )

        result = classify_doji_pattern(adj_df, {"fib_618": 9.20}, 100)

        self.assertEqual(result["doji_type"], "first_day_shrink_doji")
        self.assertEqual(result["doji_label"], "二板后第一天缩量十字星")
        self.assertEqual(result["doji_day"], 1)
        self.assertEqual(result["doji_volume_state"], "")

    def test_third_day_doji_keeps_volume_state_separate(self):
        adj_df = pd.DataFrame(
            [
                row(10.00, 10.40, 9.90, 10.30, 300),
                row(10.30, 10.60, 10.10, 10.50, 220),
                row(10.50, 11.05, 9.95, 10.54, 120),
            ]
        )

        result = classify_doji_pattern(adj_df, {"fib_618": 9.20}, 500)

        self.assertEqual(result["doji_type"], "third_day_doji")
        self.assertEqual(result["doji_label"], "二板后第三天十字星")
        self.assertEqual(result["doji_day"], 3)
        self.assertEqual(result["doji_volume_state"], "连续缩量")
        self.assertNotIn("连续缩量", result["doji_label"])

    def test_third_day_doji_can_mark_expanding_volume(self):
        adj_df = pd.DataFrame(
            [
                row(10.00, 10.40, 9.90, 10.30, 120),
                row(10.30, 10.60, 10.10, 10.50, 130),
                row(10.50, 11.05, 9.95, 10.54, 180),
            ]
        )

        result = classify_doji_pattern(adj_df, {"fib_618": 9.20}, 500)

        self.assertEqual(result["doji_label"], "二板后第三天十字星")
        self.assertEqual(result["doji_volume_state"], "扩量")

    def test_fib_lower_shadow_doji_is_classified(self):
        adj_df = pd.DataFrame(
            [
                row(10.20, 10.50, 10.00, 10.45, 100),
                row(10.40, 10.70, 10.20, 10.60, 95),
                row(10.60, 10.90, 10.40, 10.80, 90),
                row(10.52, 10.60, 10.00, 10.54, 88),
            ]
        )

        result = classify_doji_pattern(adj_df, {"fib_618": 10.05}, 500)

        self.assertEqual(result["doji_type"], "fib_lower_shadow_doji")
        self.assertEqual(result["doji_label"], "回踩0.618附近长下影十字星")
        self.assertEqual(result["doji_day"], 4)

    def test_normal_doji_is_fallback_category(self):
        adj_df = pd.DataFrame(
            [
                row(10.00, 10.40, 9.90, 10.30, 120),
                row(10.50, 11.05, 9.95, 10.54, 130),
            ]
        )

        result = classify_doji_pattern(adj_df, {"fib_618": 9.20}, 500)

        self.assertEqual(result["doji_type"], "normal_doji")
        self.assertEqual(result["doji_label"], "普通十字星")
        self.assertEqual(result["doji_day"], 2)


if __name__ == "__main__":
    unittest.main()

