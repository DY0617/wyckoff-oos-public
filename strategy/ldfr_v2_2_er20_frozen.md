# LDFR v2.2 — Trend Efficiency Filter

Frozen before first v2.2 result.

## Single change vs v2.0

Add Kaufman-style 20-day efficiency ratio to the existing daily trend selector:

ER20 = abs(close[t] - close[t-20]) / sum(abs(close[i] - close[i-1]), 20 daily steps)

Require:
- ER20 >= 0.30

The filter is direction-agnostic; direction still comes from the existing daily EMA trend, BTC regime, relative strength vs BTC, 4H regime, and structural liquidity execution.

Everything else is unchanged from frozen v2.0:
- BTC daily EMA200 market gate
- symbol daily EMA50/EMA200 trend
- 30D return vs BTC relative strength
- 4H local regime
- intact swing liquidity
- sweep
- MSS displacement
- FVG
- midpoint retest entry
- stop and TP management
- costs and conservative intrabar ordering

## Why

v2.0 reduced drawdown materially but still allowed trend-looking, high-noise regimes. ER measures directional efficiency rather than trend magnitude and is scale-free across symbols.

No ER threshold search is performed. 0.30 is frozen before testing.
