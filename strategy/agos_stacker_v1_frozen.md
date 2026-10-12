# AGOS-inspired Bounded Stacker v1 — frozen pre-backtest

Date: 2026-10-12. Stage: **research only**. This is an original, public-concept
derivative, **NOT AGOS proprietary source or a claim of replicating their settings**.

## Source vs assumptions
AGOS public auto-trading page (https://agos.me/auto-trading) describes:
- recompute a band and trend on each completed candle;
- a first entry when price breaks outside a band;
- additional staged orders as price moves adversely;
- close the cycle together above the resulting long average price.
It does NOT disclose the exact band formula, add spacing, sizes, TP/SL,
leverage, recovery rules, cross-asset risk or true historical equity curve.

**All numerical settings below are our research assumptions.**

## Three frozen variants
1. `single`: one entry, same initial hard-stop distance and full 0.75% cycle
   risk budget, same ATR profit target; NO adding.
2. `stacker`: 4 staged fills with an identical 0.75% total planned cycle loss.
3. `stacker_regime`: identical ladder and sizing, but trade only when the
   previous completed daily benchmark & asset close are above EMA200 for LONG,
   or below EMA200 for crypto SHORT. The regime is checked at signal scheduling.

The purpose is to test whether averaging adds true edge versus a comparable-risk
single entry, and whether the broad-market trend gate improves stability.

## Data & closed-bar rules
- Reuse proven ARM data adapters in the same isolated research branch.
- Stock RTH US equities and ETFs: existing stock29/30 universe, 09:30–16:00 ET.
  Evaluate 2021-09-28 to 2026-04-01 exclusive. SPY is the benchmark only.
- Crypto: BTCUSDT and ETHUSDT Binance Vision historical USDT-M hourly OHLCV
  24/7, evaluate 2021-09-28 to 2026-09-28 exclusive.
- Stock LONG only, crypto LONG and SHORT, one concurrent cycle per symbol.
- 4H buckets: crypto complete UTC 4h; stock RTH 09:30–13:30 then
  13:30–16:00 (short second bucket). A setup occurs at fully CLOSED 4H signal
  and entry at the next 1h bar open.
- Band = SMA20 ± 2 * population-std(last 20 completed 4H closes), including
  the signal bar (no incomplete candles). Signal = new close beyond lower
  band (LONG), or new close above upper band (crypto SHORT), whereas prior
  completed 4H close was inside its own prior band.
- ATR14 uses Wilder RMA of completed 4H true ranges at signal bar.
- One-shot entry on next available 1H open, no pending extended limit.

## Hard limits on the ladder
- First fill at observed next 1H open; absolute initial stop fixed at
  entry −4.75 ATR (LONG) or entry +4.75 ATR (SHORT).
- Planned adds at first-entry ±1, ±2, ±3 ATR adverse.
- Notional weights per stage: 1.0 / 1.25 / 1.5 / 1.75.
- All quantities share ONE total risk budget: 0.75% of current
  marked-to-market portfolio equity if all fills reach the fixed stop.
- Additional **gross notional cap**: full proposed ladder <=70% of portfolio
  equity (no unlimited doubling or high leverage).
- Maximum simultaneous open cycles: two (maximum planned risk 1.5%
  excluding gaps). Position sizing recalculated at first entry only.
- TP after each fill: position volume-weighted average price ±0.70 ATR
  in profitable direction (single exit for entire remaining quantity).
- Strict exit STOP-first on OHLC bar ambiguity. If an in-bar adverse move
  reaches several adds and the stop, account for those adds BEFORE stop
  loss; if the bar OPEN already gaps beyond a pre-existing stop, exit at
  open without additions. No profit target fill on the entry or add bar.
- No additions after fourth stage. Forced exit: stock after 70 RTH
  1H candles (~10 sessions), crypto after 336 hours (=14 days).
- Transaction cost 4bp fee plus 2bp slippage per side of each fill;
  crypto historic 8h settlement funding charged with hourly close
  as approximate mark, proportional to running quantity.
- Synthetic stop does not enforce real futures margin, funding mark, taxes
  or dynamic liquidations. NEVER connect to live orders in this version.

## Reporting / anti-selection requirements
- Single multi-symbol chronological simulator with portfolio-wide cap and
  hourly marked-to-market floating PnL in equity series (NOT realised-only).
- Total PnL, PF, win ratio, MTM max drawdown, worst open floating loss,
  fee/funding, year/symbol split, dependence on best 10 trades, STOP/TIME exits.
- Compare **all three** before selecting; do not optimize on this first sample.
- Main branch and production code left unchanged.
- Next validation: unseen symbols, disjoint OOS periods, stock corporate
  actions, margin/basis and adverse-funding / higher slippage stresses.
- Limits: hourly close MTM excludes momentary intrabar extremes; a liquidity
  gap can lose substantially more than the planned 0.75% per cycle.
