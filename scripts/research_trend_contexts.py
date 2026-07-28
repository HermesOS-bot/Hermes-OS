#!/usr/bin/env python3
"""Second controlled trend-entry study: hourly context definitions.

The entry trigger is frozen to the closest stage-one candidate:
- RSI recross through 50;
- Moscow session direction agrees;
- price is on the matching side of session VWAP;
- relative volume is at least 1x;
- no previous-candle breakout requirement.

Only the hourly trend definition changes. P1 and P2 are used for development;
P3 is opened once only for variants that pass the pre-registered criteria.
Exit logic remains frozen to T1. Research-only; no order placement.
"""

import csv
import sys
from datetime import timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from core.indicators import ema, relative_volume, rsi  # noqa: E402
from backtest_exit_rules import (  # noqa: E402
    DATA_DIR,
    RESEARCH_DIR,
    load_candles,
    metrics,
    session_open_series,
    session_vwap_series,
    simulate_trades,
)
from research_trend_entries import (  # noqa: E402
    COST_BPS,
    MAX_DEVELOPMENT_DRAWDOWN,
    MIN_DEVELOPMENT_TRADES,
    build_variant_signals,
    combine_metrics,
    passes_development,
    period_boundaries,
    period_signals,
)

CONTEXT_VARIANTS = {
    "ema50_200": {"kind": "ema_cross", "fast": 50, "slow": 200},
    "ema20_50": {"kind": "ema_cross", "fast": 20, "slow": 50},
    "ema10_30": {"kind": "ema_cross", "fast": 10, "slow": 30},
    "ema20_price_slope3": {"kind": "price_slope", "period": 20, "slope_lookback": 3},
    "ema50_price_slope3": {"kind": "price_slope", "period": 50, "slope_lookback": 3},
}


def classify_context(kind, closes, index, **parameters):
    if index < 0:
        return "unknown"
    if kind == "ema_cross":
        fast_values = ema(closes, parameters["fast"])
        slow_values = ema(closes, parameters["slow"])
        fast = fast_values[index]
        slow = slow_values[index]
        if fast is None or slow is None:
            return "unknown"
        if fast > slow:
            return "bullish"
        if fast < slow:
            return "bearish"
        return "flat"
    if kind == "price_slope":
        values = ema(closes, parameters["period"])
        lookback = parameters["slope_lookback"]
        if index < lookback or values[index] is None or values[index - lookback] is None:
            return "unknown"
        if closes[index] > values[index] and values[index] > values[index - lookback]:
            return "bullish"
        if closes[index] < values[index] and values[index] < values[index - lookback]:
            return "bearish"
        return "flat"
    raise ValueError("Unknown context kind: " + kind)


def build_context_series(five_minute, hourly, definition):
    hourly = sorted(hourly, key=lambda candle: candle.timestamp)
    closes = [candle.close for candle in hourly]
    completed_at = [candle.timestamp + timedelta(hours=1) for candle in hourly]
    kind = definition["kind"]

    if kind == "ema_cross":
        fast_values = ema(closes, definition["fast"])
        slow_values = ema(closes, definition["slow"])
    else:
        trend_values = ema(closes, definition["period"])

    result = []
    hourly_index = -1
    for candle in five_minute:
        observed_at = candle.timestamp + timedelta(minutes=5)
        while hourly_index + 1 < len(hourly) and completed_at[hourly_index + 1] <= observed_at:
            hourly_index += 1
        if hourly_index < 0:
            result.append("unknown")
            continue
        if kind == "ema_cross":
            fast = fast_values[hourly_index]
            slow = slow_values[hourly_index]
            if fast is None or slow is None:
                context = "unknown"
            elif fast > slow:
                context = "bullish"
            elif fast < slow:
                context = "bearish"
            else:
                context = "flat"
        else:
            lookback = definition["slope_lookback"]
            current = trend_values[hourly_index]
            previous = trend_values[hourly_index - lookback] if hourly_index >= lookback else None
            if current is None or previous is None:
                context = "unknown"
            elif closes[hourly_index] > current and current > previous:
                context = "bullish"
            elif closes[hourly_index] < current and current < previous:
                context = "bearish"
            else:
                context = "flat"
        result.append(context)
    return result


def write_report(path: Path, rows, boundaries):
    first_boundary, second_boundary = boundaries
    lines = [
        "# Trend hourly-context controlled search",
        "",
        "Research date: 2026-07-27.",
        "",
        "Stage-two study. The RSI/VWAP/session/volume entry trigger and T1 exit were frozen; only the completed-hour trend definition changed.",
        "Selection used P1 and P2 only. P3 was opened once only for variants passing development criteria.",
        "Round-trip spread/slippage assumption: 5 bps.",
        "",
        "Development acceptance criteria:",
        "",
        "- positive compounded result in both P1 and P2;",
        "- at least 50 combined P1+P2 trades;",
        "- combined maximum drawdown no worse than -5%.",
        "",
        "Period boundaries:",
        "",
        "- P1 ends {} UTC;".format(first_boundary.isoformat()),
        "- P2 ends {} UTC;".format(second_boundary.isoformat()),
        "- P3 is the closed control period.",
        "",
        "## Context variants",
        "",
        "- EMA 50/200: original slow context;",
        "- EMA 20/50 and EMA 10/30: faster crossover contexts;",
        "- price versus EMA 20 or EMA 50 plus the EMA slope over three completed hours.",
        "",
        "## Results",
        "",
    ]
    passed = [row for row in rows if row["passed"]]
    lines.append("Variants tested: {}. Passed development criteria: {}.".format(len(rows), len(passed)))
    lines.extend(
        [
            "",
            "| Context | P1 | P2 | Dev trades | Dev result | Dev DD | P3 control | P3 trades | P3 long | P3 short |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in sorted(rows, key=lambda item: item["development"]["compounded"], reverse=True):
        control = row.get("control")
        lines.append(
            "| {name} | {p1:+.2%} | {p2:+.2%} | {trades} | {dev:+.2%} | {dd:+.2%} | {p3} | {p3n} | {p3l} | {p3s} |".format(
                name=row["name"],
                p1=row["period_1"]["compounded"],
                p2=row["period_2"]["compounded"],
                trades=row["development"]["trades"],
                dev=row["development"]["compounded"],
                dd=row["development"]["drawdown"],
                p3="{:+.2%}".format(control["compounded"]) if control else "not opened",
                p3n=control["trades"] if control else "—",
                p3l="{:+.2%}".format(row["control_long"]["compounded"]) if control else "—",
                p3s="{:+.2%}".format(row["control_short"]["compounded"]) if control else "—",
            )
        )
    lines.extend(["", "## Decision", ""])
    if not passed:
        lines.append("No hourly-context variant passed development criteria. P3 remained unopened.")
    else:
        control_positive = [row for row in passed if row["control"]["compounded"] > 0]
        lines.append("Development passes: {}. Positive on P3: {}.".format(len(passed), len(control_positive)))
        for row in passed:
            lines.append(
                "- {}: development {:+.2%}, P3 {:+.2%}.".format(
                    row["name"], row["development"]["compounded"], row["control"]["compounded"]
                )
            )
    lines.extend(["", "This is research, not a trading recommendation."])
    path.write_text("\n".join(lines), encoding="utf-8")


def write_csv(path: Path, rows):
    fields = [
        "context",
        "passed_development",
        "p1_trades",
        "p1_result",
        "p2_trades",
        "p2_result",
        "development_trades",
        "development_result",
        "development_drawdown",
        "p3_trades",
        "p3_result",
        "p3_long_result",
        "p3_short_result",
    ]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            control = row.get("control")
            writer.writerow(
                {
                    "context": row["name"],
                    "passed_development": row["passed"],
                    "p1_trades": row["period_1"]["trades"],
                    "p1_result": "{:.8f}".format(row["period_1"]["compounded"]),
                    "p2_trades": row["period_2"]["trades"],
                    "p2_result": "{:.8f}".format(row["period_2"]["compounded"]),
                    "development_trades": row["development"]["trades"],
                    "development_result": "{:.8f}".format(row["development"]["compounded"]),
                    "development_drawdown": "{:.8f}".format(row["development"]["drawdown"]),
                    "p3_trades": control["trades"] if control else "",
                    "p3_result": "{:.8f}".format(control["compounded"]) if control else "",
                    "p3_long_result": "{:.8f}".format(row["control_long"]["compounded"]) if control else "",
                    "p3_short_result": "{:.8f}".format(row["control_short"]["compounded"]) if control else "",
                }
            )


def main() -> int:
    candles = load_candles(DATA_DIR / "BTCUSDperpA_5min.csv")
    hourly = load_candles(DATA_DIR / "BTCUSDperpA_1hour.csv")
    rsi_values = rsi([candle.close for candle in candles], 14)
    volume_values = relative_volume([candle.volume for candle in candles], 20)
    vwap_values = session_vwap_series(candles)
    session_opens = session_open_series(candles)
    boundaries = period_boundaries(candles)

    rows = []
    for name, definition in CONTEXT_VARIANTS.items():
        contexts = build_context_series(candles, hourly, definition)
        signals = build_variant_signals(
            candles,
            rsi_values,
            vwap_values,
            contexts,
            session_opens,
            volume_values,
            50,
            "none",
            "at_least_1x",
        )
        first_signals, second_signals, control_signals = period_signals(signals, *boundaries)
        first_trades = simulate_trades(candles, first_signals, rsi_values, vwap_values, "T1")
        second_trades = simulate_trades(candles, second_signals, rsi_values, vwap_values, "T1")
        first = combine_metrics(first_trades)
        second = combine_metrics(second_trades)
        development = combine_metrics(first_trades + second_trades)
        passed = passes_development(first, second, development)
        row = {
            "name": name,
            "period_1": first,
            "period_2": second,
            "development": development,
            "passed": passed,
        }
        if passed:
            control_trades = simulate_trades(candles, control_signals, rsi_values, vwap_values, "T1")
            row["control"] = combine_metrics(control_trades)
            row["control_long"] = combine_metrics([trade for trade in control_trades if trade["side"] == "long_candidate"])
            row["control_short"] = combine_metrics([trade for trade in control_trades if trade["side"] == "short_candidate"])
        rows.append(row)

    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    report_path = RESEARCH_DIR / "BTCUSDperpA_trend_context_search.md"
    csv_path = RESEARCH_DIR / "BTCUSDperpA_trend_context_search.csv"
    write_report(report_path, rows, boundaries)
    write_csv(csv_path, rows)

    passed = [row for row in rows if row["passed"]]
    print("Context variants tested:", len(rows))
    print("Passed development criteria:", len(passed))
    for row in sorted(passed, key=lambda item: item["development"]["compounded"], reverse=True):
        print(
            "{}: dev {:+.2%} ({} trades, DD {:+.2%}), P3 {:+.2%} ({} trades)".format(
                row["name"],
                row["development"]["compounded"],
                row["development"]["trades"],
                row["development"]["drawdown"],
                row["control"]["compounded"],
                row["control"]["trades"],
            )
        )
    print("Saved report to", report_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
