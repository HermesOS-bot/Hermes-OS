import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.indicators import ema, relative_volume, rsi


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


class RelativeVolumeTests(unittest.TestCase):
    def test_uses_only_previous_candles(self):
        result = relative_volume([10, 10, 10, 20], 3)
        self.assertEqual(result, [None, None, None, 2])


if __name__ == "__main__":
    unittest.main()
