# Tactical v14 — actual SPOT crypto research results (pre-selected 6 arms)

2026-10-12 GitHub Actions run:
https://github.com/DY0617/wyckoff-oos-public/actions/runs/38262021571
All 11 unit tests PASS and both original real spot cohorts completed
SUCCESS. Frozen hypotheses before return analysis:
[strategy/tactical_v14_frozen.md](tactical_v14_frozen.md).

Strategy is a long-only **CASH-FUNDED** monthly *spot* portfolio,
not USDT-M futures. All decisions from previously fully closed
daily prices; orders at NEXT observed monthly open, risk-on gated
by prior BTC close > EMA200 and 63d momentum positive; no shorting,
borrowing or DCA. All figures retrospective, historically
over-researched assets/dates; **NOT unseen OOS**.

Initial simulated capital 20,000 USDT per independent cohort,
transaction fee/slippage 6bps each fill side nominal; adverse
fee stress 20bps/side. Max drawdown sampled on DAY CLOSE.

## BTC/ETH true Binance SPOT, Sep 2021–Sep 2026 exclusive

| Arm | Total return | CAGR | Day-close MDD | Calmar (CAGR/MDD) | Average risky exposure | 20bp/side stressed total |
|---|---:|---:|---:|---:|---:|---:|
| BTC buy/hold | +100.30% | 14.91% | 76.63% | 0.195 | 100% | +100.02% |
| Original v11 risk_managed_gate | +58.95% | 9.71% | 17.44% | **0.557** | 16.47% | +57.32% |
| V12 monthly gate_cap | +55.03% | 9.17% | 17.19% | 0.533 | 14.60% | +53.76% |
| v14 momentum 55% budget | +89.75% | 13.67% | 28.61% | 0.478 | 22.63% | +87.31% |
| v14 inverse vol 55% budget | +77.38% | 12.15% | 28.85% | 0.421 | 22.04% | +75.15% |
| v14 breadth .30/.65 budget | +86.09% | 13.23% | 30.83% | 0.429 | 23.65% | +83.63% |
| v14 dual 63d+126d | +69.31% | 11.11% | 21.41% | 0.519 | 19.08% | +67.47% |
| v14 benchmark strength .30/.65 | +59.94% | 9.85% | 26.85% | 0.367 | 21.65% | +57.97% |
| v14 BTC 15%+satellite 45% | +76.46% | 12.03% | 23.13% | 0.520 | 17.63% | +74.67% |

**No v14 crypto BTC/ETH entry improves original V11 risk efficiency.**
V14 adds exposure, causing a larger MDD. Even relatively modest
risk-on momentum allocation -9.50% in calendar 2022,
vs original gate -4.86%. It is possible to increase
headline return by exposing more capital; that is NOT alpha.

## BTC/ETH/BNB/SOL/XRP TRUE SPOT, Jun 2022–Sep 2026 exclusive

| Arm | Total return | CAGR | Day-close MDD | Calmar | Average risky exposure | 20bp/side stressed total |
|---|---:|---:|---:|---:|---:|---:|
| BTC buy/hold | +165.47% | 25.32% | 52.97% | 0.478 | 100% | +165.10% |
| Equal monthly five-asset | +273.64% | 35.62% | 61.74% | 0.577 | 99.67% | +268.90% |
| V11 original regime gate | +118.28% | 19.78% | **14.79%** | **1.338** | 23.66% | +114.77% |
| V12 monthly gate_cap | +89.26% | 15.89% | 12.35% | 1.286 | 20.17% | +86.81% |
| v14 momentum 55% | +104.62% | 18.00% | 16.78% | 1.072 | 24.11% | +101.32% |
| v14 inverse vol 55% | +90.15% | 16.02% | 14.68% | 1.091 | 23.88% | +87.13% |
| **v14 breadth .30/.65** | **+124.55%** | **20.56%** | 15.73% | 1.308 | 26.69% | +120.70% |
| v14 dual 63d+126d | +84.02% | 15.14% | 14.68% | 1.031 | 22.16% | +81.13% |
| v14 benchmark strength .30/.65 | +115.85% | 19.47% | 15.73% | 1.238 | 24.22% | +112.37% |
| v14 BTC 15%+satellite 45% | +88.15% | 15.73% | 18.52% | 0.849 | 25.25% | +85.25% |

The v14 65% breadth budget increased total cumulative return
by +6.27 percentage points vs original V11, but MDD rose
by 0.94 percentage points, **CALMAR worsened** from
1.338 to 1.308. Most original growth in both runs
occurred in 2023–2024 crypto bull regime. There is
insufficient independent evidence of robust prospective
enhancement. BTC and stock universes have different
sample lengths; cannot pool claimed CAGR.

## Research decision (pending US stock independent third cohort)

- Preserve original V11 `risk_managed_gate` as a more
  efficient crypto risk-control development benchmark.
- Preserve V14 breadth as **exploratory growth**
  alternative only; it has an ex-ante causal economic
  idea but does NOT clear a risk-adjusted superiority bar.
- Do not tune 0.30/0.65 budgets on the seen same
  dates. Dates from 2021–2026 were extensively
  mined in prior strategy work.
- Even future spot PnL can diverge because of
  slippage spikes, exchange access/queue, USDT
  counterparty risk, taxes, and cash/interest.
  Perpetual futures funding/liquidation and
  futures-specific cost are not simulated.

No live changes, real orders, Supabase, Telegram or
production Wyckoff pipeline deployment.
