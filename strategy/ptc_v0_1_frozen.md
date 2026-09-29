# PTC v0.1 — Pullback Trend Continuation

Frozen before any result is inspected.

## Purpose
A new short-swing strategy designed from scratch for fixed Entry / SL / TP levels.
This is NOT a CAT variant.

## Pilot universe / period
- Binance USDT-M perpetual 15m data
- BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT
- LONG and SHORT
- evaluation: 2023-09-01 through 2026-09-01 UTC
- all signals use fully completed bars only

## Timeframe hierarchy
- 4H = trend regime
- 1H = pullback setup
- 15m = confirmation and execution

## 4H trend regime
LONG:
- close > EMA200
- EMA20 > EMA50 > EMA200
- EMA20 > EMA20 from 5 completed 4H bars ago

SHORT: exact inverse.

## 1H pullback setup
LONG:
- latest completed 1H bar closes below or at EMA20
- close remains above EMA50
- low is not below EMA50 by more than 0.25 * ATR14
- latest completed 4H regime is LONG

SHORT:
- close >= EMA20
- close < EMA50
- high is not above EMA50 by more than 0.25 * ATR14
- latest completed 4H regime is SHORT

A pullback setup opens a confirmation window of 8 completed 15m bars (2 hours).
Only one active setup/order/position per symbol.

## 15m confirmation
LONG:
- completed 15m close > EMA20
- close > highest high of prior 4 completed 15m bars

SHORT:
- close < EMA20
- close < lowest low of prior 4 completed 15m bars

The first qualifying confirmation within the 2h window is used.

## Fixed levels, known when confirmation bar closes
Let A = 15m Wilder ATR14.

LONG:
- Entry = confirmation high + 0.05*A
- raw SL = lowest low from the start of the 1H pullback bar through the confirmation bar - 0.10*A
- TP1 = Entry + 1.5R
- TP2 = Entry + 2.5R

SHORT:
- Entry = confirmation low - 0.05*A
- raw SL = highest high from pullback-bar start through confirmation + 0.10*A
- TP1 = Entry - 1.5R
- TP2 = Entry - 2.5R

R = absolute Entry-to-SL distance.

## Structural-risk validity
Do NOT clamp the stop.
Trade only if structural stop distance is between 0.8*A and 2.0*A.
Otherwise skip the setup.

## Pending entry
- stop-entry becomes active on first 15m bar after confirmation closes
- valid for 4 completed 15m bars (1 hour)
- long: if bar opens >= Entry, fill at open; else fill at Entry if high >= Entry
- short: if bar opens <= Entry, fill at open; else fill at Entry if low <= Entry
- cancel when validity expires

## Exit
- 50% at TP1
- remaining 50% at TP2
- fixed SL for whole trade
- no breakeven move
- no trailing stop
- max hold = 48 hours from fill; remaining size exits at first available 15m close at/after 48h
- if SL and TP are both reachable inside same 15m bar, use adverse-first ordering
- gap through SL fills at bar open

## Costs
- 4 bps fee + 2 bps slippage per fill-equivalent
- partial exits charged proportionally
- funding excluded from pilot; add actual funding only if the core edge survives

## Primary metrics
- trades; long/short split
- win rate
- total R; avg R; profit factor
- max drawdown in R
- max losing streak
- TP1 / TP2 hit rate
- average / median hold hours
- confirmation rate
- entry fill / expiry rate
- structural-risk skip rate

## Research rule
No v0.1 parameter changes after results are viewed.
If v0.1 fails, preserve it as failed and create a separately frozen v0.2.
