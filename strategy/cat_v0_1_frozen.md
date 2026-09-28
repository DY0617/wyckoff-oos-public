# CAT v0.1 — Cross-Asset Trend

Frozen before first result.

## Goal
One fully mechanical trend strategy usable on both crypto perpetual futures and U.S. stock futures/stock-linked futures.

No Wyckoff, FVG, liquidity sweep, relative-strength ranking, or discretionary chart pattern is used.

## Signal timeframe
Completed daily bars only.

For stocks, signals are generated from regular-session underlying equity/ETF bars and are intended to drive futures execution.
For crypto, UTC daily bars are used.

## Direction
For every completed daily bar compute:
- 20-day return
- 60-day return
- 120-day return
- EMA200
- ATR14

LONG regime:
- at least 2 of {ret20, ret60, ret120} are > 0
- close > EMA200

SHORT regime:
- at least 2 of {ret20, ret60, ret120} are < 0
- close < EMA200

## Entry
LONG:
- completed signal-day close > highest high of the prior 20 completed daily bars
- enter at next daily session open

SHORT:
- completed signal-day close < lowest low of the prior 20 completed daily bars
- enter at next daily session open

Only one open position per symbol.

## Risk / exit
- Initial stop: 2.0 ATR14 from actual entry fill.
- No fixed take-profit.
- LONG trailing stop after each completed daily close:
  max(previous stop, highest completed close since entry - 3.0 ATR14)
- SHORT trailing stop:
  min(previous stop, lowest completed close since entry + 3.0 ATR14)
- No time stop.
- No pyramiding.

If a new session gaps beyond the active stop, exit at the session open.
Otherwise a stop touch exits at the stop.
Trailing stops are updated only after the session closes.

## Costs
For comparability in this discovery test:
- fee: 4 bps per fill
- slippage: 2 bps per fill
- charged once per entry/exit fill

## Position normalization
Backtests report return in R:
- 1R = initial stop distance.
Portfolio sizing is intentionally separated from signal-edge testing.

## Discovery universes
Crypto:
BTC, ETH, BNB, SOL, XRP, ADA, DOGE, LINK USDT-M perpetuals.

Stocks:
30 liquid U.S. equities/ETFs from the existing RTH dataset.
The stock backtest uses underlying RTH prices as the historical signal/execution proxy because the corresponding stock-futures contracts do not have equivalent multi-year history.

## Rule
Do not alter v0.1 after seeing results. Any change must be versioned separately.
