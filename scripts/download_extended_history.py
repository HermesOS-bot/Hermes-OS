#!/usr/bin/env python3
"""Download a frozen older sample for backward out-of-sample validation.

The range ends before the original April-July 2026 development sample. The
script is read-only and cannot place orders.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "src"))

from download_market_data import (  # noqa: E402
    BTC_NEO_UID,
    DATA_DIR,
    download_in_chunks,
    load_token,
    save_csv,
)
from infrastructure.tbank_market_data import TBankMarketDataClient  # noqa: E402

START = datetime(2025, 7, 24, tzinfo=timezone.utc)
END = datetime(2026, 4, 28, tzinfo=timezone.utc)


def main() -> int:
    token = load_token()
    if not token:
        print("T-Bank token is missing")
        return 2
    client = TBankMarketDataClient(token)
    datasets = (
        (
            "BTCUSDperpA_5min_backward_validation.csv",
            "CANDLE_INTERVAL_5_MIN",
            timedelta(days=7),
        ),
        (
            "BTCUSDperpA_1hour_backward_validation.csv",
            "CANDLE_INTERVAL_HOUR",
            timedelta(days=89),
        ),
    )
    for filename, interval, chunk_size in datasets:
        candles = download_in_chunks(client, interval, START, END, chunk_size)
        count = save_csv(DATA_DIR / filename, candles)
        print(filename, count, "complete candles")
    return 0


if __name__ == "__main__":
    sys.exit(main())
