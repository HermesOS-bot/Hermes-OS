# Exit Rules Research Specification

Status: pre-registered research hypotheses  
Agreed: 2026-07-27

These rules apply only to hypothetical paper positions. They do not place or close real orders and are not trading recommendations.

## Shared execution assumptions

- A signal is known only after its five-minute candle closes.
- Hypothetical entry is the next five-minute candle open in historical tests and the observed bid/ask in forward tests.
- Exit decisions use completed five-minute candles only.
- The first applicable exit condition wins.
- A 1% adverse move is tracked as a hard stop scenario.
- Positions are not carried across the Moscow trading date.
- Long and short results are reported separately.
- Spread and slippage are tested as explicit round-trip cost scenarios.

## RSI-reversion exits

### R0 — fixed-time control

Exit at the first of:

1. 1% stop;
2. 60 minutes after entry;
3. session end.

### R1 — RSI neutralization

Exit at the first of:

1. 1% stop;
2. long: RSI crosses 50 upward;
3. short: RSI crosses 50 downward;
4. session end.

### R2 — combined RSI rule

Exit at the first of:

1. 1% stop;
2. RSI neutralization as in R1;
3. 60 minutes after entry;
4. session end.

## Trend-continuation exits

### T0 — fixed-time control

Exit at the first of:

1. 1% stop;
2. 240 minutes after entry;
3. session end.

### T1 — trend breakdown

For a long, breakdown requires both an RSI cross below 50 and a close below session VWAP. For a short, the conditions are mirrored.

Exit at the first of:

1. 1% stop;
2. confirmed trend breakdown;
3. session end.

### T2 — combined trend rule

Exit at the first of:

1. 1% stop;
2. confirmed trend breakdown as in T1;
3. 240 minutes after entry;
4. session end.

## Evaluation protocol

Compare each rule using:

- trade count;
- win rate;
- mean and median return;
- compounded result;
- maximum drawdown;
- median holding time;
- exit-reason distribution;
- long and short results separately;
- 0, 2, 5 and 10 bps round-trip cost scenarios;
- stability across time periods and forward observations.

No rule becomes a user-facing exit recommendation based on the same historical sample used to define or select it. Forward paper validation is required.
