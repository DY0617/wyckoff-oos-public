# Elliott Wave 3 v4 — Stock OOS25 20Y Frozen Stress Test

Frozen strategy: US RTH 1H LONG-only Elliott v3 (5-wave impulse + ABC + B-wave breakout), with the exact same ATR pivot, stop, target, cost, entry-validity and max-hold rules used in the successful fresh OOS25 test.

## Long-horizon test
- Historical window: 2006-04-01 through 2026-04-01.
- Five non-overlapping 4-year shards.
- 400-day warmup per shard.
- Same 25 fresh-OOS individual US equities; no ETFs, COIN or MSTR.
- BKNG uses PCLN history before the 2018 ticker change.
- RTX is not backfilled through UTX; RTX history starts at the post-merger ticker era.
- Common split factors are back-adjusted.

## Descriptive regime analysis
SPY completed RTH daily data only:
- BULL: close > EMA200 and EMA200 higher than 20 sessions ago.
- BEAR: close < EMA200 and EMA200 lower than 20 sessions ago.
- MIXED otherwise.

Regime is descriptive only and never filters a trade.

## Stability analysis
- Per-year metrics.
- Non-overlapping 4-year folds.
- Rolling 5-year metrics.
- Frozen-rule walk-forward table: prior 5 years as stability context, next year as test; no parameter selection or retraining.

This is a historical stress test, not pristine temporal OOS. The present-day OOS25 universe projected backward has survivorship bias.
