import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from research_trend_contexts import classify_context


class HourlyContextDefinitionTests(unittest.TestCase):
    def test_fast_ema_cross_classifies_direction(self):
        rising = [float(value) for value in range(1, 31)]
        falling = list(reversed(rising))
        self.assertEqual(
            classify_context("ema_cross", rising, len(rising) - 1, fast=3, slow=8),
            "bullish",
        )
        self.assertEqual(
            classify_context("ema_cross", falling, len(falling) - 1, fast=3, slow=8),
            "bearish",
        )

    def test_price_and_slope_must_agree(self):
        rising = [100.0 + value for value in range(30)]
        self.assertEqual(
            classify_context(
                "price_slope", rising, len(rising) - 1, period=5, slope_lookback=3
            ),
            "bullish",
        )
        falling = [130.0 - value for value in range(30)]
        self.assertEqual(
            classify_context(
                "price_slope", falling, len(falling) - 1, period=5, slope_lookback=3
            ),
            "bearish",
        )

    def test_unknown_until_indicators_are_ready(self):
        self.assertEqual(
            classify_context("ema_cross", [1.0, 2.0], 1, fast=2, slow=5),
            "unknown",
        )


if __name__ == "__main__":
    unittest.main()
