# Tactical V14 — final 3-market decision: more risk does not automatically mean more alpha

**Date:** 2026-10-12. GitHub Actions run 38262021571 **ALL FOUR jobs SUCCESS**:
https://github.com/DY0617/wyckoff-oos-public/actions/runs/38262021571

Frozen architecture and hypotheses recorded BEFORE market results:
[strategy/tactical_v14_frozen.md](tactical_v14_frozen.md).
Detailed crypto data:
[strategy/tactical_v14_crypto_results.md](tactical_v14_crypto_results.md).

**Scope:** independently built CASH-FUNDED, long-only, monthly tactical
risk budgeting / momentum allocation. No live capital, production
Wyckoff B/E or Supabase/Telegram/Binance order integration modified.

Six new v14 hypotheses benchmarked with original V11/V12,
plus BTC/SPY passive cash-free index ownership and other control arms.
All 11 synthetic backward-compatibility, no-future-data, cash-risk
and funding checks passed; original V12 policies and account
ledgers reproduce exactly in the new V14 code on same market data.

## Historical simulated cohort outcomes

All returns are **cumulative**, not annualized; MDD sampled at
DAY CLOSE, not worst intraday; Calmar is annualized CAGR divided
by maximum DAILY-CLOSE DD (descriptive, not future alpha).
Each cohort starts at 20,000 USD/USDT, costs 6bp each
entry/exit side and full extra severe scenario 20bp each side.
Actual Binance SPOT 1-day prices used in crypto; US RTH
29-stock data still survivor selected.
Different date ranges: BTC/ETH Sep 2021–Sep 2026;
five crypto Jun 2022–Sep 2026;
US 29 selected stocks Sep 2021–Mar 2026.

| Cohort | Arm | Total % | CAGR % | MDD % | Calmar | Mean risky capital % | Severe 20bp/side % |
|---|---|---:|---:|---:|---:|---:|---:|
| BTC/ETH SPOT | Original v11 regime gate | +58.95 | 9.71 | 17.44 | **0.557** | 16.47 | +57.32 |
| BTC/ETH SPOT | v14 momentum 55 | +89.75 | 13.67 | 28.61 | 0.478 | 22.63 | +87.31 |
| BTC/ETH SPOT | v14 inverse-vol 55 | +77.38 | 12.15 | 28.85 | 0.421 | 22.04 | +75.15 |
| BTC/ETH SPOT | v14 breadth 30/65 | +86.09 | 13.23 | 30.83 | 0.429 | 23.65 | +83.63 |
| BTC/ETH SPOT | v14 dual 63+126d | +69.31 | 11.11 | 21.41 | 0.519 | 19.08 | +67.47 |
| BTC/ETH SPOT | v14 benchmark-strength budget | +59.94 | 9.85 | 26.85 | 0.367 | 21.65 | +57.97 |
| BTC/ETH SPOT | v14 15% core +45% satellite | +76.46 | 12.03 | 23.13 | 0.520 | 17.63 | +74.67 |
| Five SPOT crypto | Original v11 regime gate | +118.28 | 19.78 | 14.79 | **1.338** | 23.66 | +114.77 |
| Five SPOT crypto | V12 monthly 50% cap | +89.26 | 15.89 | 12.35 | 1.286 | 20.17 | +86.81 |
| Five SPOT crypto | v14 momentum 55 | +104.62 | 18.00 | 16.78 | 1.072 | 24.11 | +101.32 |
| Five SPOT crypto | v14 inverse-vol 55 | +90.15 | 16.02 | 14.68 | 1.091 | 23.88 | +87.13 |
| Five SPOT crypto | **v14 breadth 30/65** | **+124.55** | **20.56** | **15.73** | 1.308 | 26.69 | +120.70 |
| Five SPOT crypto | v14 dual 63+126d | +84.02 | 15.14 | 14.68 | 1.031 | 22.16 | +81.13 |
| Five SPOT crypto | v14 benchmark-strength budget | +115.85 | 19.47 | 15.73 | 1.238 | 24.22 | +112.37 |
| Five SPOT crypto | v14 15% core+45% satellite | +88.15 | 15.73 | 18.52 | 0.849 | 25.25 | +85.25 |
| US selected 29 stocks | SPY passive | +47.80 | 9.06 | 25.37 | 0.357 | 100 | +47.59 |
| US selected 29 stocks | Original v11 regime gate | +101.40 | 16.81 | 18.13 | 0.927 | 46.82 | +93.76 |
| US selected 29 stocks | Original absolute_trend | +104.91 | 17.26 | 12.63 | **1.366** | 54.81 | +101.62 |
| US selected 29 stocks | V12 monthly 50% cap | +65.06 | 11.76 | 12.19 | 0.965 | 32.75 | +60.77 |
| US selected 29 stocks | v14 momentum 55 | +83.10 | 14.36 | 14.26 | 1.008 | 36.08 | +78.41 |
| US selected 29 stocks | v14 inverse-vol 55 | +70.72 | 12.60 | 12.92 | 0.975 | 35.93 | +65.81 |
| US selected 29 stocks | **v14 breadth 30/65** | **+77.47** | **13.58** | **12.31** | **1.103** | 35.18 | +72.10 |
| US selected 29 stocks | v14 dual 63+126d | +71.94 | 12.78 | 13.74 | 0.930 | 35.90 | +66.97 |
| US selected 29 stocks | v14 benchmark-strength budget | +61.74 | 11.26 | 14.29 | 0.788 | 32.59 | +57.19 |
| US selected 29 stocks | v14 15% core+45% satellite | +61.41 | 11.21 | 12.72 | 0.881 | 38.97 | +57.19 |

All 12 modes in all three jobs are preserved in GitHub
Actions JSON artifacts, including full per-trade BUY/SELL ledger,
daily marked equity and year attribution; the table
selects informative controls and all NEW arm variants.

## Reconciled from archived original JSON artifacts

GitHub Actions artifacts:
`tactical-v14-btc-eth` #11752542612,
`tactical-v14-five-crypto` #11752737484,
`tactical-v14-stocks` #11753496499.

Downloaded each archive and INDEPENDENTLY checked
ALL 36 arm×cohort evaluations:
- last day portfolio equity equals reported `final_equity`,
- sum of ledger fees equals reported `paid_fees`,
- minimum marked available CASH >=0 within tolerance,
- every day gross risky marked exposure <=100% equity,
- reported execution count equals raw ledger entries.

All checks PASS. This is **internal accounting fidelity**,
not a verification that selected historical prices represent
tradable bid/ask or that the strategy generates real alpha.

## What can and cannot be concluded

1. Five-spot v14 `breadth`: +124.55% vs old
   +118.28%, i.e. **6.27 percentage points extra total**
   over ~4.3 years. MDD +15.73% vs +14.79%.
   CALMAR **1.308 below original 1.338**.
   Slight growth improvement, not a
   risk-adjusted breakthrough.
2. BTC/ETH v14 breadth +86.09% is much more profitable
   than old +58.95% BUT max closing MDD increases
   from 17.44% to **30.83%**; CALMAR falls
   from 0.557 to 0.429. This violates a goal
   of reliably smoother upward account value.
3. US selected basket v14 breadth +77.47% at 12.31%
   MDD versus V12 cap +65.06% at 12.19% MDD,
   a promising **within this BIASED sample**
   tradeoff. However the already-predetermined
   absolute_trend control had +104.91% at 12.63%
   MDD and CALMAR 1.366; the new model is not
   overall best among controls.
4. The simple extra confirmation `v14_dual_horizon`
   did not improve risk-adjusted return; monthly
   faster or stricter screening can remove winners.
   Likewise inverse-vol, momentum, strength
   and benchmark core-satellite have uneven results.
5. Five-crypto breadth cumulative return +124.55%
   is mostly linked to stronger crypto periods:
   2023 +20.94%, 2024 +57.04%, 2025 +10.24%,
   2026 partial +7.25%. These are distinct annual
   portfolio results, not a future probability.

### Illustrative month-block fragility diagnostic

Using the saved month-end log equity returns,
compare V14 breadth and ORIGINAL regime gate
by pairing their MONTHLY log returns and resampling
contiguous circular six-month blocks 10,000 times
with deterministic seed 20261012:
- Five-crypto 52 months, actual relative total
  log-return +0.0283; 2.5–97.5% resampled
  pseudointerval **-0.0751 to +0.1526**.
- BTC/ETH 61 months, actual relative total
  log-return +0.1576; pseudointerval
  **-0.1463 to +0.4578**.

**Both include ZERO**. This is not a formal,
independent 95% confidence interval or valid
post-multiple-testing hypothesis test: data have
already been overmined; block length and
sample nonstationarity matter; portfolio
compounding is altered by resampling.
It is presented only as an instability check.

## Research verdict

**DO NOT promote v14 into actual trading.**
It does not robustly outperform V11/V12 on
risk-adjusted criteria across all market cohorts.
Keep V14 breadth as an unconfirmed *separate*
growth-tilt research idea, preserve original
cash/risk-managed V11 as crypto defensive
historical benchmark, and V11 absolute-trend
as a stock reference ONLY until survivorship
and total-return data are corrected.

No retrospective 0.30/0.65 budget retuning on
the same series; repeating 14 generations
and choosing a winner would amplify false
discovery and adverse performance risk.

For a genuinely improved live candidate:
(1) Add independent sources of expected return
    and diversification: independently verified
    real Treasury/bond and gold total-return
    histories, cash yields including realistic
    funding/exchange and KRW currency costs,
    rather than only scaling BTC/ETH risk.
(2) Build a survivorship-free US equity
    total-return universe incl delisted names;
    US 29 contemporary survivors are not
    reliable production backtests.
(3) Freeze a strategy and validate on
    **future unseen dates** with recorded
    paper orders, bid/ask, spreads, slippage,
    fees, cash settlement and 1-minute
    intra-day drawdown before real capital.

No live integrations, Supabase changes, order
size increases, Wyckoff B/E or Telegram updates.
