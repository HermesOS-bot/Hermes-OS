"""Read-only access to historical candles from T-Bank Invest API."""

import json
from datetime import datetime
from typing import Dict, List
from urllib.request import Request, urlopen

from core.models import Candle


API_URL = (
    "https://invest-public-api.tinkoff.ru/rest/"
    "tinkoff.public.invest.api.contract.v1.MarketDataService/GetCandles"
)


def quotation_to_float(value: Dict[str, object]) -> float:
    return float(value.get("units", 0)) + float(value.get("nano", 0)) / 1_000_000_000


class TBankMarketDataClient:
    """Minimal read-only client. It has no methods for placing orders."""

    def __init__(self, token: str) -> None:
        if not token:
            raise ValueError("T-Bank API token is required")
        self._token = token

    def get_candles(
        self,
        instrument_id: str,
        interval: str,
        from_time: datetime,
        to_time: datetime,
        limit: int = 2400,
    ) -> List[Candle]:
        payload = {
            "instrumentId": instrument_id,
            "from": from_time.isoformat().replace("+00:00", "Z"),
            "to": to_time.isoformat().replace("+00:00", "Z"),
            "interval": interval,
            "limit": limit,
        }
        request = Request(
            API_URL,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": "Bearer " + self._token,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "x-app-name": "HermesOS.market-data",
            },
        )
        with urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))

        candles = []
        for item in body.get("candles", []):
            if not item.get("isComplete", False):
                continue
            candles.append(
                Candle(
                    timestamp=datetime.fromisoformat(item["time"].replace("Z", "+00:00")),
                    open=quotation_to_float(item["open"]),
                    high=quotation_to_float(item["high"]),
                    low=quotation_to_float(item["low"]),
                    close=quotation_to_float(item["close"]),
                    volume=float(item.get("volume", 0)),
                )
            )
        return candles
