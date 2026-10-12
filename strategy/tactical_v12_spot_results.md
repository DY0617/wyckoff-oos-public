# Tactical v12 — REAL Binance spot data, dual-cohort result audit

**2026-10-12** GitHub Actions run:
https://github.com/DY0617/wyckoff-oos-public/actions/runs/38256421439

13 unit tests passed. BTC/ETH and five-asset Spot evaluation jobs PASSED.
Risk variants and parameters frozen **before** return evaluation in
[strategy/tactical_v12_frozen.md](tactical_v12_frozen.md).

This work corrects v11's key data-provenance shortcoming: it uses
**Binance actual SPOT monthly 1-D candles**, NOT USDT-M futures-price
proxies, for cash-funded non-leveraged holdings. Daily source
timestamps, OHLC consistency, unique UTC days and complete sample
coverage are checked; missing/damaged source is a FATAL error rather
than optimistic substitution. All 7 unchanged v11 arms reproduce
identical account-level outcomes when fed the same updated data.

Accounting: each cohort has a separate hypothetical initial
20,000 USDT, nominal 6bp transaction fee/slip PER side, stress 20bp
PER side (no hidden borrow or shorts). Trading at next monthly
opening price from last completed daily indicator, cash >= 0,
gross notional <= current marked portfolio equity. 1-day-close
marked drawdown omits intraday crashes. 3% *cash yield*
is an explicitly NON-historical research scenario, not a
claim of guaranteed current or past bank rates.

## Actual BTC + ETH spot: 2021-09-28 through 2026-09-28 exclusive

| Mode | Net total | CAGR | Max DD | Average invested | 20bp cost stressed total | Illustrative 3% idle cash |
|---|---:|---:|---:|---:|---:|---:|
| BTC buy-hold benchmark | +100.30% | 14.91% | 76.63% | 100% | +100.02% | +100.30% |
| equal buy-hold | +46.12% | 7.88% | 76.80% | 100% | +45.99% | +46.12% |
| equal monthly | +48.30% | 8.20% | 76.19% | 100% | +47.61% | +48.30% |
| absolute_trend | +148.02% | 19.92% | 46.87% | 44.10% | +142.11% | +169.39% |
| momentum_top | +95.25% | 14.32% | 33.76% | 29.7% | +92.32% | +116.53% |
| risk_managed | +53.60% | 8.96% | 17.44% | 17.8% | +52.02% | +73.38% |
| **v11 risk_managed_gate** | **+58.95%** | **9.71%** | **17.44%** | **16.5%** | **+57.32%** | **+79.78%** |
| v12 gate_weekly | +50.99% | 8.59% | 15.12% | 17.3% | +47.49% | +70.51% |
| v12 gate_cap | +55.03% | 9.17% | 17.19% | 14.6% | +53.76% | +75.80% |
| v12 gate_crashguard | +48.64% | 8.25% | 12.17% | 15.1% | +47.14% | +68.46% |

### BTC+ETH implications
- Actual spot data refutes the idea that an anomalous futures
  price curve alone caused v11 simulated performance: within
  this historical period numbers barely changed.
- A monthly prior 30-day trailing-benchmark-drawdown
  guard lowered closing-mark MDD from 17.44% to
  **12.17%** but reduced total return ~10.31 points.
- Faster weekly rebalancing also reduced max DD, at the
  price of lower returns and 155 executions instead of 56.
- Cash-weighted defensive accounts earn less nominal
  growth than full BTC buy-hold (100.30% vs 58.95% for
  gate) because they intentionally sit in cash most days.
- These rules DO NOT impose an intramonth stop and can
  still experience a severe intervening gap.

## Actual FIVE-SPOT BTC/ETH/BNB/SOL/XRP, 2022-06-01..2026-09-28 exclusive

| Mode | Net total | CAGR | Max DD | Average invested | 20bp cost stressed total | Illustrative 3% idle cash |
|---|---:|---:|---:|---:|---:|---:|
| BTC hold benchmark | +165.47% | 25.32% | 52.97% | 100% | +165.10% | +165.47% |
| all-five buy-hold | +154.36% | 24.09% | 62.39% | 100% | +153.85% | +154.36% |
| all-five monthly equal | +273.64% | 35.62% | 61.74% | 99.7% | +268.90% | +273.79% |
| absolute_trend | +146.54% | 23.20% | 20.64% | 38.8% | +141.92% | +166.55% |
| momentum_top | +200.39% | 28.95% | 30.15% | 51.5% | +190.84% | +219.61% |
| risk_managed | +109.41% | 18.63% | 18.45% | 28.7% | +105.65% | +129.36% |
| **v11 risk_managed_gate** | **+118.28%** | **19.78%** | **14.79%** | **23.7%** | **+114.77%** | **+140.60%** |
| v12 gate_weekly | +137.52% | 22.14% | 20.04% | 25.3% | +127.05% | +160.90% |
| v12 gate_cap | +89.26% | 15.89% | **12.35%** | 20.2% | +86.81% | +109.22% |
| v12 gate_crashguard | +107.48% | 18.38% | 14.79% | 22.9% | +104.16% | +128.94% |

### Five-spot implications
- **risk_managed_gate has the better balance of return and risk**
  compared with weekly and the monthly crash-guard. It has
  lower max DD than weekly with only 83 transactions vs 253.
- At rebalance, **gate_cap TARGETS** <=20% per asset and <=50%
  risky gross. But positions drift between monthly
  rebalances: observed maximum mark-weight was **57.4%**.
  It is NOT an always-on 50% hard risk limiter. A true
  daily cap would require separately designed next-open
  drift-control sales and explicit fee and gap stress.
- gate_cap reduced MDD by roughly 2.4 percentage
  points vs v11 gate, but sacrificed ~29 percentage points
  of cumulative performance over 4.3 years.
- Monthly crashguard had no MDD benefit versus the original
  five-asset gate. Tail guards may be late to act when
  they only trade on monthly rebalance days.
- Weekly rebalancing raised return by ~19.2 points but
  worsened max DD by ~5.3 points and tripled execution
  count. No universal argument for faster rebalancing.

### Unexplained gains are NOT presumed skill
Backtesting since v1 repeatedly used these assets and
2021-26 samples, creating heavy multiple-comparison and
post-selection risk. The 3% idle cash scenario is purely
illustrative, NOT proof of an actual yield available
historically to all users. Costs are fixed proxies, not
actual maker/taker at transaction times, liquidity,
bid/ask spreads, or tax. No delisting, USDT depegging,
weekend service outages, halted transfers or broker
settlement mechanics modeled.

**Research status:** risk gating is supported as an
economically meaningful defensive mechanism on these
two related retrospective crypto datasets. This is NOT
validated future expected return; no real-money / API
orders are authorized. Do not retroactively choose a
different winning defensive overlay per market and call
it independent out-of-sample validation.

US selected equity analysis is a separate job in this run,
based on the prior HF source with known severe survivorship
and corporate-action limitations.
