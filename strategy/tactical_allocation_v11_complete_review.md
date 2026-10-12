# Tactical Allocation V11 — FINAL strategic portfolio research

**Date:** 2026-10-12
**Original preregistered hypotheses:**
[tactical_allocation_v11_frozen.md](tactical_allocation_v11_frozen.md).
**GitHub Actions all jobs PASS (11 unit tests + three evaluation cohorts):**
https://github.com/DY0617/wyckoff-oos-public/actions/runs/38253573891.
Source: research/tactical-allocation-v11,
scripts/tactical_allocation_v11_core.py.

Research-only, no actual brokerage, Binance or Supabase orders.
No operational Track B/E or Telegram changes.

## Why this is different from v1–v10

The old approach repeatedly optimized intraday entry/TP/SL signals
on the same 2021–2026 historical prices, while many apparent winners
failed transfer/cost stress. V11 instead attempts **top-down capital
allocation**: own strong-trend assets, allocate less to volatile
assets, and move to zero-yield cash when the market regime
weakens. Decisions strictly use the last FULLY CLOSED daily bar
and execute at the NEXT eligible month-open quotation. No
margin financing, no shorting, no averaging, no intraday stops.

## Results across three separate 20,000-unit portfolios

All returns cumulative unless marked CAGR. Fee+slippage
6bps EACH buy/sell side, plus predeclared 10bp and 20bp
cost stress. Max DD on daily-close marked equity.

| Cohort | Policy | Cum. return | CAGR | Max DD | Avg invested | 20bp/side stress |
|---|---|---:|---:|---:|---:|---:|
| BTC/ETH 2021-09 to 2026-09 | BTC buy-hold | +100.32% | 14.91% | 76.67% | 100% | +100.05% |
| BTC/ETH | absolute_trend | +147.50% | 19.87% | 46.98% | 44.10% | +141.61% |
| BTC/ETH | risk_managed_gate | +58.66% | 9.67% | 17.46% | 16.43% | +57.03% |
| Five-asset crypto 2022-06 to 2026-09 | BTC buy-hold | +165.37% | 25.31% | 52.98% | 100% | +165.00% |
| Five-asset crypto | equal_monthly | +273.19% | 35.59% | 61.75% | 99.7% | +268.98% |
| Five-asset crypto | absolute_trend | +146.36% | 23.17% | 20.70% | 38.8% | +141.75% |
| **Five-asset crypto** | **risk_managed_gate** | **+118.21%** | **19.77%** | **14.78%** | **23.63%** | **+114.65%** |
| 29 selected US stock/ETF 2021-09 to 2026-03 | SPY buy-hold | +47.80% | 9.06% | 25.37% | 100% | +47.59% |
| 29 US names | equal_hold | +115.69% | 18.60% | 41.01% | 100% | +115.55% |
| **29 US names** | **absolute_trend** | **+104.91%** | **17.26%** | **12.63%** | **54.8%** | **+101.62%** |
| 29 US names | momentum_top | +243.45% | 31.50% | 38.47% | 91.0% | +223.12% |
| 29 US names | risk_managed_gate | +101.40% | 16.81% | 18.13% | 46.8% | +93.76% |

All seven arms (including full annual details and 10bps stress)
are preserved in downloadable artifacts on the GitHub Actions run.
No arm is omitted merely for failing.

### Risk-sensitive comparisons

1. **Five-asset crypto:** cash-defense/volatility-sizing
   has +118.21% growth at daily-close MDD ~14.78% (average
   invested fraction 23.63%), versus BTC buy/hold +165.37%
   but -52.98% MDD. Buy/hold would require enduring
   enormous underwater periods; tactical defense gives up
   some upside to reduce those losses.
2. **Selected US equities:** the pre-frozen absolute-trend
   arm made +104.91%, MDD 12.63%, vs SPY +47.80%,
   MDD 25.37%. This particular stock research portfolio
   is retrospective and has severe survivorship bias.
3. **Weakness:** absolute_trend crypto BTC/ETH MDD still
   ~47%. Momentum_top stock +243% came with 38.47% MDD.
   Choosing these only for return would disregard the
   user's goal of consistent loss control.
4. The five-asset market-gated risk portfolio has
   82 BUY/SELL executions total, simulated paid entry/
   exit costs ~219.06 USDT, final marked account 43,642.39.
   Daily cash never negative and max exposure ~78.2%,
   mean 23.63%. Lower losses partly reflect large cash
   holdings; the strategy does NOT promise profit monthly.
5. Market-gated five-asset year return:
   2022 partial 0.0%, 2023 +21.3%, 2024 +55.8%,
   2025 +7.4%, 2026 partial +7.5%.
   The largest individual monthly loss was ~-9.82%,
   i.e. sharply negative months can still occur.
6. Stock absolute_trend by calendar year:
   2021 partial +7.1%, 2022 -10.6%, 2023 +25.5%,
   2024 +41.1%, 2025 +17.5%, 2026 partial +2.9%.
   It is NOT a constant positive equity curve.

### Independent verification

The full five-crypto JSON artifact (#11749188049) AND
stock JSON artifact (#11749552241) were downloaded and
their daily-equity/ledger totals independently checked.
For all 7 modes in both:
- final marked equity = 20,000 * (1 + reported total return),
- cash >=0 barring sub-nanodollar floating precision,
- contemporaneous gross position notional <= total
  portfolio equity, no implicit borrowing,
- paid fees independently sum to the recorded ledgers.
Eleven targeted causality/funding/portfolio tests pass in
GitHub Actions. This is accounting consistency,
NOT independent verification of underlying price accuracy,
execution feasibility or market alpha.

### Risk-matched passive diagnostics (POST-HOC only)

For illustration, we can start with an *initial dollar
slice* of SPY or BTC equal to the tactical strategy's
observed average invested exposure, keeping all remaining
cash uninvested without rebalancing. This is NOT the same
as a predeclared same-risk benchmark or time-varying
exposure comparison:
- five-asset market-gated invested exposure mean 23.63%:
  23.63%-initial BTC plus cash would return **+39.07%**
  with max DD **29.02%** on the same reference dates,
  vs tactical **+118.21%**, DD **14.78%**.
- selected stock absolute_trend mean 54.8%: a static
  54.8%-initial SPY plus cash proxy would return **+26.20%**
  with max DD **14.42%**, vs tactical **+104.91%**,
  DD **12.63%**.
These post-hoc weights are only diagnostic; one cannot
infer a statistically significant outperformance from them.

## Most serious limitations

1. **Crypto data are BINANCE USDT-M FUTURES KLINES,
   yet the allocation accounting is SPOT-LIKE fully funded
   long inventory. Perpetual contract funding/mark-to-market
   margin/liquidations are NOT modelled. It is a directional
   price-only research proxy, neither a runnable Binance
   futures strategy nor verified historic spot PnL.**
   Actual Binance spot candles and exchange wallet mechanics
   are required before even paper-trading.
2. Historical 2021–2026 dates and these crypto/US assets
   were examined through ten previous strategy families.
   The v11 design was frozen before this batch, but the
   sample is now heavily research-selected, NOT untouched
   calendar OOS. Need an embargoed future window.
3. US contemporarily-selected 29 symbols all survived into
   the research set. Dividends, symbol mergers, splits and
   delisted constituent history are not fully adjusted;
   both the excellent portfolio and passive stock basket
   returns can be seriously biased.
4. Benchmarks exclude interest on cash; cash yield can
   improve defense approaches. No settlement/day-trading
   restrictions, capital gains tax, exact order-book spreads,
   slippage after gaps, exchange outages, future shock
   correlations or intraday MDD are modeled.
5. The "18%/12% volatility target" is an ex-ante
   position-weight heuristic, NOT a guarantee that
   realized portfolio volatility equals those numbers.
   No forecast correlation, actual borrow availability,
   dynamic funding spread or fill liquidity model.

## Verdict

**Meaningful candidate mechanism now exists**:
conservative cash-funded trend/dual-momentum portfolio
with a positive risk-control track record *in retrospective
price-only simulations*. Different from an intraday
Wyckoff reversal strategy and much lower turnover.

**Not production-approved**. Do not move risk capital,
change Wyckoff B/E, automate orders, or raise leverage
on the basis of this backtest alone.

Recommended next controlled test: pull genuine
SPOT (not futures) daily exchange candles and separate
survivorship-free / delisted-aware US equity source,
freeze all current parameters, replay a forward-held
paper portfolio with realistic commissions/slippage,
cash interest and mark-to-market risk. Compare against
SPY and BTC benchmark and passive equal-risk holdings.
