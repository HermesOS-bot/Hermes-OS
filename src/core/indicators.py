"""Transparent technical indicators implemented without external dependencies."""

from typing import Iterable, List, Optional


def ema(values: Iterable[float], period: int) -> List[Optional[float]]:
    """Return an EMA seeded with the first period's simple average."""
    data = list(values)
    if period <= 0:
        raise ValueError("EMA period must be positive")
    result: List[Optional[float]] = [None] * len(data)
    if len(data) < period:
        return result

    current = sum(data[:period]) / period
    result[period - 1] = current
    multiplier = 2 / (period + 1)
    for index in range(period, len(data)):
        current = (data[index] - current) * multiplier + current
        result[index] = current
    return result


def rsi(values: Iterable[float], period: int = 14) -> List[Optional[float]]:
    """Return Wilder's RSI for a series of closing prices."""
    data = list(values)
    if period <= 0:
        raise ValueError("RSI period must be positive")
    result: List[Optional[float]] = [None] * len(data)
    if len(data) <= period:
        return result

    changes = [data[index] - data[index - 1] for index in range(1, len(data))]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]
    average_gain = sum(gains[:period]) / period
    average_loss = sum(losses[:period]) / period

    def value(gain: float, loss: float) -> float:
        if gain == 0 and loss == 0:
            return 50.0
        if loss == 0:
            return 100.0
        if gain == 0:
            return 0.0
        relative_strength = gain / loss
        return 100 - 100 / (1 + relative_strength)

    result[period] = value(average_gain, average_loss)
    for index in range(period + 1, len(data)):
        change_index = index - 1
        average_gain = (
            average_gain * (period - 1) + gains[change_index]
        ) / period
        average_loss = (
            average_loss * (period - 1) + losses[change_index]
        ) / period
        result[index] = value(average_gain, average_loss)
    return result


def relative_volume(
    volumes: Iterable[float], period: int = 20
) -> List[Optional[float]]:
    """Current volume divided by the average of previous candles.

    The current candle is excluded from the average to avoid look-ahead leakage.
    """
    data = list(volumes)
    if period <= 0:
        raise ValueError("Volume period must be positive")
    result: List[Optional[float]] = [None] * len(data)
    for index in range(period, len(data)):
        baseline = sum(data[index - period : index]) / period
        result[index] = data[index] / baseline if baseline > 0 else None
    return result
