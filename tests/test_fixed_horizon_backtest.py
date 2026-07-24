import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from backtest_fixed_horizons import (
    build_trades,
    crosses_moscow_midnight,
    directional_return,
    maximum_drawdown,
    metrics,
)


class BacktestExecutionTests(unittest.TestCase):
    def setUp(self):
        start = datetime(2026, 7, 24, 9, tzinfo=timezone.utc)
        self.candles = []
        for index in range(20):
            price = 100 + index
            self.candles.append(
                {
                    "timestamp": start + timedelta(minutes=5 * index),
                    "open": price,
                    "high": price + 1,
                    "low": price - 1,
                    "close": price + 0.5,
                    "volume": 10,
                }
            )

    def test_enters_on_next_candle_open(self):
        signal = {
            "timestamp_utc": self.candles[0]["timestamp"].isoformat(),
            "side": "long_candidate",
        }
        trades = build_trades(self.candles, [signal], 15)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["entry_price"], self.candles[1]["open"])
        self.assertEqual(trades[0]["exit_price"], self.candles[3]["close"])

    def test_skips_overlapping_signal(self):
        signals = [
            {
                "timestamp_utc": self.candles[0]["timestamp"].isoformat(),
                "side": "long_candidate",
            },
            {
                "timestamp_utc": self.candles[1]["timestamp"].isoformat(),
                "side": "short_candidate",
            },
        ]
        self.assertEqual(len(build_trades(self.candles, signals, 15)), 1)

    def test_skips_position_crossing_moscow_midnight(self):
        entry = datetime(2026, 7, 24, 20, 50, tzinfo=timezone.utc)
        exit_time = entry + timedelta(minutes=15)
        self.assertTrue(crosses_moscow_midnight(entry, exit_time))


class BacktestMetricTests(unittest.TestCase):
    def test_short_return_is_positive_when_price_falls(self):
        self.assertAlmostEqual(directional_return("short_candidate", 100, 98), 0.02)

    def test_cost_is_subtracted_from_each_trade(self):
        trades = [{"gross_return": 0.001}, {"gross_return": 0.002}]
        result = metrics(trades, 5)
        self.assertAlmostEqual(result["mean"], 0.001)

    def test_drawdown_uses_compounded_equity(self):
        self.assertAlmostEqual(maximum_drawdown([0.1, -0.2]), -0.2)


if __name__ == "__main__":
    unittest.main()
