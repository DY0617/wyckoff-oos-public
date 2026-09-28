# LDFR v2.1 — Cross-Sectional Relative Strength + Liquidity Execution

Frozen before first v2.1 result.

## Single change vs v2.0

v2.0 used a binary relative-strength test:
- alt long if 30D return > BTC 30D return
- alt short if 30D return < BTC 30D return

v2.1 replaces only that rule with a cross-sectional rank:
- LONG eligibility: top 3 of the 8-symbol universe by prior-completed-daily 30D return.
- SHORT eligibility: bottom 3 of the same universe.
- The symbol must still satisfy its daily EMA trend condition.
- BTC broad-market EMA200 gate remains unchanged.

Everything else is unchanged:
- completed daily data only
- daily trend definition
- 4H local regime
- intact swing liquidity
- sweep penetration
- MSS displacement
- FVG definition/timing
- midpoint retest entry
- structural stop
- TP1/BE/TP2
- conservative 1H intrabar ordering
- costs
- one position per symbol

## Why

v2.0 improved drawdown and losing streaks, but its binary "stronger/weaker than BTC" selector still admitted weak members such as SOL. Cross-sectional ranking makes the selection layer explicitly choose leaders and laggards rather than merely comparing each alt with one benchmark.

No rank-size search is performed. Top/bottom 3 is frozen before testing.
