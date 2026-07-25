"""SQLite journal for paper signals. Generated databases stay outside Git."""

import sqlite3
from pathlib import Path

from core.paper_observer import PaperSignal


class PaperJournal:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(path))
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_signals (
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
                telegram_sent INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self._connection.commit()

    def contains(self, signal_key: str) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM paper_signals WHERE signal_key = ?", (signal_key,)
        ).fetchone()
        return row is not None

    def telegram_was_sent(self, signal_key: str) -> bool:
        row = self._connection.execute(
            "SELECT telegram_sent FROM paper_signals WHERE signal_key = ?",
            (signal_key,),
        ).fetchone()
        return bool(row and row[0])

    def add(
        self,
        signal: PaperSignal,
        best_bid: float,
        best_ask: float,
        entry_price: float,
        stop_price: float,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO paper_signals (
                signal_key, candle_time, observed_at, side, candle_close, rsi_14,
                relative_volume_20, hourly_context, best_bid, best_ask,
                entry_price, stop_price
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal.key,
                signal.candle_time.isoformat(),
                signal.observed_at.isoformat(),
                signal.side,
                signal.candle_close,
                signal.rsi_14,
                signal.relative_volume_20,
                signal.hourly_context,
                best_bid,
                best_ask,
                entry_price,
                stop_price,
            ),
        )
        self._connection.commit()

    def mark_telegram_sent(self, signal_key: str) -> None:
        self._connection.execute(
            "UPDATE paper_signals SET telegram_sent = 1 WHERE signal_key = ?",
            (signal_key,),
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()
