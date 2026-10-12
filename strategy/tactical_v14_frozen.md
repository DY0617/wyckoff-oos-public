# Tactical v14 — adaptive risk-on capital, not another entry indicator

Frozen on 2026-10-12 **before viewing any v14 market backtest results**.
Research only. DO NOT promote to live orders/production without
true forward OOS and exchange execution validation.

## Problem / economic hypothesis

V11-v13 directionally succeeded at limiting loss, but tended to
sit 75–85% in zero-yield cash. Daily cap rebalancing nearly
doubled transaction count while lowering max closing DD only
~0.4–0.6 percentage points. Do not iterate on the overmined
old entry/stop/TP candles. Test whether higher *intentional*
gross investment DURING robust market uptrends, including
more diversified leaders, can raise long-run growth for
acceptable incremental downside.

We keep the original monthly next-observed-session OPEN
execution, strictly prior COMPLETED DAILY 200 EMA,
63-day momentum, 60-day realized volatility, cash-only
notional and equal fee/price source. No selling trigger based
on current day's prices. No short, leveraged futures,
options, intraday hidden liquidation or reinvestment
of unavailable buying power.

**All modes below are FROZEN A PRIORI** and use the same
risk-on gate: at previous close the benchmark BTC/SPY
must be above EMA200 and have a positive 63-day return;
otherwise weights={} (100% cash until next month).
Tradable asset selection also requires its prior close
>EMA200 and prior 63-day return positive. Rank selected
assets by 63-day positive returns, descending, top 3
crypto or top 6 US-stock holdings unless otherwise noted.

## 6 new hypothesis arms

1. `v14_momentum_55`: equal allocate **55% gross**
   across the best eligible top3/6, cap each holding
   at **30% account**. If fewer leaders available,
   do not lever or redistribute above single-name cap.
2. `v14_invvol_55`: same gross 55% and top3/6, but
   distribute by inverse prior 60-day realized volatility;
   cap each at 30%. Does NOT rescale after clipping
   capped leaders; unfilled risk budget remains cash.
3. `v14_breadth`: same inverse-vol selection, but
   if **>=60% of fixed original instrument universe**
   passes positive-trend qualification, budget gross
   **65%**, otherwise gross **30%**. Benchmark gate
   must still pass. Never redefine breadth denominator
   using only winning or surviving symbols.
4. `v14_dual_horizon`: risk budget 55%, inverse-vol
   selection, require in addition **126 trading-day
   positive return** for each held name. Rank as above,
   discard ineligible names and leave unused budget cash.
5. `v14_strength`: inverse-vol weighting, gross
   **65%** if prior benchmark return63 divided by
   60-day annualised vol × sqrt(63/365 crypto, 63/252
   US stocks) is >=0.75, otherwise only **30%**.
   This is dimensionless trend strength measured only
   through previous FULL trading day.
6. `v14_core_satellite`: on risk-on regime, reserve
   **15% gross** for BTC/SPY benchmark core, and
   distribute **45% gross** inverse-vol across up to
   3/6 strongest OTHER eligible assets. Cap each name
   at 30%. In risk-off hold cash; not permanent
   benchmark buy and hold. If few satellites qualify,
   unused budget stays cash.

## Control / reusability

The prior 10 v12 strategies are retained in the code
unchanged, and dedicated synthetic data unit tests require
exact BUY/SELL ledger, daily marked equity and headline
metrics for ALL ten previous v12 policies. Also compare
with original v11 `risk_managed_gate` / v12
`gate_cap`, BTC/SPY buy-and-hold, equal-weights and
positive trend benchmark. Same 20k independent nominal
starting capital each cohort; 6bps buy/sell transaction
cost each SIDE plus severe 20bps each SIDE and optional
hypothetical nonhistorical 3% idle-cash yield scenario.

Capital budget is STRICT no-borrow accounting with
<=100% of portfolio gross mark and nonnegative cash.
30/55/65% are **target weights ONLY at monthly orders**
and can drift between monthly decisions — do not call
them hard realized all-hours caps. Compare average
invested and marked max, 1D-close MDD, CAGR, turnover,
annual subperiod, original passive opportunity cost
and severe fee stress.

## Evaluation populations

Crypto A: actual Binance SPOT BTC/ETH OHLC 2021-09-28
to 2026-09-28 exclusive (2020-04 data warmup).
Crypto B: actual Binance SPOT BTC/ETH/BNB/SOL/XRP
2022-06-01 to 2026-09-28 exclusive (520d warmup).
Stocks: HF original selected US 29 survivors,
SPY benchmark, 2021-09-28 to 2026-04-01 exclusive
(520d warmup), US RTH next available monthly OPEN.

All calendar periods and instruments have been inspected
repeatedly across v1–v13. They are **NOT untouched
holdouts/OOS**. Prevent a selected best performer from
being misrepresented as proven future alpha.
Stock universe has material survivorship, corporate
action and dividend problems. Real spot OHLC still
ignores variable transaction spreads, liquidity depth,
USDT counterparty risk, exchange downtime, tax and
portfolio level correlated market gaps. Futures
funding/liquidation and live order fills are NOT
covered by this long spot-holding simulation.
Daily-close MDD can materially understate intraday DD.

## Decision rule

**An increase in total returns does not equal strategy success
if MDD more than doubles or results concentrate in one year/
name.** Consider Calmar, annual breakdown, severe +14bps
extra EACH execution side, exposure and churn with
both controls and benchmark. Do not alter six frozen
rules on these seen samples. A genuinely new future-date
validation and paper execution are REQUIRED for a
deployable strategy. Preserve legacy Wyckoff B/E and
Supabase, Telegram and real Binance execution unchanged.
