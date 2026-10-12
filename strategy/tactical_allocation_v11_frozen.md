# V11 — strategic capital allocation, locked BEFORE results

Frozen 2026-10-12. Independent strategy research, NOT proprietary
AGOS or the earlier Stacker/Wyckoff rule set, NOT investment advice.
Do not modify live trading, production Track B/E, Supabase, or Telegram.

## Hypothesis vs previous versions

Entry First v1-v10 tried to forecast short-lived intraday turning
points, then repeatedly mined the same 2021-2026 history. No
stable after-fee advantage generalised. We now test strategic
asset allocation over months: **what assets to HOLD, in what
size, and when to hold ZERO-risk CASH**, rather than another
high-frequency technical pattern.

Seven **predeclared**, directly comparable monthly long-only
strategies; investible assets funded entirely by cash:

1. `benchmark_hold`: BUY SPY (for stock cohort) or BTCUSDT
   (crypto underlying-price proxy) once and never rebalance;
   risk/return passive opportunity-cost comparator.
2. `equal_hold`: equal-weight every traded universe member
   once at first evaluation month and never rebalance.
3. `equal_monthly`: equal-weight the same cohort every month
   at its first actual trading-day OPEN (100% allocated).
4. `absolute_trend`: hold each original universe member at
   1/N when prior completed day close > EMA200 AND positive
   63-observation price return; otherwise that slot remains
   in cash. No reallocation of rejected slots.
5. `momentum_top`: among assets passing the SAME prior-day
   absolute trend criterion, rank previous 63-day returns
   and hold the best up to 3 crypto / 6 US stock names,
   each at 1/slot allocation. Fewer than slot count
   means unused capital remains in cash.
6. `risk_managed`: same ranking and long-only qualification,
   then size positions by prior 60-day realized log-return
   volatility with a fixed desired approximate portfolio
   annualised risk target of 18% crypto / 12% US stocks.
   Each weight is min(35% crypto or 20% stock,
   targetVol/(assetVol*sqrt(maxSlots))).
   Rescale weights proportionately only if aggregate >100%.
   Variance/correlations, future regimes and broker margin
   are NOT estimated. Unused weight remains cash.
7. `risk_managed_gate`: same as 6 but only invest when
   the previous COMPLETED DAILY SPY/BTC benchmark itself
   has close>EMA200 and 63-day positive return. If false,
   stay in cash until next scheduled monthly rebalance.

No parameters are tuned per symbol or per calendar subperiod.
EMA200/63-day rank/60-day volatility/benchmark gate and
three risk sizes were frozen before computing results.

## Event-time execution and unborrowed money

- Indicators at month-open T are from strictly earlier
  completed DAY T-1 or before. Today's open used solely for
  execution and today close used solely for end-day marking.
- Trade only on first available trading day of new month;
  all prior positions sold to desired weights BEFORE any
  buy using same day's actual OPEN quote.
- Total gross purchase amount plus paid fees <= available
  realised CASH after reserving already-open holdings'
  purchase notional (never implicit stock leverage).
  Fractional shares permitted as a generous execution bound.
- No shorting, futures leverage, margin or borrowing,
  liquidation, dynamic averaging down, or SL re-anchoring.
  No synthetic lookahead fills. Buy-sell cost each execution
  side nominal 6bps including estimated slippage; compare
  10bps and severe 20bps/side.
- Skip trivial rebalance trades below 1% of equity;
  buy/hold starts once. Portfolio max exposure can never
  exceed 100% of contemporaneous total equity, with
  nonnegative cash. Cash yield is held at 0%; realistic
  interest income would improve cash alternatives.
- Day-close MTM returns and DD, CAGR, turnover, time
  invested and annually compounding portfolio equity
  reported. Trade ledger and curves fully archived.

## Predeclared separate cohorts

A. BTC/ETH, data 2021-09-28..2026-09-28 exclusive.
B. BTC/ETH/BNB/SOL/XRP, data 2022-06-01..2026-09-28
   exclusive. BTC among traded cohort, unlike prior
   study that treated it as benchmark only.
C. Selected 29 surviving US stock/ETF names + SPY baseline,
   RTH 2021-09-28..2026-04-01 exclusive.
All model accounts start at 20,000 USD/USDT independently,
520 prior days warmup.

**IMPORTANT CRYPTO CONVENTION:** available price adapter is
Binance USDT-M perpetual FUTURES OHLC, but this engine
evaluates SPOT-LIKE cash-funded long ownership to isolate
allocation choices. NO historic perpetual funding,
liquidation, contract margin or mark-price mechanics is
included. Therefore the results are a *price-movement
proxy* and MUST NOT be presented as real spot or
executable Binance futures PnL. Separate true spot data
and order cost/funding study is needed before live use.

## Acceptance and risks

Report seven whole-cohort arms, benchmark vs each, CAGR,
1D-close max drawdown, invested exposure, fees and turnover,
annual subperiods, 10bps / 20bps per-side fee stress.
Return >0 alone is not success: require enough diversified
exposures, superior risk-adjusted benchmark result,
non-concentrated profitable years and a fresh prospective
calendar date set. If only "cash" yields smooth profile,
compare its REAL opportunity cost.

Examine failures transparently. This SAME historical period
was already used heavily in previous v1-v10 research;
it is NOT an untouched OOS regardless of freezing v11.
US portfolio has selection/survivorship and stock-split/
dividend issues. The result excludes interest on cash,
intraday crashes, spreads varying over time, settlement
restrictions, taxes and rebalancing execution impact.
Risk-scaled target is an approximation, not guaranteed
future volatility; correlated crashes can overwhelm it.

No production risk parameter, orders, alerts or
Wyckoff code may change.
