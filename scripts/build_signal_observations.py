#!/usr/bin/env python3
"""Research RSI threshold crossings with hourly trend and volume context.

This is an observational report, not a trading backtest. It does not model
execution, commissions, slippage, stops, position sizing or order placement.
"""

import csv
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from core.indicators import ema, relative_volume, rsi  # noqa: E402
from core.models import Candle  # noqa: E402

DATA_DIR = REPO_ROOT / "data" / "market"
OUTPUT_DIR = REPO_ROOT / "data" / "research"
HORIZONS_MINUTES = (15, 30, 60, 240)


def load_csv(path: Path) -> List[Candle]:
    candles = []
    with path.open("r", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            candles.append(
                Candle(
                    timestamp=datetime.fromisoformat(row["timestamp_utc"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
            )
    return sorted(candles, key=lambda candle: candle.timestamp)


def build_hourly_context(hourly: List[Candle]) -> List[Dict[str, object]]:
    closes = [candle.close for candle in hourly]
    ema_50 = ema(closes, 50)
    ema_200 = ema(closes, 200)
    contexts = []
    for index, candle in enumerate(hourly):
        fast = ema_50[index]
        slow = ema_200[index]
        if fast is None or slow is None:
            trend = "unknown"
        elif fast > slow:
            trend = "bullish"
        elif fast < slow:
            trend = "bearish"
        else:
            trend = "flat"
        contexts.append(
            {
                "candle_time": candle.timestamp,
                "completed_at": candle.timestamp + timedelta(hours=1),
                "ema_50": fast,
                "ema_200": slow,
                "trend": trend,
            }
        )
    return contexts


def latest_completed_context(
    contexts: List[Dict[str, object]], timestamp: datetime, start_index: int
):
    index = start_index
    while (
        index + 1 < len(contexts)
        and contexts[index + 1]["completed_at"] <= timestamp
    ):
        index += 1
    if not contexts or contexts[index]["completed_at"] > timestamp:
        return None, index
    return contexts[index], index


def crossing_side(previous_rsi: Optional[float], current_rsi: Optional[float]):
    """Emit one event when RSI enters an extreme zone."""
    if previous_rsi is None or current_rsi is None:
        return None
    if previous_rsi >= 25 and current_rsi < 25:
        return "long_candidate"
    if previous_rsi <= 75 and current_rsi > 75:
        return "short_candidate"
    return None


def directional_return(side: str, entry: float, future: float) -> float:
    raw_return = future / entry - 1
    return raw_return if side == "long_candidate" else -raw_return


def volume_bucket(value: Optional[float]) -> str:
    if value is None:
        return "unknown"
    if value < 1:
        return "<1x"
    if value < 1.5:
        return "1-1.5x"
    if value < 2:
        return "1.5-2x"
    return ">=2x"


def format_number(value: Optional[float]) -> str:
    return "" if value is None else "{:.8f}".format(value)


def build_observations(
    five_minute: List[Candle], hourly: List[Candle]
) -> List[Dict[str, object]]:
    five_minute_rsi = rsi([candle.close for candle in five_minute], 14)
    five_minute_volume = relative_volume([candle.volume for candle in five_minute], 20)
    hourly_context = build_hourly_context(hourly)
    candles_by_time = {candle.timestamp: candle for candle in five_minute}

    observations = []
    context_index = 0
    for index, candle in enumerate(five_minute):
        previous_rsi = five_minute_rsi[index - 1] if index else None
        rsi_value = five_minute_rsi[index]
        side = crossing_side(previous_rsi, rsi_value)
        if side is None:
            continue

        context, context_index = latest_completed_context(
            hourly_context, candle.timestamp, context_index
        )
        trend = context["trend"] if context else "unknown"
        supports_signal = (
            side == "long_candidate" and trend == "bullish"
        ) or (
            side == "short_candidate" and trend == "bearish"
        )
        relative_volume_value = five_minute_volume[index]
        observation = {
            "timestamp_utc": candle.timestamp.isoformat(),
            "side": side,
            "close": candle.close,
            "rsi_14": rsi_value,
            "relative_volume_20": relative_volume_value,
            "volume_bucket": volume_bucket(relative_volume_value),
            "hourly_candle_utc": context["candle_time"].isoformat()
            if context
            else "",
            "ema_50_hourly": context["ema_50"] if context else None,
            "ema_200_hourly": context["ema_200"] if context else None,
            "hourly_trend": trend,
            "trend_supports_signal": supports_signal,
        }

        for minutes in HORIZONS_MINUTES:
            future = candles_by_time.get(candle.timestamp + timedelta(minutes=minutes))
            observation["return_{}m".format(minutes)] = (
                future.close / candle.close - 1 if future else None
            )
            observation["directional_return_{}m".format(minutes)] = (
                directional_return(side, candle.close, future.close) if future else None
            )

        next_four_hours = [
            future
            for future in five_minute[index + 1 : index + 49]
            if future.timestamp <= candle.timestamp + timedelta(hours=4)
        ]
        if next_four_hours:
            if side == "long_candidate":
                observation["max_favorable_4h"] = (
                    max(item.high for item in next_four_hours) / candle.close - 1
                )
                observation["max_adverse_4h"] = (
                    min(item.low for item in next_four_hours) / candle.close - 1
                )
            else:
                observation["max_favorable_4h"] = (
                    candle.close - min(item.low for item in next_four_hours)
                ) / candle.close
                observation["max_adverse_4h"] = (
                    candle.close - max(item.high for item in next_four_hours)
                ) / candle.close
        else:
            observation["max_favorable_4h"] = None
            observation["max_adverse_4h"] = None

        observations.append(observation)
    return observations


def summarize_group(rows: Iterable[Dict[str, object]]) -> List[str]:
    data = list(rows)
    lines = ["- Events: {}".format(len(data))]
    for minutes in HORIZONS_MINUTES:
        field = "directional_return_{}m".format(minutes)
        values = [row[field] for row in data if row.get(field) is not None]
        if not values:
            lines.append("- {} min: no complete observations".format(minutes))
            continue
        positive_rate = sum(value > 0 for value in values) / len(values)
        lines.append(
            "- {} min: median {:+.3%}; positive {:.1%} ({}/{})".format(
                minutes,
                statistics.median(values),
                positive_rate,
                sum(value > 0 for value in values),
                len(values),
            )
        )
    return lines


def write_summary(path: Path, observations: List[Dict[str, object]]) -> None:
    groups = {
        "All threshold crossings": observations,
        "Long candidates": [
            row for row in observations if row["side"] == "long_candidate"
        ],
        "Short candidates": [
            row for row in observations if row["side"] == "short_candidate"
        ],
        "Hourly trend supports direction": [
            row for row in observations if row["trend_supports_signal"]
        ],
        "Hourly trend does not support direction": [
            row for row in observations if not row["trend_supports_signal"]
        ],
    }
    by_volume = defaultdict(list)
    for row in observations:
        by_volume[row["volume_bucket"]].append(row)
    for bucket in ("<1x", "1-1.5x", "1.5-2x", ">=2x", "unknown"):
        if by_volume[bucket]:
            groups["Relative volume {}".format(bucket)] = by_volume[bucket]

    lines = [
        "# BTCUSDperpA RSI crossing observations",
        "",
        "This is exploratory research, not a trading backtest. It excludes fees, slippage, execution rules, stops and position sizing.",
        "",
    ]
    for title, rows in groups.items():
        lines.extend(["## " + title, ""])
        lines.extend(summarize_group(rows))
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    five_minute = load_csv(DATA_DIR / "BTCUSDperpA_5min.csv")
    hourly = load_csv(DATA_DIR / "BTCUSDperpA_1hour.csv")
    observations = build_observations(five_minute, hourly)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / "BTCUSDperpA_signal_observations.csv"
    fields = [
        "timestamp_utc",
        "side",
        "close",
        "rsi_14",
        "relative_volume_20",
        "volume_bucket",
        "hourly_candle_utc",
        "ema_50_hourly",
        "ema_200_hourly",
        "hourly_trend",
        "trend_supports_signal",
    ]
    for minutes in HORIZONS_MINUTES:
        fields.extend(
            ["return_{}m".format(minutes), "directional_return_{}m".format(minutes)]
        )
    fields.extend(["max_favorable_4h", "max_adverse_4h"])

    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for observation in observations:
            row = dict(observation)
            numeric_fields = [
                "rsi_14",
                "relative_volume_20",
                "ema_50_hourly",
                "ema_200_hourly",
                "max_favorable_4h",
                "max_adverse_4h",
            ]
            for minutes in HORIZONS_MINUTES:
                numeric_fields.extend(
                    ["return_{}m".format(minutes), "directional_return_{}m".format(minutes)]
                )
            for field in numeric_fields:
                row[field] = format_number(row.get(field))
            writer.writerow(row)

    summary_path = OUTPUT_DIR / "BTCUSDperpA_signal_summary.md"
    write_summary(summary_path, observations)

    long_count = sum(item["side"] == "long_candidate" for item in observations)
    short_count = sum(item["side"] == "short_candidate" for item in observations)
    print("Distinct RSI crossings:", len(observations))
    print("Long candidates:", long_count)
    print("Short candidates:", short_count)
    print("Saved observations to", output_path)
    print("Saved summary to", summary_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
