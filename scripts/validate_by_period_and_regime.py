#!/usr/bin/env python3
"""Validate the locked 60-minute RSI strategy across time and market regimes.

Locked assumptions:
- RSI crossings at 25/75;
- next 5-minute candle open for entry;
- 60-minute holding period;
- 5 basis points round-trip spread/slippage;
- no positions crossing 00:00 Moscow time.

The script keeps longs and shorts and reports them separately in bullish and
bearish hourly EMA50/EMA200 regimes. It does not place orders.
"""

import csv
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from backtest_fixed_horizons import (  # noqa: E402
    build_trades,
    load_candles,
    load_signals,
    metrics,
)

DATA_DIR = REPO_ROOT / "data" / "market"
RESEARCH_DIR = REPO_ROOT / "data" / "research"
HORIZON_MINUTES = 60
ROUND_TRIP_COST_BPS = 5


def split_periods(start: datetime, end: datetime, count: int = 3) -> List[Tuple[datetime, datetime]]:
    if count <= 0:
        raise ValueError("Period count must be positive")
    step = (end - start) / count
    periods = []
    for index in range(count):
        period_start = start + step * index
        period_end = end if index == count - 1 else start + step * (index + 1)
        periods.append((period_start, period_end))
    return periods


def signal_time(signal: Dict[str, str]) -> datetime:
    return datetime.fromisoformat(signal["timestamp_utc"])


def in_period(signal: Dict[str, str], start: datetime, end: datetime, is_last: bool) -> bool:
    timestamp = signal_time(signal)
    return start <= timestamp <= end if is_last else start <= timestamp < end


def filter_signals(
    signals: List[Dict[str, str]],
    start: datetime,
    end: datetime,
    is_last: bool,
    side: str = None,
    trend: str = None,
) -> List[Dict[str, str]]:
    result = []
    for signal in signals:
        if not in_period(signal, start, end, is_last):
            continue
        if side is not None and signal["side"] != side:
            continue
        if trend is not None and signal["hourly_trend"] != trend:
            continue
        result.append(signal)
    return result


def group_definitions():
    return [
        ("all", None, None),
        ("long_all_regimes", "long_candidate", None),
        ("short_all_regimes", "short_candidate", None),
        ("long_bullish", "long_candidate", "bullish"),
        ("long_bearish", "long_candidate", "bearish"),
        ("short_bullish", "short_candidate", "bullish"),
        ("short_bearish", "short_candidate", "bearish"),
    ]


def evaluate(
    candles: List[Dict[str, object]],
    signals: List[Dict[str, str]],
    periods: List[Tuple[datetime, datetime]],
):
    rows = []
    for period_index, (start, end) in enumerate(periods, 1):
        for group, side, trend in group_definitions():
            selected = filter_signals(
                signals,
                start,
                end,
                period_index == len(periods),
                side=side,
                trend=trend,
            )
            trades = build_trades(candles, selected, HORIZON_MINUTES)
            result = metrics(trades, ROUND_TRIP_COST_BPS)
            rows.append(
                {
                    "period": period_index,
                    "period_start_utc": start.isoformat(),
                    "period_end_utc": end.isoformat(),
                    "group": group,
                    "signals": len(selected),
                    "trades": int(result["count"]),
                    "win_rate": result["win_rate"],
                    "mean_return": result["mean"],
                    "median_return": result["median"],
                    "compounded_return": result["compounded"],
                    "max_drawdown": result["max_drawdown"],
                }
            )
    return rows


def write_csv(path: Path, rows: List[Dict[str, object]]) -> None:
    fields = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            output = dict(row)
            for field in (
                "win_rate",
                "mean_return",
                "median_return",
                "compounded_return",
                "max_drawdown",
            ):
                output[field] = "{:.8f}".format(output[field])
            writer.writerow(output)


def write_report(path: Path, rows: List[Dict[str, object]]) -> None:
    labels = {
        "all": "All signals",
        "long_all_regimes": "Longs — all regimes",
        "short_all_regimes": "Shorts — all regimes",
        "long_bullish": "Longs in bullish regime",
        "long_bearish": "Longs in bearish regime",
        "short_bullish": "Shorts in bullish regime",
        "short_bearish": "Shorts in bearish regime",
    }
    lines = [
        "# BTCUSDperpA period and regime validation",
        "",
        "Locked before this test: 60-minute exit and 5 bps round-trip costs.",
        "Market regime: last completed hourly EMA50 compared with EMA200.",
        "Each group is evaluated independently with one position at a time.",
        "",
        "This is research, not a recommendation or evidence of future returns.",
        "",
    ]
    for period in sorted({row["period"] for row in rows}):
        period_rows = [row for row in rows if row["period"] == period]
        first = period_rows[0]
        lines.extend(
            [
                "## Period {}".format(period),
                "",
                "{} — {} UTC".format(
                    first["period_start_utc"][:10], first["period_end_utc"][:10]
                ),
                "",
                "| Group | Signals | Trades | Win rate | Mean | Median | Compounded | Max drawdown |",
                "|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for row in period_rows:
            lines.append(
                "| {} | {} | {} | {:.1%} | {:+.3%} | {:+.3%} | {:+.2%} | {:+.2%} |".format(
                    labels[row["group"]],
                    row["signals"],
                    row["trades"],
                    row["win_rate"],
                    row["mean_return"],
                    row["median_return"],
                    row["compounded_return"],
                    row["max_drawdown"],
                )
            )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    candles = load_candles(DATA_DIR / "BTCUSDperpA_5min.csv")
    signals = load_signals(RESEARCH_DIR / "BTCUSDperpA_signal_observations.csv")
    periods = split_periods(candles[0]["timestamp"], candles[-1]["timestamp"], 3)
    rows = evaluate(candles, signals, periods)

    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = RESEARCH_DIR / "BTCUSDperpA_period_regime_validation.csv"
    report_path = RESEARCH_DIR / "BTCUSDperpA_period_regime_validation.md"
    write_csv(csv_path, rows)
    write_report(report_path, rows)

    for row in rows:
        if row["group"] in ("long_all_regimes", "short_all_regimes"):
            print(
                "Period {} {}: {} trades, win {:.1%}, result {:+.2%}".format(
                    row["period"],
                    row["group"],
                    row["trades"],
                    row["win_rate"],
                    row["compounded_return"],
                )
            )
    print("Saved report to", report_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
