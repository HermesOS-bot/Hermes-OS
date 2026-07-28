import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from research_trend_pullbacks import pullback_reclaim_side
from core.models import Candle


class PullbackReclaimTests(unittest.TestCase):
    def candles(self):
        return [
            Candle(datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc), 100, 101, 98, 99, 10),
            Candle(datetime(2026, 7, 27, 10, 5, tzinfo=timezone.utc), 99, 101, 98.5, 100.5, 20),
        ]

    def test_long_requires_cross_back_above_vwap(self):
        side = pullback_reclaim_side(
            1,
            self.candles(),
            [45.0, 52.0],
            [99.5, 100.0],
            ["bullish", "bullish"],
            [98.0, 98.0],
            [None, 1.2],
            50,
            "any",
        )
        self.assertEqual(side, "long_candidate")

    def test_low_volume_is_rejected_when_filter_is_enabled(self):
        side = pullback_reclaim_side(
            1,
            self.candles(),
            [45.0, 52.0],
            [99.5, 100.0],
            ["bullish", "bullish"],
            [98.0, 98.0],
            [None, 0.8],
            50,
            "at_least_1x",
        )
        self.assertIsNone(side)

    def test_no_signal_without_vwap_cross(self):
        candles = self.candles()
        candles[0] = Candle(candles[0].timestamp, 100, 102, 100, 101, 10)
        side = pullback_reclaim_side(
            1,
            candles,
            [55.0, 52.0],
            [99.5, 100.0],
            ["bullish", "bullish"],
            [98.0, 98.0],
            [None, 1.2],
            50,
            "any",
        )
        self.assertIsNone(side)


if __name__ == "__main__":
    unittest.main()
