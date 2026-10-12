# Tactical v13 — true SPOT next-session portfolio cap study (crypto)

Date 2026-10-12. GitHub Actions run 38259186868:
https://github.com/DY0617/wyckoff-oos-public/actions/runs/38259186868

Research ONLY; no live orders. Nine causal/ledger/execution unit tests
PASS, and both crypto jobs PASS. All previous V12 arms examined in
unit fixture preserved exact original V12 trade ledger/accounting.
In real exchange SPOT data, V13 engine replays prior frozen
`risk_managed_gate` and `gate_cap` with EXACT V12 performance,
trades, drawdown, cost and capital exposure; no silent comparison
engine changes. Downloaded both completed Actions JSON artifacts
and verified individually that daily last marked equity matches
reported account, all cash balances nonnegative, all ledger fee
sums match and marked exposure <=100% portfolio equity.

Frozen experimental manifest:
[strategy/tactical_v13_frozen.md](tactical_v13_frozen.md).
Uses actual historical Binance SPOT 1D OHLCV with strict missing-month/
duplicate checks; NOT USDT-M futures, with NO margin, funding, forced
liquidation or short sales. 20,000 USDT initial account per cohort,
6bp nominal each trading side, 20bp severe cost stress.
Cash earns zero in baseline, simulated 3% interest only in
an explicitly hypothetical optional scenario.
All MDDs measured at DAILY CLOSE, not intraday.

### BTC/ETH spot, 2021-09-28..2026-09-28 exclusive

| Mode | Cumulative simulated return | CAGR | Daily-close MDD | BUY/SELL transactions | Days total >50% | Days any name >20% | Max asset weight |
|---|---:|---:|---:|---:|---:|---:|---:|
| V11 original monthly regime risk | +58.95% | 9.71% | 17.44% | 56 | 62 | 539 | 35.04% |
| V12 monthly gate_cap | +55.03% | 9.17% | 17.19% | 50 | 0 | 381 | 26.02% |
| **V13 gate_cap_daily** | **+50.98%** | **8.59%** | **16.78%** | **103** | **0** | **60** | **21.58%** |
| Fixed 25% BTC + 75% cash (buy then hold) | +25.09% | 4.58% | 26.68% | 1 | 0 | 1296 | 49.65% |
| Fixed 50% BTC + 50% cash (buy then hold) | +50.18% | 8.47% | 47.19% | 1 | 1153 | 1826 | 74.74% |

V13 reacted to 30 unique daily close breach events,
executing 48 separate next-open cap-reducing sales.
Daily single-name weight >20% fell from 381 to 60
closing days, but return fell 4.05 percentage points vs
V12 gate_cap and MDD improved only 0.41 points.
The number of executions more than doubled.

### Five-crypto spot, 2022-06-01..2026-09-28 exclusive

| Mode | Cumulative simulated return | CAGR | Daily-close MDD | BUY/SELL transactions | Days total >50% | Days any name >20% | Max gross exposure |
|---|---:|---:|---:|---:|---:|---:|---:|
| V11 original monthly regime risk | +118.28% | 19.78% | 14.79% | 83 | 346 | 509 | 78.45% |
| V12 monthly gate_cap | +89.26% | 15.89% | 12.35% | 74 | 257 | 200 | 57.37% |
| **V13 gate_cap_daily** | **+83.28%** | **15.03%** | **11.78%** | **152** | **25** | **24** | **51.68%** |
| Fixed 25% BTC + 75% cash | +41.39% | 8.34% | 30.01% | 1 | 279 | 1322 | 56.65% |
| Fixed 50% BTC + 50% cash | +82.78% | 14.96% | 42.21% | 1 | 1071 | 1580 | 79.68% |

In the five-crypto study, V13 daily cap produced
71 next-session cap sells on 28 unique signal days.
Relative to v12 monthly cap, return fell 5.98 points
and closing-mark MDD improved 0.57 points.
Both risk overrun counts dropped dramatically.
High costs still left a positive +80.75%
cumulative total for V13 five-spot, but this
does not establish an expected return.

**No always-50% cap guarantee.** Overnight gaps and same-day
drifts can breach the target even with next-opening
reactive risk sales: five-spot daily-close maximum
observed gross exposure was 51.68% despite
continuous monitoring. For a strict cap guarantee,
contingent execution and much finer observation,
with nonfill and liquidity stress, would be required.

### What this actually tells us

1. The daily overlay genuinely **improves execution discipline**:
   fewer over-cap daily marks using only prior-bar prices.
2. It did **not** deliver a decisive profitability breakthrough;
   it traded about twice as much to improve max closing
   drawdown by less than 0.6 percentage points relative to
   monthly cap in BOTH crypto cohorts.
3. Passive 25% or 50% benchmark ownership is a useful
   opportunity-cost comparator, NOT a perfect
   volatility-matched passive test. Its invested weight
   drifts substantially without rebalancing. Do not claim
   superior future alpha merely because tactical risks
   outperformed these particular static cash slices.
4. V11 original monthly gate retains a materially larger
   historical return at greater risk/exposure. These
   are inherently different objectives; no universal
   winner is implied by MDD and total alone.
5. The prior 2021–2026 price window and assets have been
   repeatedly explored in v1–v12. There is no genuine
   untouched calendar OOS here. Actual exchange spreads,
   slippage at large gaps, taxes, USDT counterparty risk,
   downtime, orderbook depth and cash yield may change
   results materially.
6. The 0.2 %-point trigger tolerance was added after
   **synthetic unit tests caught fee-rounding microbreach**
   and before any V13 market return inspection. This is a
   software-consistency fix rather than threshold tuning.

Research-only decision for the crypto legs: keep V13 as an
OPTIONAL next-session risk-control overlay; DO NOT REPLACE
original V11/V12 automatically. Need fresh forward paper
period, uncertainty bounds and order fill realism.

No Binance order pipeline, Supabase, Telegram, Wyckoff
Track B/E or production code has changed.
