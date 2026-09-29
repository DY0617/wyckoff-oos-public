# CAT Short-Swing v0.2 — Breakout Retest Entry

Frozen before v0.2 results are inspected.

## Hypothesis
v0.1 chased the 1H breakout with a stop-entry. Most trades then used nearly the maximum 2 ATR stop distance. v0.2 changes only the execution concept: after a valid 1H breakout, buy a retest of the broken 20H resistance instead of chasing above the setup high.

## Universe / period
Same as v0.1 pilot:
- Binance USDT-M perpetual 15m
- BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT
- evaluation 2023-09-01 through 2026-09-01 UTC
- LONG only

## Filters
Unchanged:
4H regime
- close > EMA200
- EMA50 > EMA200
- 2 of ret20/ret60/ret120 > 0

1H setup
- close > EMA50 > EMA200
- ER20 >= 0.30
- close > highest high of prior 20 completed 1H bars

## Levels fixed at the setup close
Let A = setup-bar 1H Wilder ATR14 and H20 = highest high of prior 20 completed 1H bars.
- Entry = H20 + 0.05*A (resting buy limit after breakout)
- raw SL = lowest low of latest 5 completed 1H bars - 0.25*A
- Entry-to-SL distance clamped to [1.0*A, 2.0*A]
- R = Entry - SL
- TP1 = Entry + 1.5R
- TP2 = Entry + 2.5R

## Pending order
- active from first 15m bar after setup close
- valid for 32 x 15m bars = 8 hours
- only one pending order per symbol
- no new setup/order while one order is pending
- cancel if a bar opens at/below SL before entry
- if open <= Entry and open > SL, fill at open (price improvement)
- otherwise fill at Entry when low <= Entry <= high

## Exit
Unchanged:
- 50% TP1, 50% TP2
- fixed SL; no BE, no trail
- max hold 72h
- adverse-first if SL and TP are both reachable in the same 15m bar
- 4 bps fee + 2 bps slippage per fill-equivalent
- funding excluded from pilot; add in realism pass if viable

## Pass/fail intent
This version should not be promoted unless it shows a material positive edge after costs and a clearly improved drawdown profile versus v0.1. No parameter tuning inside v0.2 after seeing results.
