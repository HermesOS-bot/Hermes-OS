import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from research_trend_entries import passes_development, trend_side
from core.models import Candle


class TrendEntryVariantTests(unittest.TestCase):
    def candles(self):
        return [
            Candle(
                timestamp=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
                open=99.0,
                high=100.0,
                low=98.0,
                close=99.0,
                volume=10.0,
            ),
            Candle(
                timestamp=datetime(2026, 7, 27, 10, 5, tzinfo=timezone.utc),
                open=99.5,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=20.0,
            ),
        ]

    def test_early_long_recovery_without_breakout(self):
        side = trend_side(
            1,
            self.candles(),
            [39.0, 41.0],
            [99.0, 99.5],
            ["bullish", "bullish"],
            [98.0, 98.0],
            [None, 1.2],
            40,
            "none",
            "any",
        )
        self.assertEqual(side, "long_candidate")

    def test_volume_filter_rejects_low_volume(self):
        side = trend_side(
            1,
            self.candles(),
            [39.0, 41.0],
            [99.0, 99.5],
            ["bullish", "bullish"],
            [98.0, 98.0],
            [None, 0.8],
            40,
            "none",
            "at_least_1x",
        )
        self.assertIsNone(side)

    def test_breakout_is_stricter_than_candle_direction(self):
        candles = self.candles()
        candles[0] = Candle(
            timestamp=candles[0].timestamp,
            open=99.0,
            high=101.0,
            low=98.0,
            close=99.0,
            volume=10.0,
        )
        common = (
            1,
            candles,
            [44.0, 46.0],
            [99.0, 99.5],
            ["bullish", "bullish"],
            [98.0, 98.0],
            [None, 1.2],
            45,
        )
        self.assertIsNone(trend_side(*common, "breakout", "any"))
        self.assertEqual(
            trend_side(*common, "candle_direction", "any"), "long_candidate"
        )


class DevelopmentCriteriaTests(unittest.TestCase):
    def metric(self, compounded, trades=30, drawdown=-0.03):
        return {
            "compounded": compounded,
            "trades": trades,
            "drawdown": drawdown,
        }

    def test_requires_both_development_periods_positive(self):
        combined = self.metric(0.04, trades=60)
        self.assertFalse(
            passes_development(self.metric(0.02), self.metric(-0.01), combined)
        )

    def test_requires_minimum_sample_and_drawdown(self):
        positive = self.metric(0.02)
        self.assertFalse(
            passes_development(positive, positive, self.metric(0.04, trades=49))
        )
        self.assertFalse(
            passes_development(
                positive, positive, self.metric(0.04, trades=60, drawdown=-0.06)
            )
        )
        self.assertTrue(
            passes_development(
                positive, positive, self.metric(0.04, trades=60, drawdown=-0.04)
            )
        )


if __name__ == "__main__":
    unittest.main()
