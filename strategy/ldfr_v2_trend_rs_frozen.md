# LDFR v2.0 — Trend/Relative Strength + Liquidity Execution

Frozen before first v2 result.

## Design principle

Directional selection and entry execution are separated.

**Alpha / selection layer**
1. Use only prior completed UTC daily candles.
2. Broad market direction:
   - long only if BTC daily close > BTC EMA200.
   - short only if BTC daily close < BTC EMA200.
3. Symbol trend:
   - long: close > EMA50 > EMA200 and 10-day EMA50 slope > 0.
   - short: exact inverse.
4. Relative strength:
   - alt long: 30-day return > BTC 30-day return.
   - alt short: 30-day return < BTC 30-day return.
   - BTC is exempt from self-relative-strength comparison.

**Local alignment**
- Keep the existing frozen v1 4H EMA20/EMA50 regime.

**Execution layer**
- Keep v1 structural liquidity definition, sweep penetration, MSS displacement, FVG formation window, midpoint retest entry, structural stop, TP1/BE/TP2 management, conservative intrabar ordering, and costs unchanged.

## Why

v1 improved the original loose 20-bar-extreme sweep concept but failed unseen-symbol OOS. v2 tests whether liquidity/FVG works better as execution after a directional edge has already been selected by slower trend and relative strength.

This is a discovery test on the original eight design symbols. No threshold search is performed. If promising, the exact frozen v2 rules must be applied to the previously unused eight-symbol universe without modification.
