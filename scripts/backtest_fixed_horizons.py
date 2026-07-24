#!/usr/bin/env python3
"""Backtest fixed holding periods after RSI threshold crossings.

Execution assumptions:
- the signal is known only after its 5-minute candle closes;
- entry is at the next candle's open;
- exit is at a later candle's close after 15, 30 or 60 minutes;
- only one position may be open at a time for each horizon;
- positions crossing 00:00 Moscow time are skipped to keep the test intraday;
- NEO buy/sell commission is zero; uncertain spread/slippage is tested through
  several round-trip cost scenarios.

This remains research code. It does not place orders.
"""

import csv
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data" / "market"
RESEARCH_DIR = REPO_ROOT / "data" / "research"
MOSCOW_TIME = timezone(timedelta(hours=3))
HORIZONS_MINUTES = (15, 30, 60)
ROUND_TRIP_COST_BPS = (0, 2, 5, 10)


def load_candles(path: Path) -> List[Dict[str, object]]:
    rows = []
    with path.open("r", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            rows.append(
                {
                    "timestamp": datetime.fromisoformat(row["timestamp_utc"]),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                }
            )
    return sorted(rows, key=lambda row: row["timestamp"])


def load_signals(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def directional_return(side: str, entry: float, exit_price: float) -> float:
    raw = exit_price / entry - 1
    return raw if side == "long_candidate" else -raw


def crosses_moscow_midnight(entry_time: datetime, exit_time: datetime) -> bool:
    return entry_time.astimezone(MOSCOW_TIME).date() != exit_time.astimezone(
        MOSCOW_TIME
    ).date()


def build_trades(
    candles: List[Dict[str, object]],
    signals: Iterable[Dict[str, str]],
    horizon_minutes: int,
) -> List[Dict[str, object]]:
    by_time = {row["timestamp"]: row for row in candles}
    next_available_time = None
    trades = []

    for signal in signals:
        signal_time = datetime.fromisoformat(signal["timestamp_utc"])
        entry_time = signal_time + timedelta(minutes=5)
        exit_time = entry_time + timedelta(minutes=horizon_minutes)
        exit_candle_time = exit_time - timedelta(minutes=5)

        if next_available_time is not None and entry_time < next_available_time:
            continue
        if crosses_moscow_midnight(entry_time, exit_time):
            continue

        entry_candle = by_time.get(entry_time)
        exit_candle = by_time.get(exit_candle_time)
        if entry_candle is None or exit_candle is None:
            continue

        side = signal["side"]
        entry_price = entry_candle["open"]
        exit_price = exit_candle["close"]
        gross_return = directional_return(side, entry_price, exit_price)
        trades.append(
            {
                "horizon_minutes": horizon_minutes,
                "signal_time_utc": signal_time.isoformat(),
                "entry_time_utc": entry_time.isoformat(),
                "exit_time_utc": exit_time.isoformat(),
                "side": side,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "gross_return": gross_return,
                "rsi_14": signal.get("rsi_14", ""),
                "relative_volume_20": signal.get("relative_volume_20", ""),
                "volume_bucket": signal.get("volume_bucket", ""),
                "hourly_trend": signal.get("hourly_trend", ""),
                "trend_supports_signal": signal.get("trend_supports_signal", ""),
            }
        )
        next_available_time = exit_time

    return trades


def maximum_drawdown(returns: Iterable[float]) -> float:
    equity = 1.0
    peak = 1.0
    worst = 0.0
    for value in returns:
        equity *= 1 + value
        peak = max(peak, equity)
        drawdown = equity / peak - 1
        worst = min(worst, drawdown)
    return worst


def metrics(trades: List[Dict[str, object]], round_trip_cost_bps: int) -> Dict[str, float]:
    cost = round_trip_cost_bps / 10_000
    returns = [trade["gross_return"] - cost for trade in trades]
    if not returns:
        return {
            "count": 0,
            "win_rate": 0.0,
            "mean": 0.0,
            "median": 0.0,
            "compounded": 0.0,
            "max_drawdown": 0.0,
        }
    equity = 1.0
    for value in returns:
        equity *= 1 + value
    return {
        "count": len(returns),
        "win_rate": sum(value > 0 for value in returns) / len(returns),
        "mean": statistics.mean(returns),
        "median": statistics.median(returns),
        "compounded": equity - 1,
        "max_drawdown": maximum_drawdown(returns),
    }


def write_trades(path: Path, trades: List[Dict[str, object]]) -> None:
    fields = [
        "strategy_scope",
        "horizon_minutes",
        "signal_time_utc",
        "entry_time_utc",
        "exit_time_utc",
        "side",
        "entry_price",
        "exit_price",
        "gross_return",
        "rsi_14",
        "relative_volume_20",
        "volume_bucket",
        "hourly_trend",
        "trend_supports_signal",
    ]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for trade in trades:
            row = dict(trade)
            row["gross_return"] = "{:.8f}".format(row["gross_return"])
            writer.writerow(row)


def write_report(
    path: Path,
    all_trades_by_horizon: Dict[int, List[Dict[str, object]]],
    long_trades_by_horizon: Dict[int, List[Dict[str, object]]],
    short_trades_by_horizon: Dict[int, List[Dict[str, object]]],
) -> None:
    lines = [
        "# BTCUSDperpA fixed-horizon backtest",
        "",
        "Entry: next 5-minute candle open after the RSI crossing.",
        "Exit: candle close after the stated holding period.",
        "Only one position at a time. Trades crossing 00:00 Moscow are skipped.",
        "NEO buy/sell commission: 0. Spread and slippage are modeled as round-trip cost scenarios.",
        "Position size: one equal unleveraged unit per trade.",
        "",
        "This is research, not a recommendation or proof of future profitability.",
        "",
    ]
    for horizon in HORIZONS_MINUTES:
        groups = [
            ("All signals, one shared position", all_trades_by_horizon[horizon]),
            ("Long-only strategy", long_trades_by_horizon[horizon]),
            ("Short-only strategy", short_trades_by_horizon[horizon]),
        ]
        lines.extend(["## Hold {} minutes".format(horizon), ""])
        for group_name, group_trades in groups:
            lines.extend(["### " + group_name, ""])
            for cost_bps in ROUND_TRIP_COST_BPS:
                result = metrics(group_trades, cost_bps)
                lines.extend(
                    [
                        "#### Round-trip spread/slippage: {} bps".format(cost_bps),
                        "",
                        "- Trades: {}".format(result["count"]),
                        "- Win rate: {:.1%}".format(result["win_rate"]),
                        "- Mean per trade: {:+.3%}".format(result["mean"]),
                        "- Median per trade: {:+.3%}".format(result["median"]),
                        "- Compounded result: {:+.2%}".format(result["compounded"]),
                        "- Maximum drawdown: {:+.2%}".format(result["max_drawdown"]),
                        "",
                    ]
                )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    candles = load_candles(DATA_DIR / "BTCUSDperpA_5min.csv")
    signals = load_signals(RESEARCH_DIR / "BTCUSDperpA_signal_observations.csv")
    long_signals = [signal for signal in signals if signal["side"] == "long_candidate"]
    short_signals = [signal for signal in signals if signal["side"] == "short_candidate"]
    trades_by_scope = {
        "all": {
            horizon: build_trades(candles, signals, horizon)
            for horizon in HORIZONS_MINUTES
        },
        "long_only": {
            horizon: build_trades(candles, long_signals, horizon)
            for horizon in HORIZONS_MINUTES
        },
        "short_only": {
            horizon: build_trades(candles, short_signals, horizon)
            for horizon in HORIZONS_MINUTES
        },
    }

    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    all_trades = []
    for scope, horizons in trades_by_scope.items():
        for horizon in HORIZONS_MINUTES:
            for trade in horizons[horizon]:
                row = dict(trade)
                row["strategy_scope"] = scope
                all_trades.append(row)
    trades_path = RESEARCH_DIR / "BTCUSDperpA_fixed_horizon_trades.csv"
    report_path = RESEARCH_DIR / "BTCUSDperpA_fixed_horizon_report.md"
    write_trades(trades_path, all_trades)
    write_report(
        report_path,
        trades_by_scope["all"],
        trades_by_scope["long_only"],
        trades_by_scope["short_only"],
    )

    for horizon in HORIZONS_MINUTES:
        trades = trades_by_scope["all"][horizon]
        zero_cost = metrics(trades, 0)
        five_bps = metrics(trades, 5)
        long_five_bps = metrics(trades_by_scope["long_only"][horizon], 5)
        short_five_bps = metrics(trades_by_scope["short_only"][horizon], 5)
        print(
            "{}m: {} trades, gross {:+.2%}, at 5 bps {:+.2%}, drawdown {:+.2%}".format(
                horizon,
                zero_cost["count"],
                zero_cost["compounded"],
                five_bps["compounded"],
                five_bps["max_drawdown"],
            )
        )
        print(
            "  at 5 bps: longs {:+.2%}, shorts {:+.2%}".format(
                long_five_bps["compounded"], short_five_bps["compounded"]
            )
        )
    print("Saved report to", report_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
