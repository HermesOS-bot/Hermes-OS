#!/usr/bin/env python3
"""Test T-Bank Invest API access and inspect the BTC-linked NEO future.

The token is read from .pi/secrets/tbank-invest.env and is never printed.
This script is read-only: it can find instruments and request candles, but it
contains no order-placement code.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_ROOT = "https://invest-public-api.tinkoff.ru/rest/tinkoff.public.invest.api.contract.v1"
INSTRUMENTS_URL = API_ROOT + ".InstrumentsService/FindInstrument"
CANDLES_URL = API_ROOT + ".MarketDataService/GetCandles"
SECRET_FILE = Path(__file__).resolve().parents[4] / ".pi" / "secrets" / "tbank-invest.env"


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


def post_json(url: str, token: str, payload: dict) -> dict:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-app-name": "HermesOS.connectivity-test",
        },
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def quotation_to_float(value):
    if not value:
        return None
    return float(value.get("units", 0)) + float(value.get("nano", 0)) / 1_000_000_000


def candle_summary(candle: dict) -> dict:
    return {
        "time": candle.get("time"),
        "open": quotation_to_float(candle.get("open")),
        "high": quotation_to_float(candle.get("high")),
        "low": quotation_to_float(candle.get("low")),
        "close": quotation_to_float(candle.get("close")),
        "volume": candle.get("volume"),
        "isComplete": candle.get("isComplete"),
    }


def main() -> int:
    token = load_token()
    if not token:
        print("TOKEN_MISSING")
        print("Add TBANK_INVEST_TOKEN to:", SECRET_FILE)
        return 2

    try:
        instruments_payload = post_json(
            INSTRUMENTS_URL,
            token,
            {
                "query": "NEO",
                "instrumentKind": "INSTRUMENT_TYPE_FUTURES",
                "apiTradeAvailableFlag": False,
            },
        )

        instruments = instruments_payload.get("instruments", [])
        bitcoin = next(
            (
                item
                for item in instruments
                if item.get("ticker") == "BTCUSDperpA" or item.get("name") == "Neo Bitcoin"
            ),
            None,
        )
        if bitcoin is None:
            print("API_CONNECTION_OK")
            print("NEO_FUTURES_FOUND", len(instruments))
            print("BTC_NEO_NOT_FOUND")
            return 1

        now = datetime.now(timezone.utc)
        candles_payload = post_json(
            CANDLES_URL,
            token,
            {
                "instrumentId": bitcoin["uid"],
                "from": (now - timedelta(hours=24)).isoformat().replace("+00:00", "Z"),
                "to": now.isoformat().replace("+00:00", "Z"),
                "interval": "CANDLE_INTERVAL_5_MIN",
            },
        )
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        print("API_ERROR", exc.code)
        print(details[:1000])
        return 1
    except (URLError, TimeoutError) as exc:
        print("CONNECTION_ERROR", str(exc))
        return 1

    candles = candles_payload.get("candles", [])
    print("API_CONNECTION_OK")
    print("NEO_FUTURES_FOUND", len(instruments))
    print(
        "SELECTED_INSTRUMENT",
        json.dumps(
            {
                "ticker": bitcoin.get("ticker"),
                "name": bitcoin.get("name"),
                "uid": bitcoin.get("uid"),
                "figi": bitcoin.get("figi"),
                "apiTradeAvailableFlag": bitcoin.get("apiTradeAvailableFlag"),
            },
            ensure_ascii=False,
        ),
    )
    print("FIVE_MINUTE_CANDLES_24H", len(candles))
    if candles:
        print("FIRST_CANDLE", json.dumps(candle_summary(candles[0]), ensure_ascii=False))
        print("LAST_CANDLE", json.dumps(candle_summary(candles[-1]), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
