import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from validate_by_period_and_regime import filter_signals, split_periods


class PeriodSplitTests(unittest.TestCase):
    def test_three_periods_cover_full_range(self):
        start = datetime(2026, 4, 1, tzinfo=timezone.utc)
        end = start + timedelta(days=90)
        periods = split_periods(start, end, 3)
        self.assertEqual(len(periods), 3)
        self.assertEqual(periods[0], (start, start + timedelta(days=30)))
        self.assertEqual(periods[-1][1], end)

    def test_filters_side_and_regime_without_crossing_boundary(self):
        start = datetime(2026, 4, 1, tzinfo=timezone.utc)
        boundary = start + timedelta(days=30)
        signals = [
            {
                "timestamp_utc": (boundary - timedelta(minutes=5)).isoformat(),
                "side": "long_candidate",
                "hourly_trend": "bullish",
            },
            {
                "timestamp_utc": boundary.isoformat(),
                "side": "long_candidate",
                "hourly_trend": "bullish",
            },
            {
                "timestamp_utc": (boundary - timedelta(minutes=10)).isoformat(),
                "side": "short_candidate",
                "hourly_trend": "bearish",
            },
        ]
        result = filter_signals(
            signals,
            start,
            boundary,
            False,
            side="long_candidate",
            trend="bullish",
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], signals[0])


if __name__ == "__main__":
    unittest.main()
