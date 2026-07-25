"""Private Telegram notifications for Hermes OS paper observations."""

from typing import Optional

import httpx


class TelegramNotifier:
    def __init__(
        self,
        token: str,
        chat_id: str,
        proxy_url: Optional[str] = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not token or not chat_id:
            raise ValueError("Telegram token and chat ID are required")
        self._url = "https://api.telegram.org/bot{}/sendMessage".format(token)
        self._chat_id = chat_id
        self._proxy_url = proxy_url
        self._timeout_seconds = timeout_seconds

    def send(self, text: str) -> None:
        with httpx.Client(
            proxy=self._proxy_url,
            timeout=self._timeout_seconds,
        ) as client:
            response = client.post(
                self._url,
                json={"chat_id": self._chat_id, "text": text},
            )
            response.raise_for_status()
            body = response.json()
            if not body.get("ok"):
                raise RuntimeError("Telegram rejected the message")
