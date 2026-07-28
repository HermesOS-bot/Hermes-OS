#!/usr/bin/env python3
"""Third controlled trend-entry study: pullback and VWAP reclaim.

The hourly context returns to the original EMA 50/200 because faster contexts
failed stage two. A signal now requires an actual cross back through session
VWAP after a pullback, rather than buying or selling an already extended move.
P1/P2 are development periods; P3 remains closed unless a variant passes.
"""

import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from core.indicators import relative_volume, rsi  # noqa: E402
from backtest_exit_rules import (  # noqa: E402
    DATA_DIR,
    RESEARCH_DIR,
    hourly_context_series,
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

RSI_STATES = (45, 50, 55)
VOLUME_FILTERS = ("any", "at_least_1x")


def pullback_reclaim_side(
    index,
    candles,
    rsi_values,
    vwap_values,
    contexts,
    session_opens,
    volume_values,
    rsi_state,
    volume_filter,
):
    if index < 1 or rsi_values[index] is None:
        return None
    if vwap_values[index] is None or vwap_values[index - 1] is None:
        return None
    if volume_filter == "at_least_1x" and (
        volume_values[index] is None or volume_values[index] < 1
    ):
        return None
    candle = candles[index]
    previous = candles[index - 1]
    session_return = candle.close / session_opens[index] - 1
    short_state = 100 - rsi_state
    if (
        contexts[index] == "bullish"
        and session_return > 0
        and previous.close <= vwap_values[index - 1]
        and candle.close > vwap_values[index]
        and rsi_values[index] >= rsi_state
    ):
        return "long_candidate"
    if (
        contexts[index] == "bearish"
        and session_return < 0
        and previous.close >= vwap_values[index - 1]
        and candle.close < vwap_values[index]
        and rsi_values[index] <= short_state
    ):
        return "short_candidate"
    return None


def build_signals(
    candles,
    rsi_values,
    vwap_values,
    contexts,
    session_opens,
    volume_values,
    rsi_state,
    volume_filter,
):
    signals = []
    for index in range(1, len(candles)):
        side = pullback_reclaim_side(
            index,
            candles,
            rsi_values,
            vwap_values,
            contexts,
            session_opens,
            volume_values,
            rsi_state,
            volume_filter,
        )
        if side:
            signals.append(
                {"index": index, "timestamp": candles[index].timestamp, "side": side}
            )
    return signals


def write_report(path: Path, rows, boundaries):
    lines = [
        "# Trend pullback/VWAP-reclaim controlled search",
        "",
        "Research date: 2026-07-27.",
        "",
        "Stage-three study. The original completed-hour EMA 50/200 context and T1 exit were frozen.",
        "The entry requires a real cross back through session VWAP after a pullback.",
        "Selection used P1 and P2 only; P3 remained closed unless a variant passed.",
        "Round-trip spread/slippage assumption: 5 bps.",
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
        lines.append("No variant passed. P3 remained unopened.")
    else:
        for row in passed:
            lines.append(
                "- {}: development {:+.2%}, P3 {:+.2%}.".format(
                    row["name"], row["development"]["compounded"], row["control"]["compounded"]
                )
            )
    lines.extend(["", "This is research, not a trading recommendation."])
    path.write_text("\n".join(lines), encoding="utf-8")


def write_csv(path: Path, rows):
    fields = ["name", "passed", "p1_trades", "p1_result", "p2_trades", "p2_result", "dev_trades", "dev_result", "dev_drawdown", "p3_trades", "p3_result"]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            control = row.get("control")
            writer.writerow(
                {
                    "name": row["name"],
                    "passed": row["passed"],
                    "p1_trades": row["period_1"]["trades"],
                    "p1_result": row["period_1"]["compounded"],
                    "p2_trades": row["period_2"]["trades"],
                    "p2_result": row["period_2"]["compounded"],
                    "dev_trades": row["development"]["trades"],
                    "dev_result": row["development"]["compounded"],
                    "dev_drawdown": row["development"]["drawdown"],
                    "p3_trades": control["trades"] if control else "",
                    "p3_result": control["compounded"] if control else "",
                }
            )


def main() -> int:
    candles = load_candles(DATA_DIR / "BTCUSDperpA_5min.csv")
    hourly = load_candles(DATA_DIR / "BTCUSDperpA_1hour.csv")
    rsi_values = rsi([candle.close for candle in candles], 14)
    volume_values = relative_volume([candle.volume for candle in candles], 20)
    vwap_values = session_vwap_series(candles)
    contexts = hourly_context_series(candles, hourly)
    session_opens = session_open_series(candles)
    boundaries = period_boundaries(candles)

    rows = []
    for rsi_state in RSI_STATES:
        for volume_filter in VOLUME_FILTERS:
            name = "vwap_reclaim-rsi{}-{}".format(rsi_state, volume_filter)
            signals = build_signals(
                candles,
                rsi_values,
                vwap_values,
                contexts,
                session_opens,
                volume_values,
                rsi_state,
                volume_filter,
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
    report_path = RESEARCH_DIR / "BTCUSDperpA_trend_pullback_search.md"
    csv_path = RESEARCH_DIR / "BTCUSDperpA_trend_pullback_search.csv"
    write_report(report_path, rows, boundaries)
    write_csv(csv_path, rows)
    passed = [row for row in rows if row["passed"]]
    print("Pullback variants tested:", len(rows))
    print("Passed development criteria:", len(passed))
    for row in passed:
        print(row["name"], row["development"], row["control"])
    print("Saved report to", report_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
