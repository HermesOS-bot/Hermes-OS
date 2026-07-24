import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from build_signal_observations import build_hourly_context, latest_completed_context
from core.models import Candle


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
