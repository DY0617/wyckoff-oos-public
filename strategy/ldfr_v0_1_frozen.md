# LDFR v0.1 — Frozen Baseline

Frozen before the first backtest. Do not edit these thresholds in-place after seeing results; create a new version for any change.

## Thesis

A failed liquidity break can identify trapped flow. We only trade when that sweep is followed by directional displacement, a measurable three-candle fair-value gap, a retrace into the gap, and renewed confirmation in the higher-timeframe trend direction.

This is a fully mechanical formalization of the public liquidity / FVG / fakeout style concepts discussed in the source material. It is not a claim that discretionary Order Blocks or FVGs have an intrinsic edge.

## Market and timeframes

- Baseline market: Binance USDT-M perpetuals.
- Baseline symbols: BTCUSDT, ETHUSDT.
- Higher-timeframe regime: fully closed 4H candles.
- Setup / execution timeframe: fully closed 1H candles; entry at the next 1H open.
- One open position per symbol.

## Long setup

1. **4H regime**: close > EMA50, EMA20 > EMA50, EMA20 5-bar slope > 0.
2. **Sell-side liquidity sweep**: current 1H low < prior 20-bar low AND current close > that prior 20-bar low.
3. **Bullish displacement within 3 bars**:
   - range >= 1.50 × Wilder ATR14,
   - body / range >= 0.60,
   - bullish close,
   - CLV >= 0.75.
4. **Bullish FVG on the displacement bar**: current low > high two bars earlier; gap size >= 0.15 × ATR14.
5. **Retest**: within 8 bars, price touches the FVG midpoint and does not close through the lower FVG edge.
6. **Confirmation**: within 2 bars after the retest, close > previous 1H high. Re-check the 4H regime.
7. **Entry**: next 1H open.
8. **Stop**: sweep low - 0.15 × ATR14 measured at confirmation.

## Short setup

Exact inverse of the long setup.

## Management

- TP1: +1.50R, exit 50%.
- After TP1: move the remaining stop to break-even.
- TP2: +3.00R, exit the remaining 50%.
- No time stop in v0.1.
- Same-bar ambiguity is conservative: stop is evaluated before profit targets.
- Costs: 4 bps fee + 2 bps slippage per fill.
- Position sizing: fixed 1R reference risk per trade, before costs.

## Validation protocol

No parameter search is allowed before recording the baseline result.

- Development label: 2021-09-28 through 2024-09-27.
- Validation label: 2024-09-28 through 2025-09-27.
- Untouched OOS label: 2025-09-28 through 2026-09-27.

Because v0.1 is pre-frozen rather than optimized on the development interval, all three intervals are descriptive on the first run. Any tuning informed by these results must be named v0.2+ and must not retroactively redefine v0.1.

Primary diagnostics: trade count, expectancy (avg R), profit factor, total R, max drawdown in R, maximum losing streak, TP1/TP2 rates, long/short split, yearly stability, and symbol stability.
