"""Read-only access to candles and order-book quotes from T-Bank Invest API."""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
from urllib.request import Request, urlopen

from core.models import Candle


API_ROOT = "https://invest-public-api.tinkoff.ru/rest/"
CANDLES_API_URL = (
    API_ROOT + "tinkoff.public.invest.api.contract.v1.MarketDataService/GetCandles"
)
ORDER_BOOK_API_URL = (
    API_ROOT + "tinkoff.public.invest.api.contract.v1.MarketDataService/GetOrderBook"
)


@dataclass(frozen=True)
class OrderBookSnapshot:
    best_bid: Optional[float]
    best_ask: Optional[float]

    @property
    def midpoint(self) -> Optional[float]:
        if self.best_bid is None or self.best_ask is None:
            return None
        return (self.best_bid + self.best_ask) / 2

    @property
    def spread_fraction(self) -> Optional[float]:
        midpoint = self.midpoint
        if midpoint is None or midpoint <= 0:
            return None
        return (self.best_ask - self.best_bid) / midpoint


def quotation_to_float(value: Dict[str, object]) -> float:
    return float(value.get("units", 0)) + float(value.get("nano", 0)) / 1_000_000_000


class TBankMarketDataClient:
    """Minimal read-only client. It has no methods for placing orders."""

    def __init__(self, token: str) -> None:
        if not token:
            raise ValueError("T-Bank API token is required")
        self._token = token

    def _post(self, url: str, payload: Dict[str, object]) -> Dict[str, object]:
        request = Request(
            url,
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
            return json.loads(response.read().decode("utf-8"))

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
        body = self._post(CANDLES_API_URL, payload)

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

    def get_order_book(self, instrument_id: str, depth: int = 1) -> OrderBookSnapshot:
        """Return the current best bid and ask without placing any orders."""
        body = self._post(
            ORDER_BOOK_API_URL,
            {"instrumentId": instrument_id, "depth": depth},
        )
        bids = body.get("bids", [])
        asks = body.get("asks", [])
        return OrderBookSnapshot(
            best_bid=quotation_to_float(bids[0]["price"]) if bids else None,
            best_ask=quotation_to_float(asks[0]["price"]) if asks else None,
        )
