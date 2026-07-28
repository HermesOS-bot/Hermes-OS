#!/usr/bin/env python3
"""Backtest pre-registered exit rules for RSI and trend paper hypotheses.

The script is research-only and cannot place orders. It compares:
- R0: RSI entry, stop or 60-minute time exit;
- R1: RSI entry, stop or RSI-50 neutralization, otherwise session end;
- R2: RSI entry, first of stop, RSI-50 neutralization or 60 minutes;
- T0: trend entry, stop or 240-minute time exit;
- T1: trend entry, stop or confirmed RSI/VWAP breakdown, otherwise session end;
- T2: trend entry, first of stop, confirmed breakdown or 240 minutes.

All positions are closed before the Moscow trading date changes. Decisions use
completed five-minute candles only. Entry is the next candle open after a signal.
"""

import csv
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from core.indicators import ema, rsi  # noqa: E402
from core.models import Candle  # noqa: E402
from core.paper_observer import MOSCOW  # noqa: E402
from core.trend_observer import _continuation_side  # noqa: E402

DATA_DIR = REPO_ROOT / "data" / "market"
RESEARCH_DIR = REPO_ROOT / "data" / "research"
STOP_FRACTION = 0.01
ROUND_TRIP_COST_BPS = (0, 2, 5, 10)

EXIT_RULES = {
    "R0": {"signal": "rsi", "dynamic": None, "max_minutes": 60},
    "R1": {"signal": "rsi", "dynamic": "rsi_neutral", "max_minutes": None},
    "R2": {"signal": "rsi", "dynamic": "rsi_neutral", "max_minutes": 60},
    "T0": {"signal": "trend", "dynamic": None, "max_minutes": 240},
    "T1": {"signal": "trend", "dynamic": "trend_breakdown", "max_minutes": None},
    "T2": {"signal": "trend", "dynamic": "trend_breakdown", "max_minutes": 240},
}


def load_candles(path: Path) -> List[Candle]:
    candles = []
    with path.open("r", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            candles.append(
                Candle(
                    timestamp=datetime.fromisoformat(row["timestamp_utc"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
            )
    return sorted(candles, key=lambda candle: candle.timestamp)


def session_vwap_series(candles: List[Candle]) -> List[Optional[float]]:
    result = []
    current_date = None
    weighted_total = 0.0
    volume_total = 0.0
    for candle in candles:
        session_date = candle.timestamp.astimezone(MOSCOW).date()
        if session_date != current_date:
            current_date = session_date
            weighted_total = 0.0
            volume_total = 0.0
        typical_price = (candle.high + candle.low + candle.close) / 3
        weighted_total += typical_price * candle.volume
        volume_total += candle.volume
        result.append(weighted_total / volume_total if volume_total > 0 else None)
    return result


def hourly_context_series(
    five_minute: List[Candle], hourly: List[Candle]
) -> List[str]:
    hourly = sorted(hourly, key=lambda candle: candle.timestamp)
    closes = [candle.close for candle in hourly]
    fast = ema(closes, 50)
    slow = ema(closes, 200)
    completed_at = [candle.timestamp + timedelta(hours=1) for candle in hourly]
    result = []
    hourly_index = -1
    for candle in five_minute:
        observed_at = candle.timestamp + timedelta(minutes=5)
        while (
            hourly_index + 1 < len(hourly)
            and completed_at[hourly_index + 1] <= observed_at
        ):
            hourly_index += 1
        if hourly_index < 0 or fast[hourly_index] is None or slow[hourly_index] is None:
            result.append("unknown")
        elif fast[hourly_index] > slow[hourly_index]:
            result.append("bullish")
        elif fast[hourly_index] < slow[hourly_index]:
            result.append("bearish")
        else:
            result.append("flat")
    return result


def session_open_series(candles: List[Candle]) -> List[float]:
    result = []
    current_date = None
    current_open = 0.0
    for candle in candles:
        session_date = candle.timestamp.astimezone(MOSCOW).date()
        if session_date != current_date:
            current_date = session_date
            current_open = candle.open
        result.append(current_open)
    return result


def build_rsi_signals(candles: List[Candle], rsi_values) -> List[Dict[str, object]]:
    signals = []
    for index in range(1, len(candles)):
        previous = rsi_values[index - 1]
        current = rsi_values[index]
        if previous is None or current is None:
            continue
        if previous >= 25 and current < 25:
            side = "long_candidate"
        elif previous <= 75 and current > 75:
            side = "short_candidate"
        else:
            continue
        signals.append({"index": index, "timestamp": candles[index].timestamp, "side": side})
    return signals


def build_trend_signals(
    candles: List[Candle],
    rsi_values,
    vwap_values,
    hourly_contexts,
    session_opens,
) -> List[Dict[str, object]]:
    signals = []
    for index in range(1, len(candles)):
        candle = candles[index]
        session_open = session_opens[index]
        side = _continuation_side(
            rsi_values[index - 1],
            rsi_values[index],
            hourly_contexts[index],
            candle.close / session_open - 1,
            candle.close,
            vwap_values[index],
            candles[index - 1],
        )
        if side is not None:
            signals.append({"index": index, "timestamp": candle.timestamp, "side": side})
    return signals


def stop_was_hit(side: str, candle: Candle, stop_price: float) -> bool:
    if side == "long_candidate":
        return candle.low <= stop_price
    return candle.high >= stop_price


def rsi_neutral_exit(
    side: str, previous_rsi: Optional[float], current_rsi: Optional[float]
) -> bool:
    if previous_rsi is None or current_rsi is None:
        return False
    if side == "long_candidate":
        return previous_rsi < 50 <= current_rsi
    return previous_rsi > 50 >= current_rsi


def trend_breakdown_exit(
    side: str,
    previous_rsi: Optional[float],
    current_rsi: Optional[float],
    close: float,
    session_vwap: Optional[float],
) -> bool:
    if session_vwap is None or previous_rsi is None or current_rsi is None:
        return False
    if side == "long_candidate":
        return previous_rsi >= 50 > current_rsi and close < session_vwap
    return previous_rsi <= 50 < current_rsi and close > session_vwap


def directional_return(side: str, entry: float, exit_price: float) -> float:
    raw = exit_price / entry - 1
    return raw if side == "long_candidate" else -raw


def simulate_trades(
    candles: List[Candle],
    signals: Iterable[Dict[str, object]],
    rsi_values,
    vwap_values,
    rule_name: str,
    stop_fraction: float = STOP_FRACTION,
) -> List[Dict[str, object]]:
    rule = EXIT_RULES[rule_name]
    next_entry_index = 0
    trades = []
    for signal in signals:
        signal_index = int(signal["index"])
        entry_index = signal_index + 1
        if entry_index < next_entry_index or entry_index >= len(candles):
            continue
        signal_time = candles[signal_index].timestamp
        entry_candle = candles[entry_index]
        if entry_candle.timestamp != signal_time + timedelta(minutes=5):
            continue
        side = str(signal["side"])
        entry_price = entry_candle.open
        stop_price = entry_price * (1 - stop_fraction if side == "long_candidate" else 1 + stop_fraction)
        entry_date = entry_candle.timestamp.astimezone(MOSCOW).date()
        exit_index = None
        exit_price = None
        exit_reason = None

        for index in range(entry_index, len(candles)):
            candle = candles[index]
            if candle.timestamp.astimezone(MOSCOW).date() != entry_date:
                break
            if stop_was_hit(side, candle, stop_price):
                exit_index = index
                exit_price = stop_price
                exit_reason = "stop_{:.2%}".format(stop_fraction)
                break

            dynamic = rule["dynamic"]
            if dynamic == "rsi_neutral" and rsi_neutral_exit(
                side, rsi_values[index - 1], rsi_values[index]
            ):
                exit_index = index
                exit_price = candle.close
                exit_reason = "rsi_neutral"
                break
            if dynamic == "trend_breakdown" and trend_breakdown_exit(
                side,
                rsi_values[index - 1],
                rsi_values[index],
                candle.close,
                vwap_values[index],
            ):
                exit_index = index
                exit_price = candle.close
                exit_reason = "trend_breakdown"
                break

            completed_at = candle.timestamp + timedelta(minutes=5)
            max_minutes = rule["max_minutes"]
            if max_minutes is not None and completed_at >= entry_candle.timestamp + timedelta(minutes=max_minutes):
                exit_index = index
                exit_price = candle.close
                exit_reason = "time_{}m".format(max_minutes)
                break

            next_index = index + 1
            if next_index < len(candles):
                next_date = candles[next_index].timestamp.astimezone(MOSCOW).date()
                if next_date != entry_date:
                    exit_index = index
                    exit_price = candle.close
                    exit_reason = "session_end"
                    break

        if exit_index is None or exit_price is None:
            continue
        exit_time = candles[exit_index].timestamp + timedelta(minutes=5)
        trades.append(
            {
                "rule": rule_name,
                "signal_time_utc": signal_time.isoformat(),
                "entry_time_utc": entry_candle.timestamp.isoformat(),
                "exit_time_utc": exit_time.isoformat(),
                "holding_minutes": int((exit_time - entry_candle.timestamp).total_seconds() / 60),
                "side": side,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "exit_reason": exit_reason,
                "gross_return": directional_return(side, entry_price, exit_price),
            }
        )
        next_entry_index = exit_index + 1
    return trades


def maximum_drawdown(returns: Iterable[float]) -> float:
    equity = 1.0
    peak = 1.0
    worst = 0.0
    for value in returns:
        equity *= 1 + value
        peak = max(peak, equity)
        worst = min(worst, equity / peak - 1)
    return worst


def metrics(trades: List[Dict[str, object]], cost_bps: int) -> Dict[str, float]:
    cost = cost_bps / 10_000
    returns = [float(trade["gross_return"]) - cost for trade in trades]
    if not returns:
        return {"count": 0, "win_rate": 0.0, "mean": 0.0, "median": 0.0, "compounded": 0.0, "max_drawdown": 0.0, "median_hold": 0.0}
    equity = 1.0
    for value in returns:
        equity *= 1 + value
    return {
        "count": len(returns),
        "win_rate": sum(value > 0 for value in returns) / len(returns),
        "mean": statistics.mean(returns),
        "median": statistics.median(returns),
        "compounded": equity - 1,
        "max_drawdown": maximum_drawdown(returns),
        "median_hold": statistics.median(float(trade["holding_minutes"]) for trade in trades),
    }


def write_trades(path: Path, trades_by_rule) -> None:
    fields = ["rule", "signal_time_utc", "entry_time_utc", "exit_time_utc", "holding_minutes", "side", "entry_price", "exit_price", "exit_reason", "gross_return"]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for rule_name in EXIT_RULES:
            for trade in trades_by_rule[rule_name]:
                row = dict(trade)
                row["gross_return"] = "{:.8f}".format(row["gross_return"])
                writer.writerow(row)


def write_report(path: Path, trades_by_rule) -> None:
    descriptions = {
        "R0": "RSI signal: 1% stop or 60-minute exit.",
        "R1": "RSI signal: 1% stop or RSI return through 50; otherwise session end.",
        "R2": "RSI signal: first of 1% stop, RSI return through 50 or 60 minutes.",
        "T0": "Trend signal: 1% stop or 240-minute exit.",
        "T1": "Trend signal: 1% stop or RSI/VWAP breakdown; otherwise session end.",
        "T2": "Trend signal: first of 1% stop, RSI/VWAP breakdown or 240 minutes.",
    }
    lines = [
        "# BTCUSDperpA exit-rule backtest",
        "",
        "Pre-registered comparison of the exit rules agreed on 27 July 2026.",
        "Entry is the next five-minute candle open after a signal. Exit decisions use completed candles only.",
        "A stop touched inside a candle is conservatively assumed to execute before a close-based exit.",
        "Positions are not carried across the Moscow trading date. Position size is one equal unleveraged unit.",
        "",
        "This is research, not a trading recommendation or proof of future profitability.",
        "",
    ]
    for rule_name in EXIT_RULES:
        trades = trades_by_rule[rule_name]
        lines.extend(["## {}".format(rule_name), "", descriptions[rule_name], ""])
        reasons = {}
        for trade in trades:
            reasons[trade["exit_reason"]] = reasons.get(trade["exit_reason"], 0) + 1
        if reasons:
            lines.append("Exit reasons: " + ", ".join("{} {}".format(name, count) for name, count in sorted(reasons.items())))
            lines.append("")
        for scope, selected in (
            ("All", trades),
            ("Long", [trade for trade in trades if trade["side"] == "long_candidate"]),
            ("Short", [trade for trade in trades if trade["side"] == "short_candidate"]),
        ):
            lines.extend(["### {}".format(scope), ""])
            for cost_bps in ROUND_TRIP_COST_BPS:
                result = metrics(selected, cost_bps)
                lines.extend(
                    [
                        "#### Round-trip spread/slippage: {} bps".format(cost_bps),
                        "",
                        "- Trades: {}".format(result["count"]),
                        "- Win rate: {:.1%}".format(result["win_rate"]),
                        "- Mean per trade: {:+.3%}".format(result["mean"]),
                        "- Median per trade: {:+.3%}".format(result["median"]),
                        "- Compounded result: {:+.2%}".format(result["compounded"]),
                        "- Maximum drawdown: {:+.2%}".format(result["max_drawdown"]),
                        "- Median holding time: {:.0f} minutes".format(result["median_hold"]),
                        "",
                    ]
                )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    candles = load_candles(DATA_DIR / "BTCUSDperpA_5min.csv")
    hourly = load_candles(DATA_DIR / "BTCUSDperpA_1hour.csv")
    rsi_values = rsi([candle.close for candle in candles], 14)
    vwap_values = session_vwap_series(candles)
    contexts = hourly_context_series(candles, hourly)
    session_opens = session_open_series(candles)
    rsi_signals = build_rsi_signals(candles, rsi_values)
    trend_signals = build_trend_signals(candles, rsi_values, vwap_values, contexts, session_opens)
    signals_by_type = {"rsi": rsi_signals, "trend": trend_signals}
    trades_by_rule = {
        rule_name: simulate_trades(
            candles,
            signals_by_type[rule["signal"]],
            rsi_values,
            vwap_values,
            rule_name,
        )
        for rule_name, rule in EXIT_RULES.items()
    }

    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    trades_path = RESEARCH_DIR / "BTCUSDperpA_exit_rule_trades.csv"
    report_path = RESEARCH_DIR / "BTCUSDperpA_exit_rule_report.md"
    write_trades(trades_path, trades_by_rule)
    write_report(report_path, trades_by_rule)

    print("RSI signals:", len(rsi_signals))
    print("Trend signals:", len(trend_signals))
    for rule_name in EXIT_RULES:
        result = metrics(trades_by_rule[rule_name], 5)
        print(
            "{}: {} trades, 5 bps {:+.2%}, drawdown {:+.2%}, median hold {:.0f}m".format(
                rule_name,
                result["count"],
                result["compounded"],
                result["max_drawdown"],
                result["median_hold"],
            )
        )
    print("Saved report to", report_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
