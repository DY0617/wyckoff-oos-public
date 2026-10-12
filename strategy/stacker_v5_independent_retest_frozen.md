# Stacker v5 — independent post-TP retest research, frozen before execution

Date: 2026-10-12. Not AGOS proprietary strategy. Experimental branch only.
No trading orders, account secrets, Supabase production or Telegram changes.

## Motivation
Stacker v4: BTC/ETH 5-year market static +0.67%, PF1.026; all profit recycling
variants underperformed. US stock 4.5-year: old pivot-supported rebuy +2.26%
but 2022 losses were high. Re-entry on mere pullback to a fixed price is NOT
a strong independent entry signal. Do NOT tune old DCA prices on known results.

## Comparison frozen v5
- `control`: same structural parent initial BB(20,2) crossing, EMA200 previous
  complete daily gate, confirmed 4H S/R SL, 4H EMA20/50 TP, no re-entry.
- `retest`: after the *completed parent TP* close, wait at most 48 1H crypto
  or 14 RTH 1H stock candles. Price touches original TP - 1 original ATR
  for long / +1 ATR short; the *closed* 1H candle has directional CLV>=0.65,
  closes 0.25 current ATR beyond the retest level and reclaims its EMA20.
  Only consider child at the NEXT hour OPEN.
- `retest_htf`: above with prior completed 4H EMA20 directional slope and
  price relative to EMA20 aligning with child side.
- `retest_htf_barrier`: additionally reject child if prior confirmed opposing
  4H S/R pivot is closer than 1.5 x proposed stop distance to the entry.
- At most ONE fresh child trade per closed parent TP. Unlike v3/v4, the parent
  is completely liquidated and its SL is NEVER extended afterward.

## Independent child
- The child is NOT a partial hedge, not an average-down step, and has its
  own stop at the prior six **confirmed** 1H swing extreme +/-0.25 current
  1H ATR. Range 0.75..3 ATR initial stop distance. Entry at next hour OPEN
  (not same signal candle); reject gap-chase >0.75 ATR beyond retest signal
  close. Independent +2R TP, stop moved to entry after CONFIRMED 1H CLOSE
  beyond +1R; effective next hour only.
- Fresh risk budget 0.375% current marked account equity, fee-inclusive at
  a stressed 10bps/side estimate; <=70% equity notional per child;
  global maximum 2 concurrent positions.
- Time exit 72 1H crypto, 21 RTH stock hours. In ambiguous 1H bars, stop
  wins target; genuine stop gap exits at actual hour open.
- Transaction cost nominal 6bps/side, stressed 10bps/side; historical
  Binance USDT-M funding proxy charged using settlement timestamps and
  1H-close notional. MDD includes open positions at 1H CLOSE, not tick extremes.

## Evaluation design
- 2021-09-28 .. 2026-09-28 exclusive: BTC and ETH 1H USDT-M;
  2021-09-28 .. 2026-04-01 exclusive: preselected US equity RTH universe.
- 520 calendar days warmup. Reuse existing independently checked adapter;
  compare all 4 frozen variants, report parent and child contributions
  SEPARATELY, trade counts, child PF, total PF and net return, MTM MDD,
  annual split, symbol split and transaction cost stress.
- Holdout NOT claimed from previous backtests; these dates and markets are
  already seen in v1-v4. This is an in-sample hypothesis comparison only,
  and fresh unseen out-of-sample data is needed before deployment.
- Baseline may differ slightly from earlier reports due to chronology and
  size differences. Comparisons within a single v5 engine are definitive.
- Important limits: current equity universe survivor/post-selection bias,
  approximate stock corporate actions, Binance funding close-mark proxy,
  incomplete intrahour path, missing liquidation/depth/margin/taxes.

Research-only acceptance: child PF must exceed 1 after costs and across
multiple independent subperiods; total portfolio must improve *also*
under cost stress without outsized MDD, with broad symbol distribution.
No live deployment solely on aggregate backtest profit.
