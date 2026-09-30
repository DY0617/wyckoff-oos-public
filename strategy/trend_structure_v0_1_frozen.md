# Trend Structure v0.1 — Frozen Pilot

Frozen before results are inspected.

## Purpose
Cross-asset-friendly trend strategy research track using mechanical trend structure rather than discretionary chart drawing.

This experiment is independent from Wyckoff Track B, CAT, PTC, and TCB.

## Pilot market
- Binance USDT-M perpetual
- BTCUSDT, ETHUSDT, BNBUSDT
- LONG and SHORT
- 4H regime / 1H signal / 15m execution
- evaluation: 2021-09-01 through 2026-09-01 UTC
- completed bars only
- no look-ahead pivots: a pivot is usable only after the right-side confirmation bars have closed

## Shared indicators
1H:
- Wilder ATR(14)
- EMA20 / EMA50
- RSI(14)
- volume SMA20

4H regime:
LONG:
- close > EMA50
- EMA20 > EMA50
- EMA20 > EMA20 five completed 4H bars ago

SHORT: exact inverse.

## Confirmed pivots
- pivot radius = 3 completed 1H bars on each side
- pivot becomes known only 3 bars after the pivot bar
- candidate trendlines use the latest 3 qualifying confirmed pivots inside 120 completed 1H bars
- line fit is rejected when pivot RMSE > 0.35 * current ATR
- minimum pivot span = 12 bars
- slope must be meaningful but not near-vertical:
  - normalized absolute slope between 0.01 and 0.25 ATR per 1H bar

## Track A — Pivot Trendline Pullback
LONG:
- 4H LONG regime
- 1H EMA20 > EMA50
- rising support line from 3 confirmed pivot lows
- current low reaches support + 0.35 ATR
- current close remains above support - 0.10 ATR
- RSI >= 45
- current volume >= 0.80 * volume SMA20
- stop-entry = current high + 0.05 ATR

SHORT: exact inverse using a falling resistance line and current low - 0.05 ATR stop-entry.

## Track B — Trendline Breakout + Retest
LONG:
- 4H LONG regime
- descending resistance line from 3 confirmed pivot highs
- within the previous 8 completed 1H bars, a close crossed from at/below the line to > line + 0.10 ATR
- breakout volume >= 1.20 * volume SMA20
- current bar retests the projected broken line within 0.35 ATR and closes back above it
- RSI >= 50
- stop-entry = current high + 0.05 ATR

SHORT: exact inverse using an ascending support line.

## Track C — Regression Channel Pullback
- rolling window = 80 completed 1H closes
- ordinary least-squares price-on-time regression
- channel = regression +/- 1.5 residual standard deviations
- normalized absolute slope >= 0.03 ATR per 1H bar

LONG:
- 4H LONG regime
- EMA20 > EMA50
- current low reaches lower channel + 0.20 ATR
- current close finishes back above the lower channel
- RSI >= 42
- stop-entry = current high + 0.05 ATR

SHORT: exact inverse at the upper channel.

## Initial stop
Structural stop, then risk-quality filter.

LONG:
- Track A/B: below the relevant line/retest structure and latest confirmed pivot low
- Track C: below the lower regression channel and latest confirmed pivot low

SHORT: exact inverse.

Accept only planned risk between 0.70 and 2.80 current 1H ATR.

## Pending entry
- active from the first 15m bar after signal close
- expires after 16 completed 15m bars = 4 hours
- gap through stop-entry fills at the 15m open
- one active order/position per symbol
- if multiple tracks signal on the same completed 1H bar, priority A -> B -> C for the pilot; duplicate exposure is not allowed

## Exit — 20 / 20 / 60
- TP1: 20% at +1.5R
- after TP1: remaining stop moves to entry (BE)
- TP2: 20% at +2.5R
- after TP2: remaining 60% becomes Runner
- Runner stop updates only from completed 1H information:
  - LONG: max(BE, EMA20 - 0.20 ATR, latest confirmed pivot low - 0.20 ATR)
  - SHORT: min(BE, EMA20 + 0.20 ATR, latest confirmed pivot high + 0.20 ATR)
- max hold = 10 days
- adverse-first when stop and target are both reachable in one 15m bar
- gap through stop fills at open

## Stock adapter
The stock test uses the same signal/entry/exit rules, but respects the RTH market clock:
- source: existing stock53 15m RTH cache
- regime timeframe: previous completed RTH daily bar (instead of crypto 4H)
- signal timeframe: six complete 60m bars aligned from 09:30 ET through 15:30 ET
- execution timeframe: 15m RTH; the final 15:30-16:00 ET half-hour is execution-only
- evaluation: 2021-04-01 through 2026-04-01 UTC

The daily regime substitution is an asset-clock adaptation, so crypto and stock results are compared as sibling implementations, not as identical-timeframe experiments.

## Costs
- 4 bps fee + 2 bps slippage per fill-equivalent
- funding excluded from v0.1; add actual funding only if raw edge survives

## Required report
Overall and per Track / direction / symbol / year:
- trades
- win rate
- total R / average R
- profit factor
- max drawdown R
- max losing streak
- TP1 / TP2 hit rate
- Runner activation rate
- average / median hold
- entry fill / expiry counts

## Research rule
No parameter changes inside v0.1 after results are inspected.
Parameter sweeps, if warranted, must be a new version.
