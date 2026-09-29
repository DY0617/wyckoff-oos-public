# CAT Short-Swing v0.1 — Frozen Pilot

Frozen before any result is inspected.

## Goal
A short-swing execution variant inspired by CAT, with Entry / SL / TP1 / TP2 fully known before entry.

## Universe / pilot
- Binance USDT-M perpetual 15m data
- BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT
- evaluation: 2023-09-01 through 2026-09-01 UTC (warmup contained inside fetched data)
- LONG only for v0.1; shorts are a separate later experiment

## Completed-bar hierarchy
All indicators use only fully completed bars.
15m is the base execution series. 1H and 4H bars are aggregated from completed 15m bars.

## 4H regime
At the close of a completed 4H bar:
- close > EMA200
- EMA50 > EMA200
- at least 2 of ret20, ret60, ret120 are > 0

## 1H setup
At the close of a completed 1H bar, with the latest completed 4H regime valid:
- close > EMA50 > EMA200
- ER20 >= 0.30
- close > highest high of the prior 20 completed 1H bars

## Fixed order levels, known at setup time
Let A = 1H Wilder ATR14 on the setup bar.
- raw entry = setup-bar high + 0.05 * A
- structural raw stop = lowest low of the latest 5 completed 1H bars - 0.25 * A
- stop distance is clamped to [1.0*A, 2.0*A] from entry
- Entry = raw entry
- SL = Entry - clamped stop distance
- R = Entry - SL
- TP1 = Entry + 1.5R
- TP2 = Entry + 2.5R

## Entry validity
- stop-entry order becomes active on the first 15m bar AFTER the 1H setup bar closes
- valid for the next 16 completed 15m bars (4 hours)
- if a bar opens above Entry, fill at that open (gap/slippage realism)
- otherwise fill at Entry when high >= Entry
- one open position per symbol
- no re-entry while a position is open

## Exit
- 50% at TP1
- 50% at TP2
- no breakeven move in v0.1
- no trailing stop
- initial SL remains fixed for the whole trade
- maximum holding period: 72 hours from fill; remaining size exits at the first available 15m close at/after 72h
- if SL gaps through, fill at bar open
- if both SL and a TP are reachable inside the same 15m bar, use adverse-first ordering (SL before TP) unless the open itself resolves the sequence
- after TP1 has filled, remaining 50% continues toward TP2 or SL/time exit

## Costs
- 4 bps fee + 2 bps slippage per fill-equivalent, consistent with CAT research
- partial exits charged proportionally
- funding excluded from this pilot because max hold is 72h; add actual settlement funding in the realism pass if the core edge survives

## Primary metrics
- trades, win rate
- net total R, avg R, profit factor
- max drawdown in R
- max losing streak
- TP1 hit rate, TP2 hit rate
- average / median hold hours
- entry fill rate and expiry rate

## Interpretation
This is a viability pilot, not a final optimized strategy. No parameter changes are allowed after results without a new frozen version.
