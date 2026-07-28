#!/usr/bin/env python3
"""Fourth controlled trend study: strength and trend-quality indicators.

The promising stage-three entry is frozen: EMA-context-compatible Moscow
session, reclaim of session VWAP, RSI state 50, no volume filter, T1 exit.
This study replaces or supplements the hourly EMA direction with ADX/DMI or a
linear-regression trend-quality filter. P3 stays closed unless a variant passes.
"""

import math
import sys
from datetime import timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from core.indicators import ema, rsi  # noqa: E402
from backtest_exit_rules import (  # noqa: E402
    DATA_DIR,
    RESEARCH_DIR,
    load_candles,
    session_open_series,
    session_vwap_series,
    simulate_trades,
)
from research_trend_entries import (  # noqa: E402
    combine_metrics,
    passes_development,
    period_boundaries,
    period_signals,
)
from research_trend_pullbacks import build_signals  # noqa: E402

VARIANTS = (
    "ema50_200_adx15",
    "ema50_200_adx20",
    "ema50_200_adx25",
    "dmi_adx20",
    "regression20_r2_20",
    "regression20_r2_40",
)


def directional_movement(highs, lows, closes, period=14):
    size = len(closes)
    plus_di = [None] * size
    minus_di = [None] * size
    adx = [None] * size
    if size <= period * 2:
        return plus_di, minus_di, adx

    true_ranges = [0.0] * size
    plus_dm = [0.0] * size
    minus_dm = [0.0] * size
    for index in range(1, size):
        up_move = highs[index] - highs[index - 1]
        down_move = lows[index - 1] - lows[index]
        plus_dm[index] = up_move if up_move > down_move and up_move > 0 else 0.0
        minus_dm[index] = down_move if down_move > up_move and down_move > 0 else 0.0
        true_ranges[index] = max(
            highs[index] - lows[index],
            abs(highs[index] - closes[index - 1]),
            abs(lows[index] - closes[index - 1]),
        )

    smoothed_tr = sum(true_ranges[1 : period + 1])
    smoothed_plus = sum(plus_dm[1 : period + 1])
    smoothed_minus = sum(minus_dm[1 : period + 1])
    dx = [None] * size

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
    initial_dx = [value for value in dx[period:first_adx_index + 1] if value is not None]
    if len(initial_dx) == period:
        current_adx = sum(initial_dx) / period
        adx[first_adx_index] = current_adx
        for index in range(first_adx_index + 1, size):
            if dx[index] is None:
                continue
            current_adx = (current_adx * (period - 1) + dx[index]) / period
            adx[index] = current_adx
    return plus_di, minus_di, adx


def regression_stats(values, window=20):
    slopes = [None] * len(values)
    r_squared = [None] * len(values)
    total_moves = [None] * len(values)
    x_mean = (window - 1) / 2
    x_variance = sum((index - x_mean) ** 2 for index in range(window))
    for end in range(window - 1, len(values)):
        data = values[end - window + 1 : end + 1]
        y_mean = sum(data) / window
        covariance = sum(
            (index - x_mean) * (value - y_mean)
            for index, value in enumerate(data)
        )
        slope = covariance / x_variance if x_variance else 0.0
        fitted = [y_mean + slope * (index - x_mean) for index in range(window)]
        total_variance = sum((value - y_mean) ** 2 for value in data)
        residual = sum((value - fit) ** 2 for value, fit in zip(data, fitted))
        slopes[end] = slope
        r_squared[end] = 1 - residual / total_variance if total_variance > 0 else 0.0
        total_moves[end] = abs(slope) * (window - 1) / y_mean if y_mean else 0.0
    return slopes, r_squared, total_moves


def completed_hour_mapping(five_minute, hourly):
    completed_at = [candle.timestamp + timedelta(hours=1) for candle in hourly]
    mapping = []
    hourly_index = -1
    for candle in five_minute:
        observed_at = candle.timestamp + timedelta(minutes=5)
        while hourly_index + 1 < len(hourly) and completed_at[hourly_index + 1] <= observed_at:
            hourly_index += 1
        mapping.append(hourly_index)
    return mapping


def build_context_variants(five_minute, hourly):
    closes = [candle.close for candle in hourly]
    fast = ema(closes, 50)
    slow = ema(closes, 200)
    plus_di, minus_di, adx = directional_movement(
        [candle.high for candle in hourly],
        [candle.low for candle in hourly],
        closes,
        14,
    )
    slopes, r2, total_moves = regression_stats(closes, 20)
    mapping = completed_hour_mapping(five_minute, hourly)
    result = {name: [] for name in VARIANTS}

    for hourly_index in mapping:
        for name in VARIANTS:
            context = "unknown"
            if hourly_index >= 0:
                ema_direction = None
                if fast[hourly_index] is not None and slow[hourly_index] is not None:
                    ema_direction = "bullish" if fast[hourly_index] > slow[hourly_index] else "bearish"
                if name.startswith("ema50_200_adx"):
                    threshold = int(name.rsplit("adx", 1)[1])
                    if ema_direction and adx[hourly_index] is not None and adx[hourly_index] >= threshold:
                        context = ema_direction
                elif name == "dmi_adx20":
                    if adx[hourly_index] is not None and adx[hourly_index] >= 20:
                        if plus_di[hourly_index] > minus_di[hourly_index]:
                            context = "bullish"
                        elif minus_di[hourly_index] > plus_di[hourly_index]:
                            context = "bearish"
                elif name.startswith("regression20"):
                    threshold = 0.2 if name.endswith("20") else 0.4
                    if (
                        slopes[hourly_index] is not None
                        and r2[hourly_index] >= threshold
                        and total_moves[hourly_index] >= 0.005
                    ):
                        context = "bullish" if slopes[hourly_index] > 0 else "bearish"
            result[name].append(context)
    return result


def write_report(path: Path, rows, boundaries):
    lines = [
        "# Trend strength/quality controlled search",
        "",
        "Research date: 2026-07-28.",
        "",
        "The stage-three VWAP-reclaim entry, RSI state 50 and T1 exit were frozen.",
        "Only the completed-hour trend-strength or trend-quality definition changed.",
        "P1/P2 were used for development; P3 stayed closed unless a variant passed.",
        "Costs: 5 bps round trip.",
        "",
        "Acceptance: positive in P1 and P2, at least 50 development trades, drawdown no worse than -5%.",
        "",
        "Period boundaries: P1 ends {}; P2 ends {}; P3 is closed control.".format(
            boundaries[0].isoformat(), boundaries[1].isoformat()
        ),
        "",
        "| Variant | P1 | P2 | Dev trades | Dev result | Dev DD | P3 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in sorted(rows, key=lambda item: item["development"]["compounded"], reverse=True):
        control = row.get("control")
        lines.append(
            "| {name} | {p1:+.2%} | {p2:+.2%} | {n} | {dev:+.2%} | {dd:+.2%} | {p3} |".format(
                name=row["name"],
                p1=row["period_1"]["compounded"],
                p2=row["period_2"]["compounded"],
                n=row["development"]["trades"],
                dev=row["development"]["compounded"],
                dd=row["development"]["drawdown"],
                p3="{:+.2%}".format(control["compounded"]) if control else "not opened",
            )
        )
    passed = [row for row in rows if row["passed"]]
    lines.extend(["", "Passed development criteria: {} of {}.".format(len(passed), len(rows)), ""])
    if not passed:
        lines.append("No variant passed; P3 remained closed.")
    else:
        for row in passed:
            lines.append(
                "- {}: development {:+.2%}, P3 {:+.2%}.".format(
                    row["name"], row["development"]["compounded"], row["control"]["compounded"]
                )
            )
    lines.extend(["", "This is research, not a trading recommendation."])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    candles = load_candles(DATA_DIR / "BTCUSDperpA_5min.csv")
    hourly = load_candles(DATA_DIR / "BTCUSDperpA_1hour.csv")
    rsi_values = rsi([candle.close for candle in candles], 14)
    vwap_values = session_vwap_series(candles)
    session_opens = session_open_series(candles)
    contexts_by_variant = build_context_variants(candles, hourly)
    boundaries = period_boundaries(candles)
    dummy_volume = [None] * len(candles)

    rows = []
    for name, contexts in contexts_by_variant.items():
        signals = build_signals(
            candles,
            rsi_values,
            vwap_values,
            contexts,
            session_opens,
            dummy_volume,
            50,
            "any",
        )
        first_signals, second_signals, control_signals = period_signals(signals, *boundaries)
        first_trades = simulate_trades(candles, first_signals, rsi_values, vwap_values, "T1")
        second_trades = simulate_trades(candles, second_signals, rsi_values, vwap_values, "T1")
        first = combine_metrics(first_trades)
        second = combine_metrics(second_trades)
        development = combine_metrics(first_trades + second_trades)
        passed = passes_development(first, second, development)
        row = {"name": name, "period_1": first, "period_2": second, "development": development, "passed": passed}
        if passed:
            control_trades = simulate_trades(candles, control_signals, rsi_values, vwap_values, "T1")
            row["control"] = combine_metrics(control_trades)
        rows.append(row)

    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    report_path = RESEARCH_DIR / "BTCUSDperpA_trend_strength_search.md"
    write_report(report_path, rows, boundaries)
    passed = [row for row in rows if row["passed"]]
    print("Strength/quality variants tested:", len(rows))
    print("Passed development criteria:", len(passed))
    for row in passed:
        print(row["name"], row["development"], row["control"])
    print("Saved report to", report_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
