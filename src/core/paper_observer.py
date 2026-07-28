"""Pure paper-observer logic. This module cannot place orders."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

from core.indicators import ema, relative_volume, rsi
from core.models import Candle

MOSCOW = ZoneInfo("Europe/Moscow")


@dataclass(frozen=True)
class PaperSignal:
    candle_time: datetime
    observed_at: datetime
    side: str
    candle_close: float
    rsi_14: float
    relative_volume_20: Optional[float]
    hourly_context: str
    ema_50_hourly: Optional[float]
    ema_200_hourly: Optional[float]
    session_open: float
    session_high: float
    session_low: float
    session_return: float
    session_range_position: Optional[float]
    session_vwap: Optional[float]
    price_vs_session_vwap: Optional[float]
    adx_14_hourly: Optional[float] = None
    strategy_version: str = ""

    @property
    def key(self) -> str:
        base = "{}:{}".format(self.candle_time.isoformat(), self.side)
        return "{}:{}".format(self.strategy_version, base) if self.strategy_version else base


def _crossing_side(previous: Optional[float], current: Optional[float]) -> Optional[str]:
    if previous is None or current is None:
        return None
    if previous >= 25 and current < 25:
        return "long_candidate"
    if previous <= 75 and current > 75:
        return "short_candidate"
    return None


def _hourly_context(hourly: List[Candle], observed_at: datetime):
    completed = [
        candle
        for candle in hourly
        if candle.timestamp + timedelta(hours=1) <= observed_at
    ]
    if not completed:
        return "unknown", None, None
    closes = [candle.close for candle in completed]
    fast = ema(closes, 50)[-1]
    slow = ema(closes, 200)[-1]
    if fast is None or slow is None:
        context = "unknown"
    elif fast > slow:
        context = "bullish"
    elif fast < slow:
        context = "bearish"
    else:
        context = "flat"
    return context, fast, slow


def _session_context(candles: List[Candle], signal_candle: Candle):
    session_date = signal_candle.timestamp.astimezone(MOSCOW).date()
    session = [
        candle
        for candle in candles
        if candle.timestamp <= signal_candle.timestamp
        and candle.timestamp.astimezone(MOSCOW).date() == session_date
    ]
    session_open = session[0].open
    session_high = max(candle.high for candle in session)
    session_low = min(candle.low for candle in session)
    session_return = signal_candle.close / session_open - 1
    session_range = session_high - session_low
    range_position = (
        (signal_candle.close - session_low) / session_range
        if session_range > 0
        else None
    )
    total_volume = sum(candle.volume for candle in session)
    session_vwap = (
        sum(
            ((candle.high + candle.low + candle.close) / 3) * candle.volume
            for candle in session
        )
        / total_volume
        if total_volume > 0
        else None
    )
    price_vs_vwap = (
        signal_candle.close / session_vwap - 1 if session_vwap else None
    )
    return (
        session_open,
        session_high,
        session_low,
        session_return,
        range_position,
        session_vwap,
        price_vs_vwap,
    )


def detect_latest_signal(
    five_minute: List[Candle], hourly: List[Candle]
) -> Optional[PaperSignal]:
    """Return a signal only if the latest completed 5-minute candle crosses RSI."""
    candles = sorted(five_minute, key=lambda item: item.timestamp)
    if len(candles) < 22:
        return None
    rsi_values = rsi([candle.close for candle in candles], 14)
    volumes = relative_volume([candle.volume for candle in candles], 20)
    side = _crossing_side(rsi_values[-2], rsi_values[-1])
    if side is None:
        return None
    candle = candles[-1]
    observed_at = candle.timestamp + timedelta(minutes=5)
    context, fast, slow = _hourly_context(hourly, observed_at)
    (
        session_open,
        session_high,
        session_low,
        session_return,
        range_position,
        session_vwap,
        price_vs_vwap,
    ) = _session_context(candles, candle)
    return PaperSignal(
        candle_time=candle.timestamp,
        observed_at=observed_at,
        side=side,
        candle_close=candle.close,
        rsi_14=rsi_values[-1],
        relative_volume_20=volumes[-1],
        hourly_context=context,
        ema_50_hourly=fast,
        ema_200_hourly=slow,
        session_open=session_open,
        session_high=session_high,
        session_low=session_low,
        session_return=session_return,
        session_range_position=range_position,
        session_vwap=session_vwap,
        price_vs_session_vwap=price_vs_vwap,
    )


def hypothetical_entry(signal: PaperSignal, best_bid: float, best_ask: float) -> float:
    return best_ask if signal.side == "long_candidate" else best_bid


def stop_price(signal: PaperSignal, entry: float, stop_fraction: float = 0.01) -> float:
    if signal.side == "long_candidate":
        return entry * (1 - stop_fraction)
    return entry * (1 + stop_fraction)


def format_signal_message(
    signal: PaperSignal,
    best_bid: float,
    best_ask: float,
) -> str:
    midpoint = (best_bid + best_ask) / 2
    spread = (best_ask - best_bid) / midpoint if midpoint else 0.0
    entry = hypothetical_entry(signal, best_bid, best_ask)
    stop = stop_price(signal, entry)
    is_long = signal.side == "long_candidate"
    title = (
        "🟢 КРАТКОСРОЧНЫЙ ОТСКОК ВВЕРХ"
        if is_long
        else "🔴 КРАТКОСРОЧНАЯ КОРРЕКЦИЯ ВНИЗ"
    )
    context = {
        "bullish": "восходящий",
        "bearish": "нисходящий",
        "flat": "боковой",
        "unknown": "ещё не определён",
    }.get(signal.hourly_context, signal.hourly_context)
    volume = (
        "нет данных"
        if signal.relative_volume_20 is None
        else "{:.2f}× среднего".format(signal.relative_volume_20)
    )
    time_moscow = signal.observed_at.astimezone(MOSCOW).strftime("%d.%m.%Y %H:%M мск")
    if abs(signal.session_return) < 0.0001:
        alignment = "движение сессии пока нейтральное"
    elif (is_long and signal.session_return > 0) or (
        not is_long and signal.session_return < 0
    ):
        alignment = "по движению сессии"
    else:
        alignment = "против движения сессии"
    range_position = (
        "нет данных"
        if signal.session_range_position is None
        else "{:.0%} от минимума к максимуму".format(
            signal.session_range_position
        )
    )
    vwap_distance = (
        "нет данных"
        if signal.price_vs_session_vwap is None
        else "{:+.2%}".format(signal.price_vs_session_vwap)
    )
    return "\n".join(
        [
            title + " — NEO Bitcoin",
            "",
            "Время: " + time_moscow,
            "RSI 14: {:.1f}".format(signal.rsi_14),
            "Часовой контекст: " + context,
            "Сессия от открытия: {:+.2%}".format(signal.session_return),
            "Положение в диапазоне: " + range_position,
            "Цена относительно VWAP: " + vwap_distance,
            "Сигнал: " + alignment,
            "Относительный объём: " + volume,
            "Bid / Ask: {:,.2f} / {:,.2f}".format(best_bid, best_ask),
            "Спред: {:.3%}".format(spread),
            "Условный вход: {:,.2f}".format(entry),
            "Стоп-сценарий 1%: {:,.2f}".format(stop),
            "",
            "Локальный RSI-сигнал на 15–60 минут, не прогноз разворота дня.",
            "Paper-наблюдение. Реальная сделка не открыта.",
        ]
    )
