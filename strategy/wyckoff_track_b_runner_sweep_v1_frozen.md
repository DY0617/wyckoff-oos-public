# Wyckoff Track-B Runner Sweep v1 — Frozen

Frozen before results are inspected.

## Scope
Reuse TRACK_B_V1_0_FROZEN setup logic unchanged.
Entry, SL, TP1, TP2, filters, trigger window, costs, data window, and 15m execution semantics are unchanged.

## Evaluation universe
- BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT
- Binance USD-M perpetual
- 2021-09-23T00:00:00Z through 2026-09-21T20:00:00Z
- fee 4 bps + slippage 2 bps per fill
- same conservative same-bar ordering

## Scale-out modes
A. 30/30/40 (current baseline)
B. 20/30/50
C. 25/25/50

Management before runner:
- TP1 hit moves remaining stop to break-even
- TP2 hit moves remaining stop to TP1

## Runner exit modes
1. PIVOT
- remaining runner uses current confirmed 3-bar 4H pivot trailing stop +/- 0.30 ATR.

2. FIB1618_FULL
- after TP2, remaining runner exits fully at the pre-existing 1.618 Fibonacci extension when valid.
- if no valid 1.618 target is available or not reached, existing protective stop remains active until the evaluation cutoff.

3. FIB1618_HALF
- after TP2, exit 20% of original position at valid Fib 1.618 when reached.
- remaining runner continues with confirmed 4H pivot trailing.
- If runner size is less than 20%, exit up to the remaining amount.

## Comparison grid
- 30/30/40 × Pivot
- 30/30/40 × Fib1618 full
- 30/30/40 × Fib1618 half
- 20/30/50 × Pivot
- 20/30/50 × Fib1618 full
- 20/30/50 × Fib1618 half
- 25/25/50 × Pivot
- 25/25/50 × Fib1618 full
- 25/25/50 × Fib1618 half

## Metrics
- closed trades
- win rate
- net R
- average R
- profit factor
- max drawdown
- max consecutive losses
- average and median hold hours
- TP1 / TP2 hit rates
- symbol and direction breakdown
- yearly breakdown

No signal/filter parameter is changed in this sweep.
