# SR Reclaim v1 — Frozen Research Rules

Status: research / frozen baseline  
Asset class: Binance USDT-M perpetual  
Backtest window: 2021-10-01 through 2026-10-01 (exclusive end)  
Signal timeframe: 4H  
Execution timeframe: 15m

## 1. Zone construction

Support/resistance is modeled as a neutral price zone, not as a permanent support or resistance label.

- Source timeframes: 4H and 1D.
- Pivot detector: the repository's existing ATR ZigZag with 1.5 ATR reversal.
- Low pivot level: lower candle-body edge = `min(open, close)`.
- High pivot level: upper candle-body edge = `max(open, close)`.
- New pivot levels are merged when they lie within 0.45 ATR of an existing zone center.
- Baseline half-width is 0.30 ATR and is capped at 0.65 ATR.
- A zone becomes eligible only after at least 2 distinct touches.
- Touches less than 12 hours apart are treated as the same interaction to reduce 4H/1D double-counting.
- Zones older than 365 days since the most recent underlying pivot are ignored.
- Only pivots already confirmed before the current 4H signal bar opens may construct or strengthen a zone.

The same neutral zone can act as support when price approaches from above and resistance when price approaches from below. This naturally allows S/R flips without relabeling historical zones.

## 2. Long setup

A long signal requires all conditions below on a completed 4H candle:

1. Previous 4H close is above the candidate zone.
2. Current candle trades into the zone and reaches at least the zone center.
3. Current candle closes back above the zone high.
4. Close-location value (CLV) is at least 0.65.
5. Current close exceeds the highs of the prior 2 completed 4H candles.
6. EMA20 >= EMA50.
7. EMA50 is higher than it was 6 bars ago.
8. Initial stop distance is between 0.35 ATR and 2.00 ATR.
9. The nearest pre-existing opposite zone above price provides at least 2.0R of room.

## 3. Short setup

Mirror of long:

1. Previous close below candidate zone.
2. Current candle trades into the zone and reaches at least zone center.
3. Current candle closes back below zone low.
4. CLV <= 0.35.
5. Current close breaks the lows of the prior 2 completed 4H candles.
6. EMA20 <= EMA50.
7. EMA50 is lower than 6 bars ago.
8. Stop distance 0.35–2.00 ATR.
9. Nearest pre-existing opposite zone below price provides at least 2.0R.

## 4. Entry and invalidation

- Entry: market at the first 15m open after the confirmed 4H candle closes.
- Reject the trade if the opening gap from the signal close exceeds 0.25 ATR.
- Long SL: below the lower of the signal low and zone low, minus 0.15 ATR.
- Short SL: above the higher of the signal high and zone high, plus 0.15 ATR.
- After actual fill, the trade is rejected if the opposing zone no longer provides at least 2.0R.

## 5. Profit taking

- TP1: +1.0R, close 50%.
- After TP1: stop remaining 50% at actual entry (breakeven).
- TP2: nearest edge of the next pre-existing opposite S/R zone.
- Maximum hold: 24 x 4H bars (96 hours).
- Same zone cannot generate a fresh signal for 6 completed 4H bars.

## 6. Execution realism

- Existing repository costs are reused: 4 bps fee + 2 bps slippage per fill.
- Execution is evaluated on 15m candles.
- Conservative stop-first ordering is used whenever stop and target could both be touched within the same 15m candle.
- No pivot or zone may use information that was not known at the signal time.

## 7. Purpose of v1

This is intentionally not optimized. v1 tests whether a strict, mechanized version of the video's core idea has standalone edge:

`HTF body-price zone -> sweep/retest -> close reclaim -> local BOS -> trend confirmation -> next S/R target`

If the baseline is promising, subsequent tests should vary one axis at a time (zone width, minimum touches, confirmation strength, trend filter, target-R requirement) and then use symbol/time OOS validation.
