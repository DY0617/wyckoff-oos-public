# Tactical V13 — FINAL portfolio drift risk, cash controls and passive reference study

Date: 2026-10-12.
GitHub Actions run **all four jobs SUCCESS** (9 dedicated causality/
cash/next-open/ledger unit tests, BTC/ETH actual spot, five-coin
actual spot, selected US equities):
https://github.com/DY0617/wyckoff-oos-public/actions/runs/38259186868

Original V13 rules **frozen before market results**:
[strategy/tactical_v13_frozen.md](tactical_v13_frozen.md).
Crypto subgroup evidence:
[strategy/tactical_v13_crypto_results.md](tactical_v13_crypto_results.md).

No changes to existing Wyckoff Track B/E, Binance live/order route,
Telegram, Supabase, GitHub production workflows or risk config.
Independent research code in
`research/tactical-v13-drift-risk` only.
No historical backtest alpha is guaranteed or independently validated.

## What was ACTUALLY changed

1. Keep original cash-funded, long-only monthly ranking, EMA200,
   prior 63-day momentum, 60-day volatility sizing and
   benchmark risk regime. Retain original `risk_managed_gate`
   and monthly `gate_cap` **EXACTLY** (same preexisting
   v12 trade ledger, equity return, fees, DD and number of orders).
2. Add `gate_cap_daily`: same monthly target portfolio as
   `gate_cap`, but after last FULLY CLOSED daily portfolio
   mark exceeds gross 50.2% or any asset 20.2%, sell at
   the **NEXT actual daily OPEN** toward 48% total
   and 19% per name. Never retroactively fill last CLOSE
   or use current intraday HIGH/LOW for pre-open decisions.
   The 0.2 percentage-point monitoring deadband was
   fixed *before results* when a synthetic unit test
   revealed fee-only microbreaches caused pointless
   next-day trades.
3. Include two standalone precommitted passive cash
   references: one-time 25% of initial cash buys BTC/SPY,
   and one-time 50% buys BTC/SPY; hold remaining cash.
   These are **NOT exact risk-matched benchmarks** as
   exposure drifts with markets; must not claim statistically
   significant outperformance against them.
4. True Binance SPOT 1-day OHLCV with strict date
   completeness and validation; US RTH 29-stock historical
   selected-survivor proxy source remains biased.
   Three independent 20,000-unit hypothetical cash
   accounts; fees +slippage 6bps/side nominal and
   20bps/side severe stress, 0% interest cash baseline.
   3% cash interest is only an optional hypothetical
   scenario, not verified historical market yields.
5. All stated MDDs use day CLOSE marks; intraday
   drawdown, forced-sale gaps, exchange outages and
   order book depth are NOT captured.

## All three market cohort outcomes

All returns TOTAL over each cohort's history, NOT
annualized: A crypto BTC/ETH 2021-09-28..2026-09-28,
B five crypto 2022-06-01..2026-09-28,
C stocks 2021-09-28..2026-04-01,
all exclusive end dates.

| Cohort | Policy | Cum % | CAGR % | Closing MDD % | Trades | Days >50% gross | Days any name >20% | 20bp per-side stress cum % |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| BTC/ETH spot | v11 regime gate | +58.95 | 9.71 | 17.44 | 56 | 62 | 539 | +57.32 |
| BTC/ETH spot | v12 monthly cap | +55.03 | 9.17 | 17.19 | 50 | 0 | 381 | +53.76 |
| BTC/ETH spot | **v13 daily cap** | **+50.98** | **8.59** | **16.78** | **103** | **0** | **60** | **+49.65** |
| BTC/ETH spot | passive 25% BTC | +25.09 | 4.58 | 26.68 | 1 | 0 | 1296 | +25.05 |
| BTC/ETH spot | passive 50% BTC | +50.18 | 8.47 | 47.19 | 1 | 1153 | 1826 | +50.11 |
| Five actual spots | v11 regime gate | +118.28 | 19.78 | 14.79 | 83 | 346 | 509 | +114.77 |
| Five actual spots | v12 monthly cap | +89.26 | 15.89 | 12.35 | 74 | 257 | 200 | +86.81 |
| Five actual spots | **v13 daily cap** | **+83.28** | **15.03** | **11.78** | **152** | **25** | **24** | **+80.75** |
| Five actual spots | passive 25% BTC | +41.39 | 8.34 | 30.01 | 1 | 279 | 1322 | +41.36 |
| Five actual spots | passive 50% BTC | +82.78 | 14.96 | 42.21 | 1 | 1071 | 1580 | +82.71 |
| US selected 29 stocks | v11 regime gate | +101.40 | 16.81 | 18.13 | 271 | 731 | 142 | +93.76 |
| US selected 29 stocks | v12 monthly cap | +65.06 | 11.76 | 12.19 | 269 | 499 | 0 | +60.77 |
| US selected 29 stocks | **v13 daily cap** | **+60.35** | **11.05** | **11.75** | **473** | **60** | **0** | **+55.96** |
| US selected 29 stocks | passive 25% SPY | +11.96 | 2.54 | 6.75 | 1 | 0 | 1131 | +11.92 |
| US selected 29 stocks | passive 50% SPY | +23.91 | 4.87 | 13.22 | 1 | 752 | 1131 | +23.84 |

## Exposure and execution accuracy

Under V13 daily cap,
- BTC/ETH: max closing gross exposure 41.34%,
  max name 21.58%, 48 drift SELL fills over 30
  unique daily signals, fees 91.74 USDT vs 87.63
  for monthly cap.
- Five spots: max closing gross exposure 51.68%,
  max name 21.04%, 71 drift SELL fills on 28
  signal days, fees 166.28 USDT vs monthly
  162.15 USDT.
- Selected US stocks: max closing gross exposure
  52.79%, max name 15.77%, 210 drift SELL fills
  on 35 signal days, fees 272.74 USD vs
  monthly 271.81 USD.

All THREE market outputs' JSON archives were downloaded
and RECHECKED directly using an independent Python
reconciliation: (i) account final equity is identical
to last daily marked curve; (ii) summing every
trade's fees equals aggregate reported paid fees;
(iii) minimum available cash >=0 (no debt);
(iv) maximal marked gross notional <=100% of
contemporaneous account equity, even with gaps;
(v) independently counted >50% daily close
breaches match reported diagnostics.
9 dedicated GitHub Actions unit tests also pass.

**Why 50% is NOT a strict instantaneous limit:**
At yesterday close the target may drift above
the monitoring threshold. Sale can only happen
at the next SESSION OPEN, which itself can gap,
and prices can move afterward. The five-asset
observed max close was still 51.68% and US
equity 52.79%; nobody should describe
this mode as guaranteeing all-times <=50%.

## Strategic decision: do NOT default to daily sells

Daily checks achieved a genuine drop in overcap-days,
but across all three retrospective cohorts
reduced returns by 4–6 percentage points and
increased trade counts about 2x vs monthly gate_cap
to reduce MDD only by ~0.4–0.6 percentage points.
Most return cost arose from smaller active capital
exposure; nominal commission differences
were relatively small (+$4.11/+4.13/+0.93)
despite more SELL events.

Predeclared cash-mix benchmarks generally had
much worse drawdown per growth than the tactical
monthly defenses, but the mixes' ex-post invested
fraction drifted and were NOT equal-risk tests.
DO NOT assert proved economic alpha.

Provisional research choices:
- Investor prioritizing absolute retrospective
  total return: old `risk_managed_gate`,
  with substantial 15–18% historical
  closing DD and many over-cap marks.
- Investor prioritizing a SIMPLE defensive
  tradeoff: old `gate_cap` monthly,
  relatively few trades; risk on five
  spots stock still occasionally exceeds targets.
- Need an OPERATIONAL breached-target limiter:
  V13 `gate_cap_daily` is a technically
  sound NEXT-OPEN reactive overlay,
  but NOT demonstrated better reward/risk.
  Treat as optional risk-rule implementation,
  not a production-selected universal alpha.

Most important limitations are unchanged:
repeated heavy exploration of the same 2021–2026
history creates data-snooping; historical crypto
data are spot and DO NOT model perpetual
futures funding / liquidation / mark prices;
US contemporary survivors bias stock results,
with corporate actions, dividends and exact
historical member universe unverified.
Fixed fills do not include 1m/tick execution
and orderbook/slippage stress. Year-specific
and unforeseen market crashes may reverse returns.
No independent future-time validation. NO
live deployment, no risk increases, no order bots.

Next scientifically valuable work (not claimed
completed by this report): true frozen
forward-date paper runs, accurate slippage
and actual available cash yield, predeclared
gross-risk passive benchmark with comparable
time-varying volatility and an unbiased
security universe; no more blindly optimizing
thresholds on already reused years.
