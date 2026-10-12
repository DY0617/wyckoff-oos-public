# Bounded Stacker v2 — structural TP/SL research specification

Frozen before results, 2026-10-12. Distinct from AGOS proprietary methods.
A direct extension of our AGOS-inspired Stacker v1 *research*; NO exchange
automation, Telegram, Supabase, or production changes.

## Hypothesis
The v1 bounded Stacker had high realised win rate but weak/negative net PnL:
5y crypto `stacker_regime`: 508 cycles, 91.34% winners, -9.54% net,
MDD 11.20%, PF 0.707. US stocks 4.5y: 366 cycles +0.35%, PF 1.021.
Test the hypothesis that replacing arbitrary ATR exits with *completed*
4H support/resistance and 4H EMAs changes the reward/loss asymmetry.

## Frozen comparison (same signal, market filter, risk, ladder, costs)
- `baseline`: exact original Stacker regime gate and fixed
  stop 4.75 ATR beyond first fill / target avg+0.7 ATR.
  Due to a portfolio chronology fix the resulting numeric baseline can
  differ from historical Stacker v1 reporting; run both within one engine.
- `sr_ema`: STOP behind recently CONFIRMED same-side swing pivot, TP at
  the closest qualifying 4H EMA20/EMA50 favorable to average entry.
- `sr_sr`: STOP behind confirmed support/resistance pivot, TP near the
  closest qualifying opposite-side pivot resistance/support.
- `hybrid`: STOP behind confirmed pivot OR at the EMA50 +/- 6 ATR envelope
  (choose the closest structurally valid stop), TP the closest valid
  4H EMA20/50 or opposing swing resistance/support.

**All variants use exactly the same initial Bollinger entry logic and
yesterday-only daily EMA200 regime gate** (long stock/crypto, short crypto).

## Causal structure
- 4H band signal: closed 4H close crossing outside Bollinger
  SMA20 +/- 2 SD; enter at next available 1H OPEN.
- Confirm 4H pivot high/low using 2 fully closed candles to LEFT and
  2 fully closed candles to RIGHT, always at/before signal bar. Scan
  prior 90 completed 4H candles. No intraday future-derived pivots.
- Frozen EMA20, EMA50 evaluated at the confirmed 4H signal close.
- For LONG STOP, choose pivot low minus 0.25 * ATR (or EMA50 minus
  6 ATR for `hybrid`). For SHORT invert support/resistance and signs.
  Enforce 3.5 to 8.0 ATR initial stop distance. Entire four-fill
  ladder of 0/1/2/3 ATR stays strictly *inside* initial hard stop.
- For LONG TP, choose EMA20, EMA50 or pivot high minus 0.15 ATR
  (where the mode permits); for SHORT choose counterpart low plus
  0.15 ATR. Must be directionally profitable: from first entry
  between +0.5 and +8.0 ATR. Freeze as ABSOLUTE structural price
  at FIRST entry; do not recompute with future EMA/pivots.
- After adding at 1,2,3 ATR adverse distance, preserve the
  frozen absolute structural target. VWAP and fee ledger update;
  there is NO aimless target-ratchet based on future structures.
- **Skip** a new cycle rather than fabricate a support/EMA or target
  when no valid structure exists. This changes sample size relative
  to baseline, so compare sample sizes and selection effects.
- Entire predefined four-fill loss to initial stop <=0.75%
  marked equity (gross, BEFORE fees/gaps) with full cycle notional
  capped at 70% of current marked equity; 2 simultaneous cycles.
  No uncontrolled averaging, no 30x leverage.
- Exit STOP first on OHLC ambiguities; stop gaps use actual OPEN;
  no TP fill within entry/add hour. Max 14 calendar days crypto or
  70 RTH 1H bars stocks (~10 sessions).
- Commissions + slippage 6bps each side, additional 4bps/side
  stress scenario; crypto Binance historical funding paid by side.
- Chronology fix compared to older Stacker v1: new entries are
  admitted at the hour OPEN from previously completed marks
  BEFORE any current-hour high/low, exits or close can be known.

## Fixed research windows
- US selected stock/ETF research universe, RTH session only:
  2021-09-28 .. 2026-04-01 exclusive.
- BTCUSDT/ETHUSDT USDT-M Binance 1H:
  2021-09-28 .. 2026-09-28 exclusive.
- Initial simulated cash: 20,000 USD/USDT; never combine stock/crypto
  accounts into one performance claim.
- Compare win rate, net%, PF, 1H-close marked-to-market MDD,
  large loss contribution, annual, symbol and cost stress,
  trade counts plus structural-source attribution.

## Execution and reliability caveats
- This is **research only**; do not deploy if PF weak or few observations.
- All parameter settings were chosen prior to new backtest outputs.
  Do not retrospectively claim these known dates as untouched OOS.
- Short horizon structure, EMA50 +/- 6 ATR envelope, 90 4H lookback and
  3.5..8 ATR stop limits are OUR research assumptions, NOT AGOS settings.
- Portfolio MTM is at hourly close and may miss intrabar deep DD.
- The stock set is survivorship-/postselection-biased; corporate-action
  heuristics and underlying-to-futures slippage are approximate.
- Crypto exchange funding marked at hourly close is a proxy, and no
  liquidation/true margin/stressed order book simulator is in scope.
