import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from build_signal_observations import (
    build_hourly_context,
    crossing_side,
    directional_return,
    latest_completed_context,
    volume_bucket,
)
from core.models import Candle


class SignalDefinitionTests(unittest.TestCase):
    def test_emits_only_when_rsi_enters_extreme_zone(self):
        self.assertEqual(crossing_side(26, 24), "long_candidate")
        self.assertIsNone(crossing_side(24, 23))
        self.assertEqual(crossing_side(74, 76), "short_candidate")
        self.assertIsNone(crossing_side(76, 77))

    def test_directional_return_inverts_short_move(self):
        self.assertAlmostEqual(directional_return("long_candidate", 100, 102), 0.02)
        self.assertAlmostEqual(directional_return("short_candidate", 100, 98), 0.02)

    def test_volume_buckets_are_exploratory(self):
        self.assertEqual(volume_bucket(0.9), "<1x")
        self.assertEqual(volume_bucket(1.2), "1-1.5x")
        self.assertEqual(volume_bucket(1.7), "1.5-2x")
        self.assertEqual(volume_bucket(2.0), ">=2x")


class HourlyContextTests(unittest.TestCase):
    def setUp(self):
        self.hourly = []
        for hour in range(201):
            self.hourly.append(
                Candle(
                    timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc)
                    + timedelta(hours=hour),
                    open=100 + hour,
                    high=101 + hour,
                    low=99 + hour,
                    close=100 + hour,
                    volume=10,
                )
            )

    def test_current_hour_is_not_used_before_it_closes(self):
        contexts = build_hourly_context(self.hourly)
        timestamp = self.hourly[200].timestamp.replace(minute=30)
        context, _ = latest_completed_context(contexts, timestamp, 0)
        self.assertEqual(context["candle_time"], self.hourly[199].timestamp)

    def test_hour_becomes_available_at_close(self):
        contexts = build_hourly_context(self.hourly)
        timestamp = self.hourly[200].timestamp + timedelta(hours=1)
        context, _ = latest_completed_context(contexts, timestamp, 0)
        self.assertEqual(context["candle_time"], self.hourly[200].timestamp)


if __name__ == "__main__":
    unittest.main()
