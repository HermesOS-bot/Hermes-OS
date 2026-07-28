# Trend Hypothesis

Status: selected forward paper candidate  
Selected: 2026-07-28  
Version: trend-v2-adx25-vwap-reclaim

This hypothesis is for paper observation only. It does not place or close real orders and is not a trading recommendation.

## Entry rule

A long candidate requires all conditions on completed candles:

1. completed-hour EMA 50 is above EMA 200;
2. completed-hour ADX 14 is at least 25;
3. the current Moscow session is positive from its open;
4. the previous five-minute close is at or below the then-current session VWAP;
5. the current five-minute close is above the updated session VWAP;
6. current five-minute RSI 14 is at least 50.

A short candidate mirrors the rule:

1. completed-hour EMA 50 is below EMA 200;
2. completed-hour ADX 14 is at least 25;
3. the current Moscow session is negative from its open;
4. the previous five-minute close is at or above the then-current session VWAP;
5. the current five-minute close is below the updated session VWAP;
6. current five-minute RSI 14 is at most 50.

No relative-volume filter is used in this version.

## Exit research rule

Track the T1 paper exit:

- 1% adverse stop scenario;
- long: RSI crosses below 50 and the candle closes below session VWAP;
- short: RSI crosses above 50 and the candle closes above session VWAP;
- otherwise exit before the Moscow trading date changes.

Fixed 60- and 240-minute outcomes remain recorded for comparison.

## Historical selection result

On development periods with 5 bps round-trip costs:

- P1: +2.12%;
- P2: +3.42%;
- combined: +5.62%;
- maximum drawdown: -3.93%;
- trades: 44.

The result meets the return, period-stability and drawdown criteria but does not yet meet the minimum sample of 50 trades. The closed control period has not been used.

## Forward rule

- Preserve the original trend-v1 journal records.
- New events must be stored with the strategy version.
- Do not mix v1 and v2 statistics.
- Accumulate at least six additional v2 candidates before opening the historical control period.
- Any Telegram message must identify the event as `trend-v2 ADX/VWAP` so it cannot be confused with the old hypothesis.
