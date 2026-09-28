# CAT-Core v0.3 — Cross-Asset Long Trend Core

Frozen before first v0.3 result.

## Direction
LONG only.

## Symbol conditions
Using completed daily bars:
- at least 2 of 20D, 60D, 120D returns > 0
- close > EMA200
- signal close > highest high of prior 20 completed daily bars

Entry:
- next daily/session open

## Market filter
Crypto:
- BTC completed daily 20D, 60D, 120D returns
- at least 2 of 3 must be > 0

U.S. stocks / stock futures proxy:
- SPY completed RTH daily 20D, 60D, 120D returns
- at least 2 of 3 must be > 0

## Exit
- initial stop = 2 ATR14 from actual entry
- trailing stop = highest completed close since entry - 3 ATR14
- no fixed take profit
- no time stop
- one position per symbol

## Costs
- 4 bps fee per fill
- 2 bps slippage per fill

## Purpose
Test whether a symmetric cross-asset market-momentum filter reduces weak long entries, especially 2022-style drawdown periods, while preserving the positive long expectancy found in CAT v0.1.

No ER, relative-strength ranking, sector filter, or risk cap is added in this version.
