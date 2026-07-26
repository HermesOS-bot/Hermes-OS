#!/usr/bin/env python3
"""Update stop and fixed-horizon outcomes for recorded paper signals."""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from core.paper_outcomes import evaluate_path, format_outcome_message  # noqa: E402
from infrastructure.paper_journal import PaperJournal  # noqa: E402
from infrastructure.tbank_market_data import TBankMarketDataClient  # noqa: E402
from infrastructure.telegram_notifier import TelegramNotifier  # noqa: E402

INSTRUMENT_ID = "4effa274-4e8f-422c-93ff-04aa34fe8e39"
JOURNAL_PATH = REPO_ROOT / "data" / "paper" / "hermes-paper.db"


def main() -> int:
    token = os.environ.get("TBANK_INVEST_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Missing TBANK_INVEST_TOKEN")

    now = datetime.now(timezone.utc)
    market = TBankMarketDataClient(token)
    candles = market.get_candles(
        INSTRUMENT_ID,
        "CANDLE_INTERVAL_5_MIN",
        now - timedelta(days=5),
        now,
        limit=2000,
    )
    journal = PaperJournal(JOURNAL_PATH)
    updated = 0
    trend_updated = 0
    notifications = 0
    notifier = None

    def send(signal, outcome, final, strategy="rsi"):
        nonlocal notifier, notifications
        was_sent = (
            journal.trend_outcome_notification_was_sent(signal.key, final)
            if strategy == "trend"
            else journal.outcome_notification_was_sent(signal.key, final)
        )
        if was_sent:
            return
        horizon = outcome.horizons[240 if final else 60]
        if now < horizon.target_time:
            return
        if horizon.directional_return is None and not horizon.crosses_moscow_midnight:
            return
        if notifier is None:
            notifier = TelegramNotifier(
                os.environ.get("HERMES_TG_BOT_TOKEN", "").strip(),
                os.environ.get("HERMES_TG_CHAT_ID", "").strip(),
                proxy_url=os.environ.get("TG_PROXY_URL") or None,
            )
        notifier.send(
            format_outcome_message(signal, outcome, final, strategy=strategy)
        )
        if strategy == "trend":
            journal.mark_trend_outcome_notification_sent(signal.key, final)
        else:
            journal.mark_outcome_notification_sent(signal.key, final)
        notifications += 1

    try:
        for signal in journal.tracked_signals():
            if signal.observed_at > now:
                continue
            outcome = evaluate_path(signal, candles, now)
            journal.save_path_outcome(signal.key, outcome)
            send(signal, outcome, final=False)
            send(signal, outcome, final=True)
            updated += 1
        for signal in journal.tracked_trend_candidates():
            if signal.observed_at > now:
                continue
            outcome = evaluate_path(signal, candles, now)
            journal.save_trend_path_outcome(signal.key, outcome)
            send(signal, outcome, final=False, strategy="trend")
            send(signal, outcome, final=True, strategy="trend")
            trend_updated += 1
    finally:
        journal.close()

    print("Updated RSI paper outcomes:", updated)
    print("Updated trend paper outcomes:", trend_updated)
    print("Telegram outcome notifications:", notifications)
    return 0


if __name__ == "__main__":
    sys.exit(main())
