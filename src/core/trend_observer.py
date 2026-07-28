"""Shadow trend-continuation candidates for forward research only.

The detector records one pre-registered hypothesis and never places orders or
sends trading recommendations. A candidate requires alignment between the
hourly context, the current Moscow session, VWAP, an RSI-50 recross and price
confirmation beyond the previous five-minute candle.
"""

from datetime import timedelta
from typing import List, Optional

from core.indicators import directional_movement, ema, relative_volume, rsi
from core.models import Candle
from core.paper_observer import (
    MOSCOW,
    PaperSignal,
    _session_context,
    hypothetical_entry,
    stop_price,
)

TREND_STRATEGY_VERSION = "trend-v2-adx25-vwap-reclaim"
ADX_THRESHOLD = 25.0


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


def _hourly_adx_context(hourly: List[Candle], observed_at):
    completed = [
        candle
        for candle in hourly
        if candle.timestamp + timedelta(hours=1) <= observed_at
    ]
    if not completed:
        return "unknown", None, None, None
    closes = [candle.close for candle in completed]
    fast = ema(closes, 50)[-1]
    slow = ema(closes, 200)[-1]
    _, _, adx_values = directional_movement(
        [candle.high for candle in completed],
        [candle.low for candle in completed],
        closes,
        14,
    )
    adx_value = adx_values[-1]
    if fast is None or slow is None:
        context = "unknown"
    elif fast > slow:
        context = "bullish"
    elif fast < slow:
        context = "bearish"
    else:
        context = "flat"
    return context, fast, slow, adx_value


def _v2_reclaim_side(
    rsi_value: Optional[float],
    hourly_context: str,
    hourly_adx: Optional[float],
    session_return: float,
    previous_close: float,
    previous_vwap: Optional[float],
    current_close: float,
    current_vwap: Optional[float],
) -> Optional[str]:
    if (
        rsi_value is None
        or hourly_adx is None
        or hourly_adx < ADX_THRESHOLD
        or previous_vwap is None
        or current_vwap is None
    ):
        return None
    if (
        hourly_context == "bullish"
        and session_return > 0
        and previous_close <= previous_vwap
        and current_close > current_vwap
        and rsi_value >= 50
    ):
        return "long_candidate"
    if (
        hourly_context == "bearish"
        and session_return < 0
        and previous_close >= previous_vwap
        and current_close < current_vwap
        and rsi_value <= 50
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
            title + " V2 — ADX/VWAP — NEO Bitcoin",
            "",
            "Время: " + time_moscow,
            "Логика: возврат через VWAP после отката в сильном часовом тренде",
            "RSI 14: {:.1f}".format(signal.rsi_14),
            "Часовой контекст EMA 50/200: " + context,
            "ADX 14 (1 час): "
            + (
                "нет данных"
                if signal.adx_14_hourly is None
                else "{:.1f}".format(signal.adx_14_hourly)
            ),
            "Сессия от открытия: {:+.2%}".format(signal.session_return),
            "Положение в диапазоне: " + range_position,
            "Цена относительно VWAP: " + vwap_distance,
            "Относительный объём: " + volume,
            "Bid / Ask: {:,.2f} / {:,.2f}".format(best_bid, best_ask),
            "Спред: {:.3%}".format(spread),
            "Условный вход: {:,.2f}".format(entry),
            "Стоп-сценарий 1%: {:,.2f}".format(stop),
            "",
            "Трендовая гипотеза v2 — ADX ≥25 и возврат через VWAP.",
            "Paper-наблюдение. Реальная сделка не открыта.",
        ]
    )


def detect_latest_trend_candidate(
    five_minute: List[Candle], hourly: List[Candle]
) -> Optional[PaperSignal]:
    """Return a trend-v2 candidate for the latest completed five-minute candle."""
    candles = sorted(five_minute, key=lambda item: item.timestamp)
    if len(candles) < 22:
        return None
    rsi_values = rsi([candle.close for candle in candles], 14)
    volumes = relative_volume([candle.volume for candle in candles], 20)
    candle = candles[-1]
    previous = candles[-2]
    if previous.timestamp.astimezone(MOSCOW).date() != candle.timestamp.astimezone(MOSCOW).date():
        return None
    observed_at = candle.timestamp + timedelta(minutes=5)
    context, fast, slow, adx_value = _hourly_adx_context(hourly, observed_at)
    (
        session_open,
        session_high,
        session_low,
        session_return,
        range_position,
        session_vwap,
        price_vs_vwap,
    ) = _session_context(candles, candle)
    previous_vwap = _session_context(candles[:-1], previous)[5]
    side = _v2_reclaim_side(
        rsi_values[-1],
        context,
        adx_value,
        session_return,
        previous.close,
        previous_vwap,
        candle.close,
        session_vwap,
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
        adx_14_hourly=adx_value,
        strategy_version=TREND_STRATEGY_VERSION,
    )
