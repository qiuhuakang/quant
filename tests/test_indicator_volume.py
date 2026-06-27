import unittest

import pandas as pd

from src.indicator import is_volume_shrinking


class VolumeShrinkingTests(unittest.TestCase):
    def test_first_day_after_second_board_can_pass_even_if_later_volume_expands(self):
        df = pd.DataFrame(
            {
                "volume": [100, 200, 150, 300, 400],
            }
        )
        adj_df = df.iloc[2:].copy()

        shrinking, ratio = is_volume_shrinking(df, 0, 1, adj_df)

        self.assertTrue(shrinking)
        self.assertEqual(ratio, 0.75)

    def test_first_day_after_second_board_must_be_below_second_board_volume(self):
        df = pd.DataFrame(
            {
                "volume": [100, 200, 200, 120, 100],
            }
        )
        adj_df = df.iloc[2:].copy()

        shrinking, ratio = is_volume_shrinking(df, 0, 1, adj_df)

        self.assertFalse(shrinking)
        self.assertEqual(ratio, 1.0)


if __name__ == "__main__":
    unittest.main()

