"""Transparent technical indicators implemented without external dependencies."""

from typing import Iterable, List, Optional, Tuple


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


def directional_movement(
    highs: Iterable[float],
    lows: Iterable[float],
    closes: Iterable[float],
    period: int = 14,
) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    """Return Wilder's +DI, -DI and ADX series."""
    high_data = list(highs)
    low_data = list(lows)
    close_data = list(closes)
    if period <= 0:
        raise ValueError("DMI period must be positive")
    if not (len(high_data) == len(low_data) == len(close_data)):
        raise ValueError("High, low and close series must have equal length")
    size = len(close_data)
    plus_di: List[Optional[float]] = [None] * size
    minus_di: List[Optional[float]] = [None] * size
    adx: List[Optional[float]] = [None] * size
    if size <= period * 2:
        return plus_di, minus_di, adx

    true_ranges = [0.0] * size
    plus_dm = [0.0] * size
    minus_dm = [0.0] * size
    for index in range(1, size):
        up_move = high_data[index] - high_data[index - 1]
        down_move = low_data[index - 1] - low_data[index]
        plus_dm[index] = up_move if up_move > down_move and up_move > 0 else 0.0
        minus_dm[index] = down_move if down_move > up_move and down_move > 0 else 0.0
        true_ranges[index] = max(
            high_data[index] - low_data[index],
            abs(high_data[index] - close_data[index - 1]),
            abs(low_data[index] - close_data[index - 1]),
        )

    smoothed_tr = sum(true_ranges[1 : period + 1])
    smoothed_plus = sum(plus_dm[1 : period + 1])
    smoothed_minus = sum(minus_dm[1 : period + 1])
    dx: List[Optional[float]] = [None] * size
    for index in range(period, size):
        if index > period:
            smoothed_tr = smoothed_tr - smoothed_tr / period + true_ranges[index]
            smoothed_plus = smoothed_plus - smoothed_plus / period + plus_dm[index]
            smoothed_minus = smoothed_minus - smoothed_minus / period + minus_dm[index]
        if smoothed_tr <= 0:
            continue
        plus_di[index] = 100 * smoothed_plus / smoothed_tr
        minus_di[index] = 100 * smoothed_minus / smoothed_tr
        denominator = plus_di[index] + minus_di[index]
        dx[index] = (
            100 * abs(plus_di[index] - minus_di[index]) / denominator
            if denominator > 0
            else 0.0
        )

    first_adx_index = period * 2 - 1
    initial_dx = [
        value for value in dx[period : first_adx_index + 1] if value is not None
    ]
    if len(initial_dx) == period:
        current_adx = sum(initial_dx) / period
        adx[first_adx_index] = current_adx
        for index in range(first_adx_index + 1, size):
            if dx[index] is None:
                continue
            current_adx = (current_adx * (period - 1) + dx[index]) / period
            adx[index] = current_adx
    return plus_di, minus_di, adx


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
