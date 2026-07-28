import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from research_trend_strength import directional_movement, regression_stats


class TrendStrengthIndicatorTests(unittest.TestCase):
    def test_dmi_favors_positive_direction_in_rising_market(self):
        closes = [100.0 + index for index in range(60)]
        highs = [value + 0.5 for value in closes]
        lows = [value - 0.5 for value in closes]
        plus_di, minus_di, adx = directional_movement(highs, lows, closes, 14)
        self.assertGreater(plus_di[-1], minus_di[-1])
        self.assertIsNotNone(adx[-1])
        self.assertGreater(adx[-1], 20)

    def test_dmi_favors_negative_direction_in_falling_market(self):
        closes = [160.0 - index for index in range(60)]
        highs = [value + 0.5 for value in closes]
        lows = [value - 0.5 for value in closes]
        plus_di, minus_di, adx = directional_movement(highs, lows, closes, 14)
        self.assertGreater(minus_di[-1], plus_di[-1])
        self.assertGreater(adx[-1], 20)

    def test_regression_detects_clean_linear_trend(self):
        values = [100.0 + index * 0.5 for index in range(30)]
        slopes, r_squared, moves = regression_stats(values, 20)
        self.assertGreater(slopes[-1], 0)
        self.assertAlmostEqual(r_squared[-1], 1.0)
        self.assertGreater(moves[-1], 0.005)

    def test_regression_waits_for_full_window(self):
        slopes, r_squared, moves = regression_stats([1.0, 2.0, 3.0], 5)
        self.assertEqual(slopes, [None, None, None])
        self.assertEqual(r_squared, [None, None, None])
        self.assertEqual(moves, [None, None, None])


if __name__ == "__main__":
    unittest.main()
