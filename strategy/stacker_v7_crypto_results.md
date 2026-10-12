# Stacker v7 — crypto instrument-holdout research results

Executed in GitHub Actions run #38225282544 (2026-10-12):
https://github.com/DY0617/wyckoff-oos-public/actions/runs/38225282544
Unchanged pre-result assumptions:
[strategy/stacker_v7_regime_holdout_frozen.md](stacker_v7_regime_holdout_frozen.md)

**This is our independent, hypothetical strategy, not AGOS's private Stacker.**
Binance 1H OHLC futures, gross planned stop risk <=0.75% equity/cycle
including stressed estimated fees, 70% notional cap/cycle, at most
2 concurrent cycles. Initial cash 20,000 USD/USDT; 6bps each
fill/side incl simulated slippage, 10bps stress each fill/side;
funding proxy from monthly funding archives. Max drawdown uses
1H-close marked equity and omits within-hour extremes.

## Development comparator: BTCUSDT + ETHUSDT 2021-09-28..2026-09-28 exclusive

| Predeclared policy | Closed cycles | Net return | PF | MTM MDD | +4bp/side stress |
|---|---:|---:|---:|---:|---:|
| control | 207 | +0.67% | 1.026 | 4.35% | -0.85% |
| asset_vol_skip | 175 | +3.32% | 1.155 | 3.46% | +1.93% |
| benchmark_vol_skip | 182 | +3.88% | 1.181 | 3.20% | +2.47% |
| either_vol_skip | 175 | +3.32% | 1.155 | 3.46% | +1.93% |
| bb_rejection | 49 | +2.12% | 1.520 | 1.83% | +1.78% |
| asset_vol_rejection | 38 | +1.33% | 1.398 | 1.87% | +1.05% |
| shock_skip | 172 | +3.44% | 1.181 | 5.21% | +2.22% |
| graded_size | 207 | +1.53% | 1.069 | 3.68% | +0.17% |

## Fresh symbol holdout: BNBUSDT + SOLUSDT + XRPUSDT, 2022-06-01..2026-09-28

BTCUSDT is benchmark ONLY and is not traded in this account.
These symbols had never been backtested directly in our original
BTC/ETH Stacker series. However this is NOT held-out future time.

| Predeclared policy | Closed cycles | Net return | PF | MTM MDD | +4bp/side stress |
|---|---:|---:|---:|---:|---:|
| control | 224 | -2.66% | 0.910 | 9.80% | -3.88% |
| asset_vol_skip | 188 | -5.46% | 0.805 | 11.89% | -6.56% |
| benchmark_vol_skip | 191 | -2.02% | 0.923 | 9.22% | -3.13% |
| either_vol_skip | 177 | -4.50% | 0.826 | 10.92% | -5.53% |
| bb_rejection | 63 | -3.88% | 0.605 | 5.91% | -4.22% |
| asset_vol_rejection | 54 | -4.46% | 0.507 | 5.99% | -4.75% |
| shock_skip | 189 | **+2.34%** | **1.106** | **5.31%** | **+1.32%** |
| graded_size | 224 | -4.57% | 0.826 | 10.47% | -5.62% |

## Interpretation / no-cherry-picking discipline

- `bb_rejection` showed unusually high PF on BTC/ETH but
  failed on heldout new symbols, confirming sample-transfer risk.
- `benchmark_vol_skip` also failed to generalise to BNB/SOL/XRP.
- **Only `shock_skip` was profitable on both historical sets and
  held its sign under additional +4bps EACH SIDE fee stress.**
- `shock_skip` is a simple PREDECLARED market microstructure
  hypothesis: skip next-open fade entries after a *completed 4H
  signal candle* whose high-low spread exceeds 2.25 times its
  ATR14. This reduces adverse shock exposure; do NOT change
  2.25 after inspecting these results and call it holdout.
- New-asset annual gross-net USD PnL by entry year for shock_skip:
  2022 +1,015.68 (partial); 2023 -169.78; 2024 -331.77;
  2025 -38.87; 2026 -7.55 (partial).
  Of three fresh instruments, BNB about -8.61, SOL +330.75,
  XRP +145.58. These are not consistently positive years.
- Known BTC/ETH shock_skip annual USD PnL:
  2021 +182.84 partial, 2022 +213.52, 2023 -373.69,
  2024 -82.76, 2025 +916.57, 2026 -168.20 partial.
- A MONTH-BLOCK resampling diagnostic (3,000 draws with
  replacement, one-month PnL blocks, seed 42) on the new-asset
  shock_skip produced a 2.5%–97.5% *resampled total-profit*
  range around -1,768 to +2,777 USDT. This is **not a formal
  frequentist confidence interval**, months aren't independent,
  compounding and simultaneous exposure are only approximated.
  The wide range containing 0 is further evidence of fragility.
- Returns are only +2.34% over over four years on alt holdout and
  +3.44% over five years on known crypto. Compared to passive
  market exposures these are economically small and not
  evidence of a production-ready or stable compounder.

## Decision

**Research candidate ONLY: shock_skip, no live orders.**
Others do not robustly transfer to unseen instruments. More
untouched instruments / *future* validation, verified futures
execution costs and funding, intrabar risk and margin/liquidation,
risk-equivalent passive benchmarks and longer disjoint periods
are required before confidence.

The selected US stock cohort runs separately; do not infer
its results from crypto evidence.

All code and evidence are on a segregated research branch; original
Track B/E, Supabase, Telegram and exchange/auto-order setups are untouched.
