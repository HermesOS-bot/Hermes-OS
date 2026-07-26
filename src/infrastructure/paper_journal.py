"""SQLite journal for paper signals. Generated databases stay outside Git."""

import sqlite3
from datetime import datetime
from pathlib import Path

from core.paper_observer import PaperSignal
from core.paper_outcomes import HorizonOutcome, PathOutcome, TrackedPaperSignal

_SIGNAL_CONTEXT_COLUMNS = (
    "session_open",
    "session_high",
    "session_low",
    "session_return",
    "session_range_position",
    "session_vwap",
    "price_vs_session_vwap",
)


class PaperJournal:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(path))
        self._create_rsi_tables()
        self._create_trend_tables()
        self._connection.commit()

    def _create_rsi_tables(self) -> None:
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
                session_open REAL,
                session_high REAL,
                session_low REAL,
                session_return REAL,
                session_range_position REAL,
                session_vwap REAL,
                price_vs_session_vwap REAL,
                telegram_sent INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        existing_columns = {
            row[1]
            for row in self._connection.execute("PRAGMA table_info(paper_signals)")
        }
        for column in _SIGNAL_CONTEXT_COLUMNS:
            if column not in existing_columns:
                self._connection.execute(
                    "ALTER TABLE paper_signals ADD COLUMN {} REAL".format(column)
                )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_path_state (
                signal_key TEXT PRIMARY KEY,
                stop_hit INTEGER NOT NULL,
                stop_hit_time TEXT,
                max_favorable_return REAL,
                max_adverse_return REAL,
                intermediate_sent INTEGER NOT NULL DEFAULT 0,
                final_sent INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(signal_key) REFERENCES paper_signals(signal_key)
            )
            """
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_horizon_outcomes (
                signal_key TEXT NOT NULL,
                horizon_minutes INTEGER NOT NULL,
                target_time TEXT NOT NULL,
                candle_time TEXT,
                reference_close REAL,
                estimated_exit_price REAL,
                directional_return REAL,
                crosses_moscow_midnight INTEGER NOT NULL,
                PRIMARY KEY(signal_key, horizon_minutes),
                FOREIGN KEY(signal_key) REFERENCES paper_signals(signal_key)
            )
            """
        )

    def _create_trend_tables(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS trend_candidates (
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
                price_vs_session_vwap REAL
            )
            """
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS trend_path_state (
                signal_key TEXT PRIMARY KEY,
                stop_hit INTEGER NOT NULL,
                stop_hit_time TEXT,
                max_favorable_return REAL,
                max_adverse_return REAL,
                FOREIGN KEY(signal_key) REFERENCES trend_candidates(signal_key)
            )
            """
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS trend_horizon_outcomes (
                signal_key TEXT NOT NULL,
                horizon_minutes INTEGER NOT NULL,
                target_time TEXT NOT NULL,
                candle_time TEXT,
                reference_close REAL,
                estimated_exit_price REAL,
                directional_return REAL,
                crosses_moscow_midnight INTEGER NOT NULL,
                PRIMARY KEY(signal_key, horizon_minutes),
                FOREIGN KEY(signal_key) REFERENCES trend_candidates(signal_key)
            )
            """
        )

    def contains(self, signal_key: str) -> bool:
        return self._contains("paper_signals", signal_key)

    def trend_contains(self, signal_key: str) -> bool:
        return self._contains("trend_candidates", signal_key)

    def _contains(self, table: str, signal_key: str) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM {} WHERE signal_key = ?".format(table), (signal_key,)
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
        self._insert_signal(
            "paper_signals", signal, best_bid, best_ask, entry_price, stop_price
        )

    def add_trend_candidate(
        self,
        signal: PaperSignal,
        best_bid: float,
        best_ask: float,
        entry_price: float,
        stop_price: float,
    ) -> None:
        self._insert_signal(
            "trend_candidates", signal, best_bid, best_ask, entry_price, stop_price
        )

    def _insert_signal(
        self,
        table: str,
        signal: PaperSignal,
        best_bid: float,
        best_ask: float,
        entry_price: float,
        stop_price: float,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO {} (
                signal_key, candle_time, observed_at, side, candle_close, rsi_14,
                relative_volume_20, hourly_context, best_bid, best_ask,
                entry_price, stop_price, session_open, session_high, session_low,
                session_return, session_range_position, session_vwap,
                price_vs_session_vwap
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """.format(table),
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
                signal.session_open,
                signal.session_high,
                signal.session_low,
                signal.session_return,
                signal.session_range_position,
                signal.session_vwap,
                signal.price_vs_session_vwap,
            ),
        )
        self._connection.commit()

    def tracked_signals(self):
        return self._tracked_from("paper_signals")

    def tracked_trend_candidates(self):
        return self._tracked_from("trend_candidates")

    def _tracked_from(self, table: str):
        rows = self._connection.execute(
            """
            SELECT signal_key, observed_at, side, entry_price, best_bid,
                   best_ask, stop_price
            FROM {}
            ORDER BY observed_at
            """.format(table)
        ).fetchall()
        return [
            TrackedPaperSignal(
                key=row[0],
                observed_at=datetime.fromisoformat(row[1]),
                side=row[2],
                entry_price=row[3],
                best_bid=row[4],
                best_ask=row[5],
                stop_price=row[6],
            )
            for row in rows
        ]

    def save_path_outcome(self, signal_key: str, outcome: PathOutcome) -> None:
        self._save_path(
            "paper_path_state", "paper_horizon_outcomes", signal_key, outcome
        )

    def save_trend_path_outcome(
        self, signal_key: str, outcome: PathOutcome
    ) -> None:
        self._save_path(
            "trend_path_state", "trend_horizon_outcomes", signal_key, outcome
        )

    def _save_path(
        self,
        path_table: str,
        horizon_table: str,
        signal_key: str,
        outcome: PathOutcome,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO {} (
                signal_key, stop_hit, stop_hit_time,
                max_favorable_return, max_adverse_return
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(signal_key) DO UPDATE SET
                stop_hit = excluded.stop_hit,
                stop_hit_time = excluded.stop_hit_time,
                max_favorable_return = excluded.max_favorable_return,
                max_adverse_return = excluded.max_adverse_return
            """.format(path_table),
            (
                signal_key,
                int(outcome.stop_hit),
                outcome.stop_hit_time.isoformat() if outcome.stop_hit_time else None,
                outcome.max_favorable_return,
                outcome.max_adverse_return,
            ),
        )
        for horizon in outcome.horizons.values():
            if horizon.directional_return is None and not horizon.crosses_moscow_midnight:
                continue
            self._save_horizon(horizon_table, signal_key, horizon)
        self._connection.commit()

    def _save_horizon(
        self, table: str, signal_key: str, outcome: HorizonOutcome
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO {} (
                signal_key, horizon_minutes, target_time, candle_time,
                reference_close, estimated_exit_price, directional_return,
                crosses_moscow_midnight
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(signal_key, horizon_minutes) DO UPDATE SET
                candle_time = excluded.candle_time,
                reference_close = excluded.reference_close,
                estimated_exit_price = excluded.estimated_exit_price,
                directional_return = excluded.directional_return,
                crosses_moscow_midnight = excluded.crosses_moscow_midnight
            """.format(table),
            (
                signal_key,
                outcome.horizon_minutes,
                outcome.target_time.isoformat(),
                outcome.candle_time.isoformat() if outcome.candle_time else None,
                outcome.reference_close,
                outcome.estimated_exit_price,
                outcome.directional_return,
                int(outcome.crosses_moscow_midnight),
            ),
        )

    def outcome_notification_was_sent(self, signal_key: str, final: bool) -> bool:
        column = "final_sent" if final else "intermediate_sent"
        row = self._connection.execute(
            "SELECT {} FROM paper_path_state WHERE signal_key = ?".format(column),
            (signal_key,),
        ).fetchone()
        return bool(row and row[0])

    def mark_outcome_notification_sent(self, signal_key: str, final: bool) -> None:
        column = "final_sent" if final else "intermediate_sent"
        self._connection.execute(
            "UPDATE paper_path_state SET {} = 1 WHERE signal_key = ?".format(column),
            (signal_key,),
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
