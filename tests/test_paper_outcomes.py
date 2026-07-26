import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.models import Candle
from core.paper_outcomes import TrackedPaperSignal, evaluate_path, format_outcome_message


class PaperOutcomeTests(unittest.TestCase):
    def signal(self, side="long_candidate", observed_at=None):
        observed_at = observed_at or datetime(2026, 7, 25, 10, 0, tzinfo=timezone.utc)
        if side == "long_candidate":
            entry, stop = 100.1, 99.099
        else:
            entry, stop = 99.9, 100.899
        return TrackedPaperSignal(
            key="signal",
            observed_at=observed_at,
            side=side,
            entry_price=entry,
            best_bid=99.9,
            best_ask=100.1,
            stop_price=stop,
        )

    def candle(self, timestamp, close=100.0, high=100.5, low=99.5):
        return Candle(timestamp, close, high, low, close, 10.0)

    def test_records_fixed_horizon_independently_from_stop(self):
        signal = self.signal()
        candles = [
            self.candle(signal.observed_at, close=99.5, high=100.2, low=99.0),
            self.candle(signal.observed_at + timedelta(minutes=5), close=100.0),
            self.candle(signal.observed_at + timedelta(minutes=10), close=101.0),
        ]
        result = evaluate_path(
            signal, candles, signal.observed_at + timedelta(minutes=15)
        )
        self.assertTrue(result.stop_hit)
        self.assertEqual(result.stop_hit_time, signal.observed_at)
        self.assertIsNotNone(result.horizons[15].directional_return)
        self.assertGreater(result.horizons[15].directional_return, 0)

    def test_short_favorable_and_adverse_returns_have_correct_signs(self):
        signal = self.signal("short_candidate")
        candles = [self.candle(signal.observed_at, high=101.0, low=98.0)]
        result = evaluate_path(
            signal, candles, signal.observed_at + timedelta(minutes=5)
        )
        self.assertGreater(result.max_favorable_return, 0)
        self.assertLess(result.max_adverse_return, 0)
        self.assertTrue(result.stop_hit)

    def test_excludes_horizon_crossing_moscow_midnight(self):
        observed_at = datetime(2026, 7, 25, 20, 50, tzinfo=timezone.utc)
        signal = self.signal(observed_at=observed_at)
        candles = [
            self.candle(observed_at + timedelta(minutes=10), close=101.0)
        ]
        result = evaluate_path(
            signal, candles, observed_at + timedelta(minutes=15)
        )
        self.assertTrue(result.horizons[15].crosses_moscow_midnight)
        self.assertIsNone(result.horizons[15].directional_return)

    def test_formats_intermediate_and_final_messages(self):
        signal = self.signal()
        candles = [
            self.candle(signal.observed_at + timedelta(minutes=index), close=101.0)
            for index in range(0, 240, 5)
        ]
        result = evaluate_path(
            signal, candles, signal.observed_at + timedelta(minutes=240)
        )
        intermediate = format_outcome_message(signal, result, final=False)
        final = format_outcome_message(signal, result, final=True)
        trend = format_outcome_message(
            signal, result, final=False, strategy="trend"
        )
        self.assertIn("РЕЗУЛЬТАТ ЧЕРЕЗ ЧАС", intermediate)
        self.assertIn("60 мин", intermediate)
        self.assertIn("ИТОГ ЗА 4 ЧАСА", final)
        self.assertIn("Максимум в плюс", final)
        self.assertIn("Реальной сделки не было", final)
        self.assertIn("ТРЕНД — РЕЗУЛЬТАТ ЧЕРЕЗ ЧАС", trend)
        self.assertIn("Трендовая paper-гипотеза", trend)

    def test_ignores_incomplete_candle(self):
        signal = self.signal()
        candle = self.candle(signal.observed_at, close=101.0)
        result = evaluate_path(
            signal, [candle], signal.observed_at + timedelta(minutes=4)
        )
        self.assertIsNone(result.max_favorable_return)


if __name__ == "__main__":
    unittest.main()
