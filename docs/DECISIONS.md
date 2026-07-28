# Decisions Log

This file records important project decisions and rationale.

## 2026-07-04
- Chose a modular architecture for Hermes OS.
- Prioritized transparency and testability over complexity.
- Initially defined BTC as the first market reference.

## 2026-07-24
- Chose T-Bank Invest API as the first data source and brokerage environment.
- Chose a BTC-linked NEO asset available in T-Bank as the first instrument; its exact ticker and API identifier still need verification.
- Defined the initial product as a decision-support assistant, not an automatic execution system.
- Planned later expansion to oil, USD/RUB and Moscow Exchange index futures.

## 2026-07-27
- Pre-registered three paper exit scenarios for RSI-reversion signals: fixed 60 minutes (R0), RSI-50 neutralization (R1), and their combination (R2), all with the existing 1% stop and no overnight holding.
- Pre-registered three paper exit scenarios for trend-continuation signals: fixed 240 minutes (T0), confirmed RSI/VWAP breakdown (T1), and their combination (T2), all with the existing 1% stop and no overnight holding.
- Required historical comparison followed by forward paper validation before any exit rule may be described as a recommendation.
- Kept real order placement and automatic trade closing out of scope.

## 2026-07-28
- Selected `trend-v2-adx25-vwap-reclaim` as the next forward paper candidate.
- Froze its entry rule as completed-hour EMA 50/200 direction, ADX 14 at least 25, matching Moscow-session direction, a five-minute reclaim of session VWAP after a pullback, and RSI on the matching side of 50.
- Removed the relative-volume filter from this candidate because it worsened the controlled development result.
- Kept the minimum-sample requirement: the candidate has 44 development trades and must accumulate at least six more forward events before the closed historical control period is opened.
- Required versioned journal records so original trend-v1 and new trend-v2 results are never mixed.
