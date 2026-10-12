# Tactical v12 — true spot market data + top-down risk defense

Frozen **before running V12 returns**, 2026-10-12.
Original independently developed portfolio research. No trading
orders, Supabase, Telegram or production workflows affected.

## Purpose

v11 monthly absolute-trend and risk-managed benchmark gating yielded
promising HISTORICAL price-based returns. But v11 simulated cash-funded
spot ownership using **BINANCE USDT-M FUTURES PRICE** data. V12
first corrects that data mismatch and locks all v11 parameters
unchanged. Then tests 3 new RISK architecture alternatives whose
purpose is loss prevention, not historical return maximisation.
Do not choose V12 arm after results and call it a true OOS test.

## Data correction / strict data quality

Binance official monthly **SPOT 1-day** raw public archives:
`https://data.binance.vision/data/spot/monthly/klines/<symbol>/1d/...`
for BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT. Separate cohorts:
- BTC/ETH Sep 28 2021–Sep 28 2026 exclusive, 520 days warmup.
- 5 assets Jun 01 2022–Sep 28 2026 exclusive, 520 days warmup.
- US selected stocks RTH Sep 28 2021–Apr 01 2026 exclusive,
  same original HF data adapter, exploratory only.

Hourly futures OHLCV, historical funding, futures liquidation,
futures margin or shorting are NOT used in V12 cash-funded spot
backtest. All SPOT days must form a strict, unique 86,400,000ms
UTC calendar sequence, month ZIP required, OHLC consistency
checked, bad/missing dates cause FULL study failure, not silent
zero fills. Date conversion accepts millisecond or microsecond
timestamps. Daily EMA/return indicators computed solely from
past daily closing price series, signals at preceding day and
orders at the next observed daily OPEN.

Unlike true held-out data, **all dates and symbols had already been
examined before in v1-v11**. V12 is a data-quality/architecture
stress test, NOT independent OOS alpha discovery.

## Locked portfolio variants

**The original seven v11 modes remain bitwise equivalent on the
same input candles with zero cash interest**:
benchmark_hold, equal_hold, equal_monthly, absolute_trend,
momentum_top, risk_managed and risk_managed_gate. A direct parity
assertion checks all seven in every dataset.

Three new deliberately simple independent DEFENSIVE alternatives,
each sharing ALL original v11 day-close indicators, cash-funded
rebalancer, fee model and capped positions:

8. `gate_weekly`: identical v11 `risk_managed_gate` target
   weights and absolute trend/best top-3 (crypto) or top-6 stock
   strength rules, but **first observed session of each ISO
   calendar WEEK** instead of monthly. This reduces delay to
   risk-off but may increase turnover, whipsaw and tax.
9. `gate_cap`: same original monthly BTC/SPY gate, vol target
   and ranked leaders. Reduce EACH asset's weight to max **20%**
   and reduce entire gross weight pro-rata to **50%** at
   every monthly rebalance. No risk boost in calm markets.
   Enables lower risk at the cost of lower long-term growth.
10. `gate_crashguard`: same original monthly gate, plus an
    additional rule using benchmark's **previous 30 completed
    daily closes**: if last completed daily CLOSE is **15% or
    more below the max completed 30-day close**, target
    ALL positions to zero cash at next monthly rebalance.
    This is additional historical drawdown condition and
    cannot eliminate a crash between monthly decisions.
    An anti-whipsaw or daily stop is NOT implied.

All four risk/gate types long-only, no margin, no options,
no external capital contributions, no DCA, no leverage.
The initial capital is 20,000 units in each separately
simulated cohort. Total gross exposure <=100% account equity;
cash may never be negative; orders executed using next open
after previous completed daily indicators.

## Costs, cash yield, audit checks

- Nominal buy/sell cost **6bps each side**; severe 20bps
  each side, no retrofitted per-asset discount.
- CASH yield scenario **0%** (base) and 3% APY on
  daily uninvested cash ONLY. **3% is purely illustrative**,
  NOT a verified historically achievable deposit/broker
  yield. Compound between observed trading dates.
- Compare total return, annualised CAGR, daily-close MDD,
  cash exposure, turnover/fees, worst day, annual returns,
  passive BTC/SPY, equal buy-and-hold.
- Every original seven v11 modes must match v11 returns,
  MDD, fees, execution count exactly when run with same
  corrected input dataset. If not, study MUST fail.
- Unit test no future data, cash constraint, weekly
  real trade timing, gap-free spot days, duplicate/bad
  OHLC rejection, interest only on idle cash.
- Require that a clearly weak or expensive variant be
  rejected. Risk-protection is not automatically alpha:
  if it is simply ~90% cash, explicitly compare a
  similarly cash-heavy passive index position.

## Critical limitations

Spot price data is actually SPOT but does not include
actual order-book queues, transaction impact, asset
delisting/migration risks or tax. USD/USDT stablecoin
depeg, deposit/redemption, and jurisdiction differences
are excluded. Monthly and weekly strategies still face
full overnight and intramonth losses. Cash rate is
illustrative only. No futures mechanics are represented.
US stock universe survives into recent dates; original
HF prices are NOT a verified split/dividend-adjusted
total-return or survivorship-free research universe.
Repeated historical test selection means all positive
results are retrospective, not expected returns.

**Deployment criterion remains unmet without completely
unseen forward data and implementation-level spot
order/fill/slippage/liquidity validation.**
