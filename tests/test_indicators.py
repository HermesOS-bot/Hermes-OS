import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.indicators import directional_movement, ema, relative_volume, rsi


class EmaTests(unittest.TestCase):
    def test_seeds_with_simple_average(self):
        values = [1, 2, 3, 4]
        result = ema(values, 3)
        self.assertEqual(result[:2], [None, None])
        self.assertEqual(result[2], 2)
        self.assertEqual(result[3], 3)


class RsiTests(unittest.TestCase):
    def test_constant_market_is_neutral(self):
        result = rsi([100] * 20, 14)
        self.assertEqual(result[14], 50)

    def test_rising_market_reaches_one_hundred(self):
        result = rsi(list(range(20)), 14)
        self.assertEqual(result[14], 100)

    def test_falling_market_reaches_zero(self):
        result = rsi(list(range(20, 0, -1)), 14)
        self.assertEqual(result[14], 0)


class DirectionalMovementTests(unittest.TestCase):
    def test_rising_market_has_positive_direction_and_strong_adx(self):
        closes = [100 + index for index in range(60)]
        highs = [value + 0.5 for value in closes]
        lows = [value - 0.5 for value in closes]
        plus_di, minus_di, adx = directional_movement(highs, lows, closes, 14)
        self.assertGreater(plus_di[-1], minus_di[-1])
        self.assertGreater(adx[-1], 25)

    def test_rejects_mismatched_series(self):
        with self.assertRaises(ValueError):
            directional_movement([1, 2], [1], [1, 2], 14)


class RelativeVolumeTests(unittest.TestCase):
    def test_uses_only_previous_candles(self):
        result = relative_volume([10, 10, 10, 20], 3)
        self.assertEqual(result, [None, None, None, 2])


if __name__ == "__main__":
    unittest.main()
