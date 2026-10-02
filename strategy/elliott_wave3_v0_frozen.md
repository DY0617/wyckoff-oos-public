# Elliott Wave 3 v0 — Frozen Research Spec

This strategy is independent from Wyckoff / Track B. It tests only a mechanically defined wave structure.

## Market and data
- Binance USDT-M perpetuals
- BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT
- Signal timeframes: 1H and 4H
- Execution: 15m bars
- Evaluation: 2021-10-01 through 2026-10-01 exclusive
- Fees: 4 bp per fill
- Slippage: 2 bp per fill

## Pivot definition
Realtime ATR ZigZag:
- ATR(14)
- reversal threshold: 1.50 ATR
- a pivot is not usable until the reversal bar closes and confirms it
- therefore no future-window pivot labeling or repaint lookahead is allowed

## Wave 1 / Wave 2 setup
Long:
- confirmed pivots L -> H -> L
- Wave 1 length >= 2.00 ATR
- Wave 2 low must remain above Wave 1 origin
- Wave 2 retracement: 0.382 to 0.786 of Wave 1
- Wave 2 duration <= 2.50 x Wave 1 duration

Short is exactly symmetric.

## Entry
- Entry is the Wave 1 extreme breakout.
- The order becomes active only after the Wave 2 pivot is confirmed.
- Order validity: 12 signal bars.
- If Wave 2 invalidation / stop is hit before entry, cancel the setup.

## Stop and targets
- SL: Wave 2 extreme +/- 0.15 ATR.
- TP1: Wave 2 extreme +/− 1.000 x Wave 1 length.
- TP2: Wave 2 extreme +/− 1.618 x Wave 1 length.
- Exit 50% at TP1.
- After TP1, move the remaining stop to breakeven.
- Exit remaining 50% at TP2.
- Maximum hold: 48 signal bars.

## Conservative execution convention
When price ordering inside a 15m candle is unknowable, adverse outcomes are assumed first:
- stop before target
- invalidation before an intrabar breakout entry
- breakeven before TP2 when both become possible in the same bar

## Primary diagnostics
Report:
- trades
- Long / Short split
- win rate
- total R
- average R
- profit factor
- max drawdown in R
- max losing streak
- TP1 / TP2 hit rates
- average holding time
- 1H vs 4H
- symbol breakdown
- Wave 2 retracement buckets: 0.382–0.500 / 0.500–0.618 / 0.618–0.786
- yearly results

This file freezes v0. Any parameter changes should be tested as a new version rather than silently changing this baseline.
