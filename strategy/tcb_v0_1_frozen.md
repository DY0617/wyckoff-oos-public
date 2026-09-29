# TCB v0.1 — Trend Compression Breakout

Frozen before results are inspected.

## Purpose
A new cross-asset-friendly short-swing strategy with all prices fixed before entry.
TCB does not use CAT or PTC entry logic.

## Pilot
- Binance USDT-M perpetual 15m execution data
- BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT
- LONG and SHORT
- evaluation 2023-09-01 through 2026-09-01 UTC
- completed bars only

## Structure
- 4H: directional trend
- 1H: volatility compression box
- 15m: execution only

## 4H trend
LONG:
- close > EMA200
- EMA50 > EMA200
- EMA50 > EMA50 from 5 completed 4H bars ago

SHORT: exact inverse.

## 1H compression box
Use the latest 6 completed 1H bars.

Let:
- BoxHigh = max high of those 6 bars
- BoxLow = min low of those 6 bars
- BoxRange = BoxHigh - BoxLow
- A = current 1H Wilder ATR14
- ATRmean50 = mean of the latest 50 completed 1H ATR14 values

Compression is valid when:
- BoxRange <= 2.2*A
- A <= 0.90*ATRmean50

Trend-location filter:
LONG:
- box midpoint > current 1H EMA50
- BoxLow >= EMA50 - 0.50*A
- latest completed 4H regime is LONG

SHORT:
- box midpoint < current 1H EMA50
- BoxHigh <= EMA50 + 0.50*A
- latest completed 4H regime is SHORT

## Fixed levels at setup close
LONG:
- Entry = BoxHigh + 0.05*A
- SL = BoxLow - 0.05*A
- TP1 = Entry + 1.5R
- TP2 = Entry + 2.5R

SHORT:
- Entry = BoxLow - 0.05*A
- SL = BoxHigh + 0.05*A
- TP1 = Entry - 1.5R
- TP2 = Entry - 2.5R

R = absolute Entry-to-SL distance.

Only accept setups with R between 0.8*A and 2.3*A.
No stop clamping.

## Pending order
- active from first 15m bar after setup closes
- valid for 32 completed 15m bars = 8 hours
- LONG: stop-entry at Entry
- SHORT: stop-entry at Entry
- gap through Entry fills at open
- one active order/position per symbol

## Exit
- 50% TP1
- 50% TP2
- fixed SL
- no BE
- no trailing
- max hold 48h
- adverse-first when SL and TP are both reachable in one 15m bar
- gap through SL fills at open

## Costs
- 4 bps fee + 2 bps slippage per fill-equivalent
- funding excluded from pilot; add actual funding if core edge survives

## Metrics
trades, long/short, win rate, total/avg R, PF, max DD R, max losing streak,
TP1/TP2 hit rate, hold time, setup fill/expiry, risk rejection.

## Research rule
No parameter changes inside v0.1 after results are seen.
