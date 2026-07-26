"""Shadow trend-continuation candidates for forward research only.

The detector records one pre-registered hypothesis and never places orders or
sends trading recommendations. A candidate requires alignment between the
hourly context, the current Moscow session, VWAP, an RSI-50 recross and price
confirmation beyond the previous five-minute candle.
"""

from datetime import timedelta
from typing import List, Optional

from core.indicators import relative_volume, rsi
from core.models import Candle
from core.paper_observer import (
    MOSCOW,
    PaperSignal,
    _hourly_context,
    _session_context,
    hypothetical_entry,
    stop_price,
)


def _continuation_side(
    previous_rsi: Optional[float],
    current_rsi: Optional[float],
    hourly_context: str,
    session_return: float,
    current_close: float,
    session_vwap: Optional[float],
    previous_candle: Candle,
) -> Optional[str]:
    if previous_rsi is None or current_rsi is None or session_vwap is None:
        return None
    if (
        hourly_context == "bullish"
        and session_return > 0
        and current_close > session_vwap
        and previous_rsi <= 50 < current_rsi
        and current_close > previous_candle.high
    ):
        return "long_candidate"
    if (
        hourly_context == "bearish"
        and session_return < 0
        and current_close < session_vwap
        and previous_rsi >= 50 > current_rsi
        and current_close < previous_candle.low
    ):
        return "short_candidate"
    return None


def format_trend_message(
    signal: PaperSignal, best_bid: float, best_ask: float
) -> str:
    is_long = signal.side == "long_candidate"
    title = "🟢 ТРЕНДОВЫЙ ЛОНГ" if is_long else "🔴 ТРЕНДОВЫЙ ШОРТ"
    context = "восходящий" if is_long else "нисходящий"
    midpoint = (best_bid + best_ask) / 2
    spread = (best_ask - best_bid) / midpoint if midpoint else 0.0
    entry = hypothetical_entry(signal, best_bid, best_ask)
    stop = stop_price(signal, entry)
    time_moscow = signal.observed_at.astimezone(MOSCOW).strftime(
        "%d.%m.%Y %H:%M мск"
    )
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
    volume = (
        "нет данных"
        if signal.relative_volume_20 is None
        else "{:.2f}× среднего".format(signal.relative_volume_20)
    )
    return "\n".join(
        [
            title + " — NEO Bitcoin",
            "",
            "Время: " + time_moscow,
            "Логика: продолжение движения после локального отката",
            "RSI 14: {:.1f}".format(signal.rsi_14),
            "Часовой контекст: " + context,
            "Сессия от открытия: {:+.2%}".format(signal.session_return),
            "Положение в диапазоне: " + range_position,
            "Цена относительно VWAP: " + vwap_distance,
            "Относительный объём: " + volume,
            "Bid / Ask: {:,.2f} / {:,.2f}".format(best_bid, best_ask),
            "Спред: {:.3%}".format(spread),
            "Условный вход: {:,.2f}".format(entry),
            "Стоп-сценарий 1%: {:,.2f}".format(stop),
            "",
            "Трендовая paper-гипотеза. Реальная сделка не открыта.",
        ]
    )


def detect_latest_trend_candidate(
    five_minute: List[Candle], hourly: List[Candle]
) -> Optional[PaperSignal]:
    """Return a shadow candidate only for the latest completed 5-minute candle."""
    candles = sorted(five_minute, key=lambda item: item.timestamp)
    if len(candles) < 22:
        return None
    rsi_values = rsi([candle.close for candle in candles], 14)
    volumes = relative_volume([candle.volume for candle in candles], 20)
    candle = candles[-1]
    previous = candles[-2]
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
    side = _continuation_side(
        rsi_values[-2],
        rsi_values[-1],
        context,
        session_return,
        candle.close,
        session_vwap,
        previous,
    )
    if side is None:
        return None
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
