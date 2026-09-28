# LDFR v2.2 — Unseen8 OOS

Exact frozen v2.2 rules. No strategy changes.

## Test symbols never used in prior LDFR design/tuning
- AVAXUSDT
- ATOMUSDT
- NEARUSDT
- AAVEUSDT
- ALGOUSDT
- VETUSDT
- THETAUSDT
- SANDUSDT

BTCUSDT is downloaded only as the broad-market and relative-strength benchmark; it is not included in OOS trading results.

All v2.2 parameters remain unchanged, including:
- BTC daily EMA200 market gate
- symbol daily EMA50/EMA200 trend
- 30D relative strength vs BTC
- ER20 >= 0.30
- 4H regime
- intact structural liquidity sweep
- MSS displacement
- FVG and midpoint retest
- structural stop
- TP1/BE/TP2
- costs and conservative intrabar ordering

Purpose: untouched cross-symbol validation of v2.2 after the strong 14-trade design-universe result.
