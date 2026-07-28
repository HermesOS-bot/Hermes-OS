import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.models import Candle
from core.paper_observer import PaperSignal
from core.paper_outcomes import evaluate_path
from core.trend_observer import (
    TREND_STRATEGY_VERSION,
    _continuation_side,
    _v2_reclaim_side,
    format_trend_message,
)
from infrastructure.paper_journal import PaperJournal


class TrendRuleTests(unittest.TestCase):
    def previous(self):
        return Candle(
            timestamp=datetime(2026, 7, 26, 10, 0, tzinfo=timezone.utc),
            open=99.0,
            high=100.0,
            low=98.0,
            close=99.0,
            volume=10.0,
        )

    def test_bullish_continuation_requires_rsi_recross_and_price_confirmation(self):
        side = _continuation_side(
            previous_rsi=49.0,
            current_rsi=51.0,
            hourly_context="bullish",
            session_return=0.01,
            current_close=100.5,
            session_vwap=99.5,
            previous_candle=self.previous(),
        )
        self.assertEqual(side, "long_candidate")

    def test_bearish_continuation_is_mirrored(self):
        side = _continuation_side(
            previous_rsi=51.0,
            current_rsi=49.0,
            hourly_context="bearish",
            session_return=-0.01,
            current_close=97.5,
            session_vwap=98.5,
            previous_candle=self.previous(),
        )
        self.assertEqual(side, "short_candidate")

    def test_trend_message_is_explicitly_paper_only(self):
        signal = PaperSignal(
            candle_time=datetime(2026, 7, 26, 10, 0, tzinfo=timezone.utc),
            observed_at=datetime(2026, 7, 26, 10, 5, tzinfo=timezone.utc),
            side="long_candidate",
            candle_close=100.0,
            rsi_14=51.0,
            relative_volume_20=1.2,
            hourly_context="bullish",
            ema_50_hourly=101.0,
            ema_200_hourly=99.0,
            session_open=98.0,
            session_high=101.0,
            session_low=97.0,
            session_return=100.0 / 98.0 - 1,
            session_range_position=0.75,
            session_vwap=99.0,
            price_vs_session_vwap=100.0 / 99.0 - 1,
            adx_14_hourly=27.0,
            strategy_version=TREND_STRATEGY_VERSION,
        )
        message = format_trend_message(signal, 99.9, 100.1)
        self.assertIn("ТРЕНДОВЫЙ ЛОНГ", message)
        self.assertIn("возврат через VWAP", message)
        self.assertIn("Реальная сделка не открыта", message)

    def test_v2_long_requires_adx_and_vwap_reclaim(self):
        side = _v2_reclaim_side(
            rsi_value=52.0,
            hourly_context="bullish",
            hourly_adx=27.0,
            session_return=0.01,
            previous_close=99.0,
            previous_vwap=99.5,
            current_close=100.5,
            current_vwap=100.0,
        )
        self.assertEqual(side, "long_candidate")

    def test_v2_rejects_weak_adx(self):
        side = _v2_reclaim_side(
            rsi_value=52.0,
            hourly_context="bullish",
            hourly_adx=24.9,
            session_return=0.01,
            previous_close=99.0,
            previous_vwap=99.5,
            current_close=100.5,
            current_vwap=100.0,
        )
        self.assertIsNone(side)

    def test_countertrend_candidate_is_rejected(self):
        side = _continuation_side(
            previous_rsi=49.0,
            current_rsi=51.0,
            hourly_context="bullish",
            session_return=-0.01,
            current_close=100.5,
            session_vwap=99.5,
            previous_candle=self.previous(),
        )
        self.assertIsNone(side)


class TrendJournalTests(unittest.TestCase):
    def test_migrates_existing_v1_trend_table_without_losing_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "paper.db"
            connection = sqlite3.connect(path)
            connection.execute(
                """
                CREATE TABLE trend_candidates (
                    signal_key TEXT PRIMARY KEY,
                    candle_time TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    side TEXT NOT NULL,
                    candle_close REAL NOT NULL,
                    rsi_14 REAL NOT NULL,
                    relative_volume_20 REAL,
                    hourly_context TEXT NOT NULL,
                    best_bid REAL NOT NULL,
                    best_ask REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    stop_price REAL NOT NULL,
                    session_open REAL NOT NULL,
                    session_high REAL NOT NULL,
                    session_low REAL NOT NULL,
                    session_return REAL NOT NULL,
                    session_range_position REAL,
                    session_vwap REAL,
                    price_vs_session_vwap REAL,
                    telegram_sent INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            connection.execute(
                """INSERT INTO trend_candidates VALUES (
                    'old', '2026-07-26T10:00:00+00:00',
                    '2026-07-26T10:05:00+00:00', 'long_candidate',
                    100, 51, 1.2, 'bullish', 99.9, 100.1, 100.1, 99.099,
                    98, 101, 97, 0.02, 0.75, 99, 0.01, 1
                )"""
            )
            connection.commit()
            connection.close()
            journal = PaperJournal(path)
            try:
                row = journal._connection.execute(
                    "SELECT strategy_version, adx_14_hourly FROM trend_candidates WHERE signal_key = 'old'"
                ).fetchone()
                self.assertEqual(row, ("trend-v1", None))
            finally:
                journal.close()

    def test_records_shadow_candidate_and_outcomes_without_rsi_signal(self):
        signal = PaperSignal(
            candle_time=datetime(2026, 7, 26, 10, 0, tzinfo=timezone.utc),
            observed_at=datetime(2026, 7, 26, 10, 5, tzinfo=timezone.utc),
            side="long_candidate",
            candle_close=100.0,
            rsi_14=51.0,
            relative_volume_20=1.2,
            hourly_context="bullish",
            ema_50_hourly=101.0,
            ema_200_hourly=99.0,
            session_open=98.0,
            session_high=101.0,
            session_low=97.0,
            session_return=100.0 / 98.0 - 1,
            session_range_position=0.75,
            session_vwap=99.0,
            price_vs_session_vwap=100.0 / 99.0 - 1,
            adx_14_hourly=27.0,
            strategy_version=TREND_STRATEGY_VERSION,
        )
        with tempfile.TemporaryDirectory() as directory:
            journal = PaperJournal(Path(directory) / "paper.db")
            try:
                journal.add_trend_candidate(signal, 99.9, 100.1, 100.1, 99.099)
                self.assertTrue(journal.trend_contains(signal.key))
                self.assertFalse(journal.contains(signal.key))
                self.assertFalse(journal.trend_telegram_was_sent(signal.key))
                journal.mark_trend_telegram_sent(signal.key)
                self.assertTrue(journal.trend_telegram_was_sent(signal.key))
                tracked = journal.tracked_trend_candidates()
                self.assertEqual(len(tracked), 1)
                self.assertEqual(tracked[0].strategy_version, TREND_STRATEGY_VERSION)
                stored = journal._connection.execute(
                    "SELECT strategy_version, adx_14_hourly FROM trend_candidates"
                ).fetchone()
                self.assertEqual(stored[0], TREND_STRATEGY_VERSION)
                self.assertEqual(stored[1], 27.0)
                outcome = evaluate_path(tracked[0], [], tracked[0].observed_at)
                journal.save_trend_path_outcome(signal.key, outcome)
                self.assertFalse(
                    journal.trend_outcome_notification_was_sent(
                        signal.key, final=False
                    )
                )
                journal.mark_trend_outcome_notification_sent(
                    signal.key, final=False
                )
                self.assertTrue(
                    journal.trend_outcome_notification_was_sent(
                        signal.key, final=False
                    )
                )
                rows = journal._connection.execute(
                    "SELECT COUNT(*) FROM trend_path_state"
                ).fetchone()[0]
                self.assertEqual(rows, 1)
            finally:
                journal.close()


if __name__ == "__main__":
    unittest.main()
