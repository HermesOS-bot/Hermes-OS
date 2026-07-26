"""Outcome calculations for recorded paper signals.

Fixed horizons remain independent from the 1% stop scenario. The module uses
completed five-minute candles only and never places orders.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

from core.models import Candle

MOSCOW = ZoneInfo("Europe/Moscow")
HORIZONS_MINUTES = (15, 30, 60, 120, 240)


@dataclass(frozen=True)
class TrackedPaperSignal:
    key: str
    observed_at: datetime
    side: str
    entry_price: float
    best_bid: float
    best_ask: float
    stop_price: float

    @property
    def spread_fraction(self) -> float:
        midpoint = (self.best_bid + self.best_ask) / 2
        if midpoint <= 0:
            return 0.0
        return (self.best_ask - self.best_bid) / midpoint


@dataclass(frozen=True)
class HorizonOutcome:
    horizon_minutes: int
    target_time: datetime
    candle_time: Optional[datetime]
    reference_close: Optional[float]
    estimated_exit_price: Optional[float]
    directional_return: Optional[float]
    crosses_moscow_midnight: bool


@dataclass(frozen=True)
class PathOutcome:
    stop_hit: bool
    stop_hit_time: Optional[datetime]
    max_favorable_return: Optional[float]
    max_adverse_return: Optional[float]
    horizons: Dict[int, HorizonOutcome]


def directional_return(side: str, entry_price: float, exit_price: float) -> float:
    raw = exit_price / entry_price - 1
    return raw if side == "long_candidate" else -raw


def estimated_exit_price(
    signal: TrackedPaperSignal, reference_close: float
) -> float:
    """Estimate an executable exit using half of the entry-time spread.

    Live order-book snapshots will replace this estimate when available. This
    fallback is explicit and avoids treating a candle close as executable.
    """
    half_spread = signal.spread_fraction / 2
    if signal.side == "long_candidate":
        return reference_close * (1 - half_spread)
    return reference_close * (1 + half_spread)


def crosses_moscow_midnight(start: datetime, end: datetime) -> bool:
    return start.astimezone(MOSCOW).date() != end.astimezone(MOSCOW).date()


def _completed_after_entry(
    candles: Iterable[Candle], observed_at: datetime, until: datetime
) -> List[Candle]:
    return sorted(
        [
            candle
            for candle in candles
            if candle.timestamp >= observed_at
            and candle.timestamp + timedelta(minutes=5) <= until
        ],
        key=lambda candle: candle.timestamp,
    )


def _format_horizon(outcome: HorizonOutcome) -> str:
    if outcome.crosses_moscow_midnight:
        return "{} мин: исключено — переход через 00:00 мск".format(
            outcome.horizon_minutes
        )
    if outcome.directional_return is None:
        return "{} мин: данных пока нет".format(outcome.horizon_minutes)
    return "{} мин: {:+.2%}".format(
        outcome.horizon_minutes, outcome.directional_return
    )


def format_outcome_message(
    signal: TrackedPaperSignal,
    outcome: PathOutcome,
    final: bool,
    strategy: str = "rsi",
) -> str:
    if strategy == "trend":
        title = (
            "📈 ТРЕНД — ИТОГ ЗА 4 ЧАСА"
            if final
            else "📈 ТРЕНД — РЕЗУЛЬТАТ ЧЕРЕЗ ЧАС"
        )
    else:
        title = "📊 ИТОГ ЗА 4 ЧАСА" if final else "⏱ РЕЗУЛЬТАТ ЧЕРЕЗ ЧАС"
    direction = "лонг" if signal.side == "long_candidate" else "шорт"
    horizons = (120, 240) if final else (15, 30, 60)
    lines = [title + " — NEO Bitcoin", "", "Направление: " + direction]
    lines.extend(_format_horizon(outcome.horizons[minutes]) for minutes in horizons)
    lines.append("")
    if outcome.stop_hit:
        lines.append("Стоп-сценарий 1%: сработал")
    else:
        lines.append("Стоп-сценарий 1%: не сработал")
    if final:
        favorable = outcome.max_favorable_return
        adverse = outcome.max_adverse_return
        lines.extend(
            [
                "Максимум в плюс: "
                + ("нет данных" if favorable is None else "{:+.2%}".format(favorable)),
                "Максимум в минус: "
                + ("нет данных" if adverse is None else "{:+.2%}".format(adverse)),
            ]
        )
    label = (
        "Трендовая paper-гипотеза. Реальной сделки не было."
        if strategy == "trend"
        else "Paper-наблюдение. Реальной сделки не было."
    )
    lines.extend(["", label])
    return "\n".join(lines)


def evaluate_path(
    signal: TrackedPaperSignal,
    candles: Iterable[Candle],
    until: datetime,
) -> PathOutcome:
    path_end = min(until, signal.observed_at + timedelta(minutes=240))
    completed = _completed_after_entry(candles, signal.observed_at, path_end)

    stop_hit_time = None
    favorable: List[float] = []
    adverse: List[float] = []
    for candle in completed:
        if signal.side == "long_candidate":
            favorable.append(candle.high / signal.entry_price - 1)
            adverse.append(candle.low / signal.entry_price - 1)
            touched_stop = candle.low <= signal.stop_price
        else:
            favorable.append(1 - candle.low / signal.entry_price)
            adverse.append(1 - candle.high / signal.entry_price)
            touched_stop = candle.high >= signal.stop_price
        if touched_stop and stop_hit_time is None:
            stop_hit_time = candle.timestamp

    by_completion = {
        candle.timestamp + timedelta(minutes=5): candle for candle in completed
    }
    horizons = {}
    for minutes in HORIZONS_MINUTES:
        target = signal.observed_at + timedelta(minutes=minutes)
        midnight = crosses_moscow_midnight(signal.observed_at, target)
        candle = by_completion.get(target)
        if candle is None or midnight:
            horizons[minutes] = HorizonOutcome(
                minutes, target, None, None, None, None, midnight
            )
            continue
        exit_price = estimated_exit_price(signal, candle.close)
        horizons[minutes] = HorizonOutcome(
            minutes,
            target,
            candle.timestamp,
            candle.close,
            exit_price,
            directional_return(signal.side, signal.entry_price, exit_price),
            False,
        )

    return PathOutcome(
        stop_hit=stop_hit_time is not None,
        stop_hit_time=stop_hit_time,
        max_favorable_return=max(favorable) if favorable else None,
        max_adverse_return=min(adverse) if adverse else None,
        horizons=horizons,
    )
