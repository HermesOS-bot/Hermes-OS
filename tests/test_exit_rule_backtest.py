import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from backtest_exit_rules import (
    build_rsi_signals,
    rsi_neutral_exit,
    session_vwap_series,
    simulate_trades,
    stop_was_hit,
    trend_breakdown_exit,
)
from core.models import Candle


class ExitConditionTests(unittest.TestCase):
    def candle(self, high=101.0, low=99.0):
        return Candle(
            timestamp=datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc),
            open=100.0,
            high=high,
            low=low,
            close=100.0,
            volume=10.0,
        )

    def test_stop_is_mirrored(self):
        self.assertTrue(stop_was_hit("long_candidate", self.candle(low=98.9), 99.0))
        self.assertTrue(stop_was_hit("short_candidate", self.candle(high=101.1), 101.0))

    def test_rsi_neutral_exit_requires_crossing(self):
        self.assertTrue(rsi_neutral_exit("long_candidate", 49.0, 51.0))
        self.assertTrue(rsi_neutral_exit("short_candidate", 51.0, 49.0))
        self.assertFalse(rsi_neutral_exit("long_candidate", 51.0, 52.0))

    def test_trend_breakdown_requires_rsi_and_vwap(self):
        self.assertTrue(
            trend_breakdown_exit("long_candidate", 51.0, 49.0, 98.0, 99.0)
        )
        self.assertFalse(
            trend_breakdown_exit("long_candidate", 51.0, 49.0, 100.0, 99.0)
        )
        self.assertTrue(
            trend_breakdown_exit("short_candidate", 49.0, 51.0, 100.0, 99.0)
        )


class ExitSimulationTests(unittest.TestCase):
    def setUp(self):
        start = datetime(2026, 7, 27, 9, 0, tzinfo=timezone.utc)
        self.candles = []
        for index in range(20):
            self.candles.append(
                Candle(
                    timestamp=start + timedelta(minutes=5 * index),
                    open=100.0,
                    high=100.2,
                    low=99.8,
                    close=100.0 + index * 0.01,
                    volume=10.0,
                )
            )
        self.vwap = session_vwap_series(self.candles)

    def test_r0_exits_after_sixty_minutes(self):
        rsi_values = [40.0] * len(self.candles)
        trades = simulate_trades(
            self.candles,
            [{"index": 0, "side": "long_candidate"}],
            rsi_values,
            self.vwap,
            "R0",
        )
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["holding_minutes"], 60)
        self.assertEqual(trades[0]["exit_reason"], "time_60m")

    def test_r2_uses_earlier_rsi_exit(self):
        rsi_values = [20.0, 30.0, 49.0, 51.0] + [55.0] * 16
        trades = simulate_trades(
            self.candles,
            [{"index": 0, "side": "long_candidate"}],
            rsi_values,
            self.vwap,
            "R2",
        )
        self.assertEqual(trades[0]["exit_reason"], "rsi_neutral")
        self.assertEqual(trades[0]["holding_minutes"], 15)

    def test_stop_has_priority_over_close_rule(self):
        candles = list(self.candles)
        candles[1] = Candle(
            timestamp=candles[1].timestamp,
            open=100.0,
            high=101.0,
            low=98.5,
            close=101.0,
            volume=10.0,
        )
        rsi_values = [49.0, 51.0] + [55.0] * 18
        trades = simulate_trades(
            candles,
            [{"index": 0, "side": "long_candidate"}],
            rsi_values,
            session_vwap_series(candles),
            "R2",
        )
        self.assertEqual(trades[0]["exit_reason"], "stop_1.00%")
        self.assertAlmostEqual(trades[0]["gross_return"], -0.01)

    def test_build_rsi_signals_only_on_entry_to_extreme(self):
        rsi_values = [30.0, 24.0, 20.0, 76.0]
        signals = build_rsi_signals(self.candles[:4], rsi_values)
        self.assertEqual([signal["side"] for signal in signals], ["long_candidate", "short_candidate"])


if __name__ == "__main__":
    unittest.main()
