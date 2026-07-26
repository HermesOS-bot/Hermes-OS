#!/usr/bin/env python3
"""Run one read-only Hermes OS paper-observer cycle.

Designed to be called by a scheduler. It reads market data, records a fresh RSI
crossing and sends a private Telegram notification. It has no trading methods.
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from core.paper_observer import (  # noqa: E402
    detect_latest_signal,
    format_signal_message,
    hypothetical_entry,
    stop_price,
)
from core.trend_observer import detect_latest_trend_candidate  # noqa: E402
from infrastructure.paper_journal import PaperJournal  # noqa: E402
from infrastructure.tbank_market_data import TBankMarketDataClient  # noqa: E402
from infrastructure.telegram_notifier import TelegramNotifier  # noqa: E402

INSTRUMENT_ID = "4effa274-4e8f-422c-93ff-04aa34fe8e39"
JOURNAL_PATH = REPO_ROOT / "data" / "paper" / "hermes-paper.db"


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError("Missing required environment variable: " + name)
    return value


def main() -> int:
    now = datetime.now(timezone.utc)
    market = TBankMarketDataClient(required_env("TBANK_INVEST_TOKEN"))
    five_minute = market.get_candles(
        INSTRUMENT_ID,
        "CANDLE_INTERVAL_5_MIN",
        now - timedelta(days=5),
        now,
        limit=2000,
    )
    hourly = market.get_candles(
        INSTRUMENT_ID,
        "CANDLE_INTERVAL_HOUR",
        now - timedelta(days=30),
        now,
        limit=1000,
    )
    signal = detect_latest_signal(five_minute, hourly)
    trend = detect_latest_trend_candidate(five_minute, hourly)
    if signal is not None and now - signal.observed_at > timedelta(minutes=12):
        signal = None
    if trend is not None and now - trend.observed_at > timedelta(minutes=12):
        trend = None

    journal = PaperJournal(JOURNAL_PATH)
    try:
        needs_signal = signal is not None and (
            not journal.contains(signal.key)
            or not journal.telegram_was_sent(signal.key)
        )
        needs_trend = trend is not None and not journal.trend_contains(trend.key)
        if not needs_signal and not needs_trend:
            print("No new RSI crossing or shadow trend candidate")
            return 0

        book = market.get_order_book(INSTRUMENT_ID, depth=1)
        if book.best_bid is None or book.best_ask is None:
            raise RuntimeError("Order book has no bid or ask")

        if needs_trend:
            trend_entry = hypothetical_entry(trend, book.best_bid, book.best_ask)
            journal.add_trend_candidate(
                trend,
                book.best_bid,
                book.best_ask,
                trend_entry,
                stop_price(trend, trend_entry),
            )
            print("Shadow trend candidate recorded; no Telegram notification")

        if needs_signal:
            entry = hypothetical_entry(signal, book.best_bid, book.best_ask)
            stop = stop_price(signal, entry)
            if not journal.contains(signal.key):
                journal.add(signal, book.best_bid, book.best_ask, entry, stop)
            else:
                print("Retrying Telegram delivery for recorded RSI signal")
            notifier = TelegramNotifier(
                required_env("HERMES_TG_BOT_TOKEN"),
                required_env("HERMES_TG_CHAT_ID"),
                proxy_url=os.environ.get("TG_PROXY_URL") or None,
            )
            notifier.send(format_signal_message(signal, book.best_bid, book.best_ask))
            journal.mark_telegram_sent(signal.key)
            print("RSI paper signal recorded and sent")
        return 0
    finally:
        journal.close()


if __name__ == "__main__":
    sys.exit(main())
