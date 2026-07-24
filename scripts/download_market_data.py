#!/usr/bin/env python3
"""Download BTC NEO candles for research on two timeframes.

5-minute candles are intended for entry hypotheses.
Hourly candles are intended for trend and market-context hypotheses.
The script is read-only and cannot place orders.
"""

import csv
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List

REPO_ROOT = Path(__file__).resolve().parents[1]
VAULT_ROOT = Path(__file__).resolve().parents[4]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from core.models import Candle  # noqa: E402
from infrastructure.tbank_market_data import TBankMarketDataClient  # noqa: E402

SECRET_FILE = VAULT_ROOT / ".pi" / "secrets" / "tbank-invest.env"
DATA_DIR = REPO_ROOT / "data" / "market"
BTC_NEO_UID = "4effa274-4e8f-422c-93ff-04aa34fe8e39"


def load_token() -> str:
    token = os.environ.get("TBANK_INVEST_TOKEN", "").strip()
    if token:
        return token
    if not SECRET_FILE.exists():
        return ""
    for raw_line in SECRET_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "TBANK_INVEST_TOKEN":
            return value.strip().strip('"').strip("'")
    return ""


def deduplicate_candles(candles: Iterable[Candle]) -> List[Candle]:
    """Keep one candle per timestamp when adjacent API chunks overlap."""
    by_timestamp = {candle.timestamp: candle for candle in candles}
    return sorted(by_timestamp.values(), key=lambda candle: candle.timestamp)


def validate_candles(candles: Iterable[Candle]) -> List[Candle]:
    result = sorted(candles, key=lambda candle: candle.timestamp)
    timestamps = set()
    for candle in result:
        if candle.timestamp in timestamps:
            raise ValueError("Duplicate candle: {}".format(candle.timestamp.isoformat()))
        timestamps.add(candle.timestamp)
        if candle.low > min(candle.open, candle.close, candle.high):
            raise ValueError("Invalid low at {}".format(candle.timestamp.isoformat()))
        if candle.high < max(candle.open, candle.close, candle.low):
            raise ValueError("Invalid high at {}".format(candle.timestamp.isoformat()))
        if candle.volume < 0:
            raise ValueError("Negative volume at {}".format(candle.timestamp.isoformat()))
    return result


def save_csv(path: Path, candles: Iterable[Candle]) -> int:
    rows = validate_candles(deduplicate_candles(candles))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["timestamp_utc", "open", "high", "low", "close", "volume"])
        for candle in rows:
            writer.writerow(
                [
                    candle.timestamp.isoformat(),
                    candle.open,
                    candle.high,
                    candle.low,
                    candle.close,
                    candle.volume,
                ]
            )
    return len(rows)


def download_in_chunks(
    client: TBankMarketDataClient,
    interval: str,
    from_time: datetime,
    to_time: datetime,
    chunk_size: timedelta,
) -> List[Candle]:
    candles = []
    chunk_start = from_time
    request_count = 0
    while chunk_start < to_time:
        chunk_end = min(chunk_start + chunk_size, to_time)
        candles.extend(
            client.get_candles(
                instrument_id=BTC_NEO_UID,
                interval=interval,
                from_time=chunk_start,
                to_time=chunk_end,
            )
        )
        request_count += 1
        print(interval, "chunk", request_count, "complete")
        chunk_start = chunk_end
    return deduplicate_candles(candles)


def main() -> int:
    token = load_token()
    if not token:
        print("T-Bank token is missing:", SECRET_FILE)
        return 2

    client = TBankMarketDataClient(token)
    now = datetime.now(timezone.utc)
    datasets = [
        (
            "BTCUSDperpA_5min.csv",
            "CANDLE_INTERVAL_5_MIN",
            now - timedelta(days=89),
            timedelta(days=7),
        ),
        (
            "BTCUSDperpA_1hour.csv",
            "CANDLE_INTERVAL_HOUR",
            now - timedelta(days=89),
            timedelta(days=89),
        ),
    ]

    for filename, interval, from_time, chunk_size in datasets:
        candles = download_in_chunks(
            client=client,
            interval=interval,
            from_time=from_time,
            to_time=now,
            chunk_size=chunk_size,
        )
        count = save_csv(DATA_DIR / filename, candles)
        print(filename, count, "complete candles")

    print("Saved to", DATA_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
