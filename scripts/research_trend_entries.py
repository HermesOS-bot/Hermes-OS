#!/usr/bin/env python3
"""Controlled search for explainable trend-entry variants.

Selection uses only the first two chronological periods. The final period is
reported only for variants that pass the pre-registered development criteria.
Exit logic is frozen to T1: 1% stop, confirmed RSI/VWAP breakdown, or session
end. This script is research-only and cannot place orders.
"""

import csv
import itertools
import sys
from datetime import timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from core.indicators import relative_volume, rsi  # noqa: E402
from core.paper_observer import MOSCOW  # noqa: E402
from backtest_exit_rules import (  # noqa: E402
    DATA_DIR,
    RESEARCH_DIR,
    hourly_context_series,
    load_candles,
    metrics,
    session_open_series,
    session_vwap_series,
    simulate_trades,
)

RSI_LEVELS = (40, 45, 50)
CONFIRMATIONS = ("breakout", "candle_direction", "none")
VOLUME_FILTERS = ("any", "at_least_1x")
COST_BPS = 5
MIN_DEVELOPMENT_TRADES = 50
MAX_DEVELOPMENT_DRAWDOWN = -0.05


def trend_side(
    index,
    candles,
    rsi_values,
    vwap_values,
    hourly_contexts,
    session_opens,
    volume_values,
    rsi_level,
    confirmation,
    volume_filter,
):
    if index < 1:
        return None
    previous_rsi = rsi_values[index - 1]
    current_rsi = rsi_values[index]
    vwap = vwap_values[index]
    volume = volume_values[index]
    if previous_rsi is None or current_rsi is None or vwap is None:
        return None
    if volume_filter == "at_least_1x" and (volume is None or volume < 1):
        return None

    candle = candles[index]
    previous = candles[index - 1]
    session_return = candle.close / session_opens[index] - 1
    short_level = 100 - rsi_level

    long_base = (
        hourly_contexts[index] == "bullish"
        and session_return > 0
        and candle.close > vwap
        and previous_rsi <= rsi_level < current_rsi
    )
    short_base = (
        hourly_contexts[index] == "bearish"
        and session_return < 0
        and candle.close < vwap
        and previous_rsi >= short_level > current_rsi
    )

    if confirmation == "breakout":
        long_confirmed = candle.close > previous.high
        short_confirmed = candle.close < previous.low
    elif confirmation == "candle_direction":
        long_confirmed = candle.close > candle.open
        short_confirmed = candle.close < candle.open
    elif confirmation == "none":
        long_confirmed = True
        short_confirmed = True
    else:
        raise ValueError("Unknown confirmation: " + confirmation)

    if long_base and long_confirmed:
        return "long_candidate"
    if short_base and short_confirmed:
        return "short_candidate"
    return None


def build_variant_signals(
    candles,
    rsi_values,
    vwap_values,
    hourly_contexts,
    session_opens,
    volume_values,
    rsi_level,
    confirmation,
    volume_filter,
):
    signals = []
    for index in range(1, len(candles)):
        side = trend_side(
            index,
            candles,
            rsi_values,
            vwap_values,
            hourly_contexts,
            session_opens,
            volume_values,
            rsi_level,
            confirmation,
            volume_filter,
        )
        if side is not None:
            signals.append(
                {"index": index, "timestamp": candles[index].timestamp, "side": side}
            )
    return signals


def period_boundaries(candles):
    start = candles[0].timestamp
    end = candles[-1].timestamp + timedelta(minutes=5)
    span = end - start
    return start + span / 3, start + span * 2 / 3


def period_signals(signals, first_boundary, second_boundary):
    return (
        [signal for signal in signals if signal["timestamp"] < first_boundary],
        [
            signal
            for signal in signals
            if first_boundary <= signal["timestamp"] < second_boundary
        ],
        [signal for signal in signals if signal["timestamp"] >= second_boundary],
    )


def combine_metrics(trades, cost_bps=COST_BPS):
    result = metrics(trades, cost_bps)
    return {
        "trades": int(result["count"]),
        "win_rate": result["win_rate"],
        "mean": result["mean"],
        "compounded": result["compounded"],
        "drawdown": result["max_drawdown"],
        "median_hold": result["median_hold"],
    }


def passes_development(first, second, combined):
    return (
        first["compounded"] > 0
        and second["compounded"] > 0
        and combined["trades"] >= MIN_DEVELOPMENT_TRADES
        and combined["drawdown"] >= MAX_DEVELOPMENT_DRAWDOWN
    )


def write_report(path: Path, rows, boundaries) -> None:
    first_boundary, second_boundary = boundaries
    lines = [
        "# Trend-entry controlled search",
        "",
        "Research date: 2026-07-27.",
        "",
        "Selection used only periods P1 and P2. P3 was opened once only for variants that passed the pre-registered development criteria.",
        "Exit rule was frozen to T1: 1% stop, confirmed RSI/VWAP breakdown, or Moscow session end.",
        "Round-trip spread/slippage assumption: 5 bps.",
        "",
        "Development acceptance criteria:",
        "",
        "- positive compounded result in both P1 and P2;",
        "- at least 50 combined P1+P2 trades;",
        "- combined P1+P2 maximum drawdown no worse than -5%;",
        "- economically explainable rule from a limited 18-variant matrix.",
        "",
        "Period boundaries:",
        "",
        "- P1 ends {} UTC;".format(first_boundary.isoformat()),
        "- P2 ends {} UTC;".format(second_boundary.isoformat()),
        "- P3 is the final control period.",
        "",
        "## Search space",
        "",
        "- RSI recovery levels: 40/60, 45/55, 50/50;",
        "- price confirmation: previous-candle breakout, candle direction, or none;",
        "- relative-volume filter: none or at least 1x the previous-20-candle average;",
        "- hourly EMA context, Moscow-session direction, and VWAP alignment were retained in every variant.",
        "",
        "## Results",
        "",
    ]
    passed = [row for row in rows if row["passed"]]
    lines.append("Variants tested: {}. Passed development criteria: {}.".format(len(rows), len(passed)))
    lines.append("")
    lines.append("| Variant | P1 | P2 | Dev trades | Dev result | Dev DD | P3 control | P3 trades |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for row in sorted(rows, key=lambda item: item["development"]["compounded"], reverse=True):
        p3 = row.get("control")
        lines.append(
            "| {name} | {p1:+.2%} | {p2:+.2%} | {trades} | {dev:+.2%} | {dd:+.2%} | {p3} | {p3_trades} |".format(
                name=row["name"],
                p1=row["period_1"]["compounded"],
                p2=row["period_2"]["compounded"],
                trades=row["development"]["trades"],
                dev=row["development"]["compounded"],
                dd=row["development"]["drawdown"],
                p3="{:+.2%}".format(p3["compounded"]) if p3 else "not opened",
                p3_trades=p3["trades"] if p3 else "—",
            )
        )
    lines.extend(["", "## Accepted variants", ""])
    if not passed:
        lines.append("No variant passed the development criteria. The control period remained unopened for selection.")
    else:
        for row in sorted(passed, key=lambda item: item["development"]["compounded"], reverse=True):
            control = row["control"]
            lines.extend(
                [
                    "### " + row["name"],
                    "",
                    "- Development result: {:+.2%}; {} trades; drawdown {:+.2%}.".format(
                        row["development"]["compounded"],
                        row["development"]["trades"],
                        row["development"]["drawdown"],
                    ),
                    "- P3 control result: {:+.2%}; {} trades; drawdown {:+.2%}.".format(
                        control["compounded"], control["trades"], control["drawdown"]
                    ),
                    "- P3 long result: {:+.2%}; short result: {:+.2%}.".format(
                        row["control_long"]["compounded"],
                        row["control_short"]["compounded"],
                    ),
                    "",
                ]
            )
    lines.extend(
        [
            "## Interpretation rule",
            "",
            "A development pass is not enough. A candidate is only promising if P3 is also positive after costs and does not depend on one unexplained outlier. Forward paper validation remains mandatory.",
            "",
            "This is research, not a trading recommendation.",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_csv(path: Path, rows) -> None:
    fields = [
        "name",
        "rsi_level",
        "confirmation",
        "volume_filter",
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
        "p3_drawdown",
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
                    "name": row["name"],
                    "rsi_level": row["rsi_level"],
                    "confirmation": row["confirmation"],
                    "volume_filter": row["volume_filter"],
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
                    "p3_drawdown": "{:.8f}".format(control["drawdown"]) if control else "",
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
    hourly_contexts = hourly_context_series(candles, hourly)
    session_opens = session_open_series(candles)
    boundaries = period_boundaries(candles)

    rows = []
    for rsi_level, confirmation, volume_filter in itertools.product(
        RSI_LEVELS, CONFIRMATIONS, VOLUME_FILTERS
    ):
        name = "RSI{}-{}-{}".format(rsi_level, confirmation, volume_filter)
        signals = build_variant_signals(
            candles,
            rsi_values,
            vwap_values,
            hourly_contexts,
            session_opens,
            volume_values,
            rsi_level,
            confirmation,
            volume_filter,
        )
        first_signals, second_signals, control_signals = period_signals(
            signals, *boundaries
        )
        first_trades = simulate_trades(candles, first_signals, rsi_values, vwap_values, "T1")
        second_trades = simulate_trades(candles, second_signals, rsi_values, vwap_values, "T1")
        first = combine_metrics(first_trades)
        second = combine_metrics(second_trades)
        development = combine_metrics(first_trades + second_trades)
        passed = passes_development(first, second, development)
        row = {
            "name": name,
            "rsi_level": rsi_level,
            "confirmation": confirmation,
            "volume_filter": volume_filter,
            "period_1": first,
            "period_2": second,
            "development": development,
            "passed": passed,
        }
        if passed:
            control_trades = simulate_trades(
                candles, control_signals, rsi_values, vwap_values, "T1"
            )
            row["control"] = combine_metrics(control_trades)
            row["control_long"] = combine_metrics(
                [trade for trade in control_trades if trade["side"] == "long_candidate"]
            )
            row["control_short"] = combine_metrics(
                [trade for trade in control_trades if trade["side"] == "short_candidate"]
            )
        rows.append(row)

    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    report_path = RESEARCH_DIR / "BTCUSDperpA_trend_entry_search.md"
    csv_path = RESEARCH_DIR / "BTCUSDperpA_trend_entry_search.csv"
    write_report(report_path, rows, boundaries)
    write_csv(csv_path, rows)

    passed = [row for row in rows if row["passed"]]
    print("Variants tested:", len(rows))
    print("Passed development criteria:", len(passed))
    for row in sorted(passed, key=lambda item: item["development"]["compounded"], reverse=True):
        print(
            "{}: dev {:+.2%} ({} trades, DD {:+.2%}), control {:+.2%} ({} trades)".format(
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
