# Stacker v5 BTC/ETH independent retest study — frozen historic results

Research-only result from GitHub Actions run 38222776851 at 2026-10-12.
Corresponding branch: `research/stacker-v5-independent-retest`,
commit 9e5a6cefc1d052b30d5617dc801d6a3396bfcbfb.

**This is NOT an implementation or validation of AGOS proprietary algorithms.**
These are separate frozen research rules devised from public mean-reversion ideas.

Universe: BTCUSDT / ETHUSDT Binance USDT-M historical 1H, evaluation
2021-09-28 to 2026-09-28 exclusive, starting 20,000 USDT, parent bounded
cycle 0.75% planned risk, child fresh risk 0.375% (inclusive of 10bps
fee stress), max 2 simultaneous cycles, 6bps estimated trading cost per
side and approximate historical funding. Hourly close marked-equity DD.

| Mode | Parent cycles | Independent child trades | Net return | PF | 1H-close MTM DD | 10bp/side stress return | Child PnL | Child PF |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| control | 207 | 0 | +0.672% | 1.026 | 4.350% | -0.849% | n/a | n/a |
| retest (1H close bounce/reclaim) | 207 | 24 | -1.880% | 0.940 | 7.248% | -3.809% | -501 USDT | 0.550 |
| retest_htf (+ completed 4H EMA slope) | 207 | 13 | +0.242% | 1.008 | 5.422% | -1.575% | -81 USDT | 0.856 |
| retest_htf_barrier (+ confirmed swing resistance clearance) | 207 | 2 | -0.016% | 0.999 | 4.768% | -1.593% | -137 USDT | 0.000 |

Notes:
- The parent strategy *exits its entire position at EMA TP*. The
  child is a NEW independently sized trade, with fresh stop from the
  last six COMPLETED 1H bars and a target 2R from actual entry.
  No legacy stop lowering, no uncontrolled averaging.
- The child signal must follow an original EMA TP close and test its
  frozen TP +/- original ATR, then close directionally back above
  EMA20 (below SHORT), enter next 1H open only. Previous-4H filter
  and resistance barrier were also compared without post-hoc tuning.
- More selective rules reduce the number of losing trades but do
  not create robust positive child expectancy. No arm survives the
  +4bps/side transaction-cost stress.
- Crypto child sample sizes 24/13/2 are too small to claim general
  performance; risk of multiple-testing/selection is substantial.
- Research conclusion: DO NOT ACTIVATE IN LIVE PORTFOLIO.
- LIMITATIONS: only BTC & ETH; hourly close MTM, not tick-level DD;
  imperfect trading/funding and exact liquidation modelling;
  all years already seen during v1-v4 development, NOT independent OOS.
