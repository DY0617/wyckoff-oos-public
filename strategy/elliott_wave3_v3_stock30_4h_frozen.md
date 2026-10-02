# Elliott Wave 3 v3 — Stock30 4H Cross-Asset OOS Frozen Spec

This test transfers the existing crypto v3 logic to US stocks without tuning on stocks.

## Universe
Existing Stock30 research universe:
AAPL, AMZN, AVGO, MSFT, MU, AMD, INTC, JPM, NFLX, V, COST, GOOGL, META, NVDA, QQQ, TSLA, UBER, WMT, AMAT, CAT, HD, ORCL, SPY, TSM, CRM, CSCO, DIS, IBM, COIN, MSTR.

## Signal
Exact v3 Elliott rules:
- confirmed 5-wave standard impulse
- confirmed ABC correction
- entry = B-wave extreme breakout after C confirmation
- ATR ZigZag reversal = 1.50 ATR
- SL = C extreme +/- 0.15 ATR
- TP1 = C +/- 1.0 x macro Wave 1 impulse
- TP2 = C +/- 1.618 x macro Wave 1 impulse
- 50% at TP1, remaining stop to breakeven, remaining 50% at TP2
- same 4 bp fee + 2 bp slippage per fill

## US RTH adaptation
- 15m execution uses RTH cash bars only.
- Signal sequence uses the existing stock research convention:
  - 09:30-13:30 ET = 4h bar
  - 13:30-16:00 ET = 2.5h stub
- Entry validity = 12 signal bars, counted in signal bars (not elapsed wall-clock hours).
- Max hold = 48 signal bars, counted in signal bars.
- Common stock split ratios are detected and prior OHLC is back-adjusted.

This is a cross-asset OOS test. No stock-specific parameter changes are permitted before reading results.
