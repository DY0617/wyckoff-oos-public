# AGOS-inspired Bounded Stacker v1 — completed research review

Recorded 2026-10-12. Source: GitHub Actions run #38214821516.
https://github.com/DY0617/wyckoff-oos-public/actions/runs/38214821516

**Important:** This is NOT the performance of AGOS's undisclosed implementation.
It is our original band-breakout / capped DCA prototype inspired by the
limited public explanation. Parameters were locked prior to the run.

Starting cash: $20,000; total max two concurrent cycles, 0.75% maximum
planned risk per cycle, max 70% cash notional per cycle; 6bps
commission/slippage per side; funded crypto with historical Binance rates
and 1H close proxy. Mark-to-market DD uses end-of-hour open positions.

## BTC/ETH Binance futures, 2021-09-28 to 2026-09-28 exclusive

| Variant | Trades | Win rate | Return | Hourly-close MTM MDD | PF |
|---|---:|---:|---:|---:|---:|
| Equal-risk single | 1,014 | 83.43% | -34.75% | 35.39% | 0.647 |
| Bounded Stacker | 1,122 | 89.93% | -26.69% | 27.03% | 0.639 |
| Bounded Stacker + daily EMA200 gate | 508 | 91.34% | -9.54% | 11.20% | 0.707 |

In the gated version, average winner +$9.93, average loser -$148.05:
required break-even win ratio approximately 93.72%. Observed 91.34%.
All years except partial 2021 negative in this version.

## US stocks & ETFs RTH, 2021-09-28 to 2026-04-01 exclusive

| Variant | Trades | Win rate | Return | Hourly-close MTM MDD | PF |
|---|---:|---:|---:|---:|---:|
| Equal-risk single | 456 | 83.77% | +1.18% | 4.60% | 1.032 |
| Bounded Stacker | 527 | 92.22% | -0.84% | 3.54% | 0.967 |
| Bounded Stacker + daily EMA200 gate | 366 | 93.44% | +0.35% | 3.52% | 1.021 |

Stock gated yearly realised cycle PnL in USD: 2021 -188, 2022 -125,
2023 -122, 2024 +108, 2025 +470, 2026 partial -73. The small
positive return for stocks is far below the amount of validation and
execution uncertainty; it is not strong evidence of an investable edge.

## Decision

**REJECT as production trading strategy.** Keep the branch and artifacts
as research evidence. Do NOT merge the execution code into existing
Wyckoff Track B, CAT, Supabase or Telegram live paths; do NOT connect
exchange credentials; do NOT raise leverage or remove stops to artificially
increase win ratio.

Potential future research must begin with a predeclared DIFFERENT market
hypothesis and unseen datasets (e.g., whether fixed-risk countertrend
entries have predictive post-shock reversal information compared to the
passive benchmark), not tune these thresholds to fit the known period.

Caveats: 1H-close MTM understates intrabar floating DD; simulated OHLC
paths adverse-first but do not model order book; cash stock data with
simple corporate-action heuristic is not an executable stock-futures
performance record; survivorship bias affects the equity universe;
funding uses hourly-close approximations rather than exact mark;
no liquidation / dynamic exchange margin / exchange outage / taxes.
