# Tactical Allocation v11 — verified BTC/ETH and five-asset crypto results

2026-10-12 GitHub Actions run:
https://github.com/DY0617/wyckoff-oos-public/actions/runs/38253573891

**Independent portfolio-allocation research, NOT AGOS proprietary,
NOT a live Binance futures performance estimate.**
Both crypto research jobs and 11 cash/causality invariants passed.
Frozen prior-to-results details:
[strategy/tactical_allocation_v11_frozen.md](tactical_allocation_v11_frozen.md).

The prices are **BINANCE USDT-M futures OHLC**, evaluated as a
*cash-funded SPOT-LIKE long-only price model*. No futures funding,
margin, liquidation, futures leverage or actual spot-market
bid/ask mechanics. Do NOT deploy through a perpetual-futures
order endpoint using these returns. Real tradable spot data,
funding and contract accounting are required before application.

Monthly schedule uses strictly prior COMPLETED daily
market indicators and enters at the *next monthly trading-day
OPEN*. Full gross notional must be paid for, including fees,
with no negative cash (11 dedicated unit tests PASS).
Initial equity each separate cohort is 20,000 USDT.
Fees and slippage nominal 6bps SIDE, stressed at 10bps and
20bps EACH SIDE. No shorts and no DCA.
CAGR and max drawdown derive from daily-close marked account
equity including current cash and held inventory value.

## A — BTCUSDT and ETHUSDT, 2021-09-28..2026-09-28 exclusive

| Frozen mode | 5y cumulative | CAGR | daily-close max DD | Mean invested exposure | Severe 20bps-side return |
|---|---:|---:|---:|---:|---:|
| BTC buy/hold | +100.32% | 14.91% | 76.67% | 100% | +100.05% |
| BTC/ETH equal buy/hold | +46.13% | 7.88% | 76.84% | 100% | +46.00% |
| equal-weight monthly | +48.29% | 8.20% | 76.23% | 100% | +47.59% |
| absolute trend, cash slots | +147.50% | 19.87% | 46.98% | 44.10% | +141.61% |
| positive-trend top rank | +95.02% | 14.29% | 33.84% | 29.74% | +92.09% |
| inverse-vol risk budget | +53.31% | 8.92% | 17.46% | 17.80% | +51.74% |
| **inverse-vol risk + BTC regime gate** | **+58.66%** | **9.67%** | **17.46%** | **16.43%** | **+57.03%** |

Risk-gated annual sample return by evaluation year:
2021 partial +5.08%, 2022 -4.86%, 2023 +14.94%,
2024 +27.89%, 2025 +4.06%, 2026 partial +3.75%.

The best total return is NOT necessarily the preferred option:
absolute_trend still suffered a severe 46.98% drawdown.
The regime-gated risk-managed arm averaged just 16.43%
invested exposure. Its lower DD is partly due to being mostly
IN CASH, which has material upside opportunity cost.

## B — five futures-price underlying proxies BTC, ETH, BNB, SOL,
XRP, 2022-06-01..2026-09-28 exclusive

| Frozen mode | 4.3y cumulative | CAGR | daily-close max DD | Mean invested exposure | Severe 20bps-side return |
|---|---:|---:|---:|---:|---:|
| BTC buy/hold | +165.37% | 25.31% | 52.98% | 100% | +165.00% |
| five equal buy/hold | +154.49% | 24.10% | 62.40% | 100% | +154.12% |
| five equal monthly | +273.19% | 35.59% | 61.75% | 99.7% | +268.98% |
| absolute trend/cash | +146.36% | 23.17% | 20.70% | 38.8% | +141.75% |
| momentum top-3 | +200.12% | 28.93% | 30.15% | 51.5% | +190.68% |
| risk-managed | +109.19% | 18.60% | 18.43% | 28.6% | +105.39% |
| **risk-managed + BTC market gate** | **+118.21%** | **19.77%** | **14.78%** | **23.63%** | **+114.65%** |

Market-gated annual evaluation returns:
2022 partial 0.0%, 2023 +21.3%, 2024 +55.8%,
2025 +7.4%, 2026 partial +7.5%.
No cash interest credited. Monthly worst return for this arm
was approximately -9.82% during February 2025. It is NOT
a loss-free or continuously upward monthly equity strategy.
The large +55.8% calendar 2024 does contribute substantially
to overall returns. All data periods were previously exposed
by earlier trading strategy research, i.e. NOT independent
forward OOS.

### Independent ledger and risk accounting check

Downloaded original completed run's full JSON artifact
`tactical-allocation-v11-five-crypto` (#11749188049) and
independently checked ALL seven policy ledgers/daily curves:
- last equity mathematically equals 20,000*(1+reported return)
- minimum cash across daily curves >= -1e-5 (round-off only)
- max invested exposure <=100% of contemporaneous equity
- modes printed exactly the same outcomes as archived report.

For gate: starting 20,000 grew to 43,642.39 simulated
USDT price-value, 82 filled BUY/SELL transactions, paid
219.06 USDT fees over the period at nominal cost.
Exposure averaged 23.63%, with maximum ~78.21%.

### Cash-scaled BTC baseline: diagnostic only

Take initial BUY-HOLD BTC exposure of 23.63% and keep the
remaining 76.37% in zero-yield cash, retaining the original
BTC benchmark daily price path. This gives a mechanical
+39.07% cumulative return and ~29.02% max DD, compared
with active 5-name gate's +118.21% and 14.78%.
This reference is **post-hoc matched to realised average
exposure**, not a prospective independent reference
strategy, and cannot establish causal alpha/significance.
The gate has dynamic exposure and diversified winners;
the static mixture has neither.

## Research decision

This is strategically different from v1-v10's frequent
entry/exit/stop tuning. A top-down portfolio can reduce
the number of false turning-point bets, avoid long bear
regimes and keep unused risk capital in cash.
**Research candidates**:
- conservative: risk_managed_gate, best multi-crypto
  4.3-year MDD and positive nominal/severe-cost result;
- growth-oriented: absolute_trend, but large drawdowns
  and concentrated bull years;
- passive comparison: BTC spot-equivalent buy/hold and
  five-asset monthly equal weight.

**NOT deployment approved.** Proven research issues:
(1) futures underlying OHLC is not actual tradable spot,
(2) futures funding is omitted, (3) 2021–26 data are
over-researched, (4) no truly untouched future period,
(5) volatility/correlation estimates can fail violently,
(6) no taxes, slippage spikes, order book, cash interest,
(7) macro bull-run may dominate the experiment.

Further validation: actual historical spot OHLC, real
spot/futures transaction accounting, alternative data
providers, disjoint cohorts and a prospectively frozen
paper-trading sample without strategy re-optimization.
No changes to operational Wyckoff Track B/E, Telegram,
Supabase, Binance live systems.
