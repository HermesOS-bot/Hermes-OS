import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from core.paper_observer import PaperSignal, format_signal_message, hypothetical_entry, stop_price
from core.paper_outcomes import evaluate_path
from infrastructure.paper_journal import PaperJournal
from infrastructure.tbank_market_data import TBankMarketDataClient


class PaperSignalTests(unittest.TestCase):
    def signal(self, side):
        return PaperSignal(
            candle_time=datetime(2026, 7, 25, 10, 0, tzinfo=timezone.utc),
            observed_at=datetime(2026, 7, 25, 10, 5, tzinfo=timezone.utc),
            side=side,
            candle_close=100.0,
            rsi_14=24.5 if side == "long_candidate" else 75.5,
            relative_volume_20=1.8,
            hourly_context="bullish",
            ema_50_hourly=101.0,
            ema_200_hourly=99.0,
            session_open=98.0,
            session_high=102.0,
            session_low=97.0,
            session_return=100.0 / 98.0 - 1,
            session_range_position=0.6,
            session_vwap=99.0,
            price_vs_session_vwap=100.0 / 99.0 - 1,
        )

    def test_long_uses_ask_and_stop_below_entry(self):
        signal = self.signal("long_candidate")
        self.assertEqual(hypothetical_entry(signal, 99.0, 101.0), 101.0)
        self.assertAlmostEqual(stop_price(signal, 101.0), 99.99)

    def test_short_uses_bid_and_stop_above_entry(self):
        signal = self.signal("short_candidate")
        self.assertEqual(hypothetical_entry(signal, 99.0, 101.0), 99.0)
        self.assertAlmostEqual(stop_price(signal, 99.0), 99.99)

    def test_message_explicitly_says_no_trade_was_opened(self):
        message = format_signal_message(self.signal("long_candidate"), 99.0, 101.0)
        self.assertIn("КРАТКОСРОЧНЫЙ ОТСКОК ВВЕРХ", message)
        self.assertIn("Часовой контекст: восходящий", message)
        self.assertIn("Сессия от открытия: +2.04%", message)
        self.assertIn("Положение в диапазоне: 60%", message)
        self.assertIn("Сигнал: по движению сессии", message)
        self.assertIn("не прогноз разворота дня", message)
        self.assertIn("Реальная сделка не открыта", message)


class PaperJournalTests(unittest.TestCase):
    def test_records_and_marks_telegram_delivery(self):
        signal = PaperSignal(
            candle_time=datetime(2026, 7, 25, 10, 0, tzinfo=timezone.utc),
            observed_at=datetime(2026, 7, 25, 10, 5, tzinfo=timezone.utc),
            side="long_candidate",
            candle_close=100.0,
            rsi_14=24.5,
            relative_volume_20=1.8,
            hourly_context="bullish",
            ema_50_hourly=101.0,
            ema_200_hourly=99.0,
            session_open=98.0,
            session_high=102.0,
            session_low=97.0,
            session_return=100.0 / 98.0 - 1,
            session_range_position=0.6,
            session_vwap=99.0,
            price_vs_session_vwap=100.0 / 99.0 - 1,
        )
        with tempfile.TemporaryDirectory() as directory:
            journal = PaperJournal(Path(directory) / "paper.db")
            try:
                journal.add(signal, 99.0, 101.0, 101.0, 99.99)
                self.assertTrue(journal.contains(signal.key))
                self.assertFalse(journal.telegram_was_sent(signal.key))
                journal.mark_telegram_sent(signal.key)
                self.assertTrue(journal.telegram_was_sent(signal.key))
                row = journal._connection.execute(
                    """
                    SELECT session_return, session_range_position,
                           price_vs_session_vwap
                    FROM paper_signals WHERE signal_key = ?
                    """,
                    (signal.key,),
                ).fetchone()
                self.assertAlmostEqual(row[0], signal.session_return)
                self.assertAlmostEqual(row[1], 0.6)
                self.assertAlmostEqual(row[2], signal.price_vs_session_vwap)
                tracked = journal.tracked_signals()
                self.assertEqual(len(tracked), 1)
                outcome = evaluate_path(
                    tracked[0], [], tracked[0].observed_at
                )
                journal.save_path_outcome(signal.key, outcome)
                self.assertFalse(
                    journal.outcome_notification_was_sent(signal.key, final=False)
                )
                journal.mark_outcome_notification_sent(signal.key, final=False)
                self.assertTrue(
                    journal.outcome_notification_was_sent(signal.key, final=False)
                )
            finally:
                journal.close()


class OrderBookTests(unittest.TestCase):
    def test_extracts_best_bid_ask_and_spread(self):
        client = TBankMarketDataClient("test-token")
        client._post = Mock(
            return_value={
                "bids": [{"price": {"units": "99", "nano": 500000000}}],
                "asks": [{"price": {"units": "100", "nano": 500000000}}],
            }
        )
        book = client.get_order_book("instrument")
        self.assertEqual(book.best_bid, 99.5)
        self.assertEqual(book.best_ask, 100.5)
        self.assertAlmostEqual(book.midpoint, 100.0)
        self.assertAlmostEqual(book.spread_fraction, 0.01)


if __name__ == "__main__":
    unittest.main()
