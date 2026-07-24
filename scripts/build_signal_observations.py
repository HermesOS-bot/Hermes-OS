#!/usr/bin/env python3
"""Build research observations from 5-minute and hourly candles.

This script does not recommend or execute trades. It records where the initial
RSI hypothesis triggered and adds hourly trend and relative-volume context.
"""

import csv
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from core.indicators import ema, relative_volume, rsi  # noqa: E402
from core.models import Candle  # noqa: E402

DATA_DIR = REPO_ROOT / "data" / "market"
OUTPUT_DIR = REPO_ROOT / "data" / "research"


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


def format_number(value: Optional[float]) -> str:
    return "" if value is None else "{:.8f}".format(value)


def main() -> int:
    five_minute = load_csv(DATA_DIR / "BTCUSDperpA_5min.csv")
    hourly = load_csv(DATA_DIR / "BTCUSDperpA_1hour.csv")

    five_minute_rsi = rsi([candle.close for candle in five_minute], 14)
    five_minute_volume = relative_volume([candle.volume for candle in five_minute], 20)
    hourly_context = build_hourly_context(hourly)

    observations = []
    context_index = 0
    for index, candle in enumerate(five_minute):
        rsi_value = five_minute_rsi[index]
        if rsi_value is None:
            continue
        if rsi_value < 25:
            side = "long_candidate"
        elif rsi_value > 75:
            side = "short_candidate"
        else:
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
        observations.append(
            {
                "timestamp_utc": candle.timestamp.isoformat(),
                "side": side,
                "close": candle.close,
                "rsi_14": rsi_value,
                "relative_volume_20": five_minute_volume[index],
                "hourly_candle_utc": context["candle_time"].isoformat()
                if context
                else "",
                "ema_50_hourly": context["ema_50"] if context else None,
                "ema_200_hourly": context["ema_200"] if context else None,
                "hourly_trend": trend,
                "trend_supports_signal": supports_signal,
            }
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / "BTCUSDperpA_signal_observations.csv"
    fields = [
        "timestamp_utc",
        "side",
        "close",
        "rsi_14",
        "relative_volume_20",
        "hourly_candle_utc",
        "ema_50_hourly",
        "ema_200_hourly",
        "hourly_trend",
        "trend_supports_signal",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for observation in observations:
            row = dict(observation)
            for field in ("rsi_14", "relative_volume_20", "ema_50_hourly", "ema_200_hourly"):
                row[field] = format_number(row[field])
            writer.writerow(row)

    long_count = sum(item["side"] == "long_candidate" for item in observations)
    short_count = sum(item["side"] == "short_candidate" for item in observations)
    supported_count = sum(item["trend_supports_signal"] for item in observations)
    print("Observations:", len(observations))
    print("Long candidates:", long_count)
    print("Short candidates:", short_count)
    print("Supported by hourly trend:", supported_count)
    print("Saved to", output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
