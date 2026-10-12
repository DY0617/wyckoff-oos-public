# Tactical v12 — FINAL actual spot revalidation and portfolio defenses

Date 2026-10-12. All GitHub Actions jobs SUCCESS:
https://github.com/DY0617/wyckoff-oos-public/actions/runs/38256421439
Tests: 13 dedicated invariants passed, plus required EXACT parity
checks against all seven preexisting V11 modes on corrected
input source. Frozen hypotheses: [tactical_v12_frozen.md](tactical_v12_frozen.md).
Crypto details: [tactical_v12_spot_results.md](tactical_v12_spot_results.md).

**Original independent research, historical simulator,
NOT a current portfolio, verified forward alpha, or trading advice.**
No production Binance, Supabase, Wyckoff Track B/E or Telegram changes.

## Engineering work completed

1. Replaced v11 crypto USDT-M futures price proxy with **actual
   Binance spot 1-D archived OHLCV**, strict UTC timestamps,
   spot provenance, contiguous complete daily bars, fatal failures
   on missing months/gaps/duplicate timestamps/invalid OHLC.
2. Preserved v11 portfolio BUY/SELL, 200d EMA, 63d momentum,
   60d vol, 6bps costs/side, cash funded <=100% gross,
   original portfolio monthly next OPEN, one-way unlevered
   long and cash positions. Added V11/V12 exact same-market
   trade/PnL equivalence assertions, passed.
3. Added three previously frozen defensive arms:
   * `gate_weekly`: same regime/weights, ISO weekly turnover.
   * `gate_cap`: monthly original BTC/SPY gate, each
     position's *rebalance target* <=20%, total portfolio
     risky TARGET weight <=50%.
   * `gate_crashguard`: monthly gate + prior 30-completed-day
     benchmark trailing drawdown >=15% -> cash.
4. All ten policies retested with 6bps nominal cost per SIDE,
   severe 20bps/side, and optional ILLUSTRATIVE 3% APY
   on available idle cash, not claimed historically tradable.
   Stores trade ledgers and daily marked-equity curves.

## Three independent research portfolios

Separate, equally starting accounts 20,000 USD/USDT.
CAGR annualised, MDD daily closing-mark, NOT within-day extrema.

| Market cohort | Arm | Cum. return | CAGR | MDD | severe 20bps per-side return | Average risky invested |
|---|---|---:|---:|---:|---:|---:|
| BTC/ETH ACTUAL spot, 2021-09..2026-09 | BTC buy-hold | +100.30% | 14.91% | 76.63% | +100.02% | 100% |
| BTC/ETH spot | **v11 gate monthly** | **+58.95%** | **9.71%** | 17.44% | +57.32% | 16.5% |
| BTC/ETH spot | gate_weekly | +50.99% | 8.59% | 15.12% | +47.49% | 17.3% |
| BTC/ETH spot | gate_cap | +55.03% | 9.17% | 17.19% | +53.76% | 14.6% |
| BTC/ETH spot | gate_crashguard | +48.64% | 8.25% | **12.17%** | +47.14% | 15.1% |
| All five ACTUAL spots, 2022-06..2026-09 | BTC buy-hold | +165.47% | 25.32% | 52.97% | +165.10% | 100% |
| Five crypto spots | **v11 gate monthly** | **+118.28%** | **19.78%** | 14.79% | +114.77% | 23.7% |
| Five crypto spots | gate_weekly | +137.52% | 22.14% | 20.04% | +127.05% | 25.3% |
| Five crypto spots | **gate_cap** | **+89.26%** | **15.89%** | **12.35%** | +86.81% | 20.2% |
| Five crypto spots | gate_crashguard | +107.48% | 18.38% | 14.79% | +104.16% | 22.9% |
| Selected 29 US equity/ETF 2021-09..2026-03 | SPY buy-hold | +47.80% | 9.06% | 25.37% | +47.59% | 100% |
| US equity | v11 gate monthly | +101.40% | 16.81% | 18.13% | +93.76% | 46.8% |
| US equity | gate_weekly | +116.69% | 18.72% | 27.01% | +97.63% | 47.8% |
| US equity | **gate_cap** | **+65.06%** | **11.76%** | **12.19%** | +60.77% | 32.8% |
| US equity | gate_crashguard | +101.40% | 16.81% | 18.13% | +93.76% | 46.8% |

### Observed tradeoff, NOT post-optimized winner

**Monthly original v11 risk_managed_gate remains most economical
overall in the five-spot cohort:** return +118.28%, MDD
14.79%, 83 fills. A faster weekly filter had 253 fills,
higher return but MORE drawdown (20.04%).

**Defensive gate_cap cuts marked drawdown in both five-asset
spot and US equity cohorts**, giving up material total
profits and lowering active exposure. The strategy does NOT
claim superior risk-adjusted returns automatically:
the changes might simply be a more cash-heavy exposure
position. Risk matching with a passive cash+BTC/SPY mix
chosen before data is still required.

**Important design limitation:** 50% is a *monthly
rebalance TARGET*, not permanent 50% holding ceiling.
By month-end before next rebalance, marked notional
can rise above 50% purely from asset price appreciation.
Observed maximum risky exposure:
five spot 57.4%, US stocks 56.2%. If strict
always-under-50% is operational requirement, an entirely
separate DAILY drift rebalancer triggered by prior close
and executed next session OPEN is needed, with additional
turnover and gap/slippage modeling. This version must
NOT be described as a hard risk guarantee.

The 30d drawdown crash-guard is not general:
for BTC/ETH it cut MDD 17.44 -> 12.17 but on five
spot names it did not improve MDD and in stocks it
had no effect on the already filtered monthly gate.
This is evidence against universally adding more
technical risk filters. Past-sample selection risk
makes cherry-picking one market inadmissible.

## Fair comparisons and market-data limits

- Cash-funded strategy has substantial idle assets:
  BTC/ETH gate mean exposure ~16.5%, five-crypto ~23.7%.
  Risk control results must be compared against
  **ex-ante predetermined** risk-matched passive mixes,
  not only 100% benchmark. That comparison has not
  been sufficiently completed here.
- All the actual SPOT OHLC archives represent Binance
  USDT spot-like price activity, not a guarantee of
  a current Korean user's available market, fees,
  fiat conversion or USDT transfer settlement.
  Perpetual futures have funding, liquidation,
  margin and basis costs that do not appear in
  these spot-ledger results.
- Original US equity data are still selected-survivor
  HF RTH OHLC. Dividends, delisted constituents,
  corporate actions and historical membership must
  be independently corrected. The high US backtest
  results may be considerably overstated. V12
  corrected the CRYPTO source mismatch, not stock
  survivorship data.
- Fee cost assumptions still a constant proxy;
  partial fills, tax, bid/ask spread shocks,
  24/7 downtime, weekends and cash interest
  actually obtainable over historical dates omitted.
- The 3% idle cash APY scenario is **illustrative,
  not a historical rate series** and may be
  unavailable, risk-bearing or taxable in real life.
- Daily-close MDD can miss intraday spikes.
  2021–2026 samples repeatedly researched in
  v1–v12, NOT truly untouched future OOS.

## Final honest assessment

**Improvement has been proven at the software/source
consistency level**: Binance SPOT corrected, v11
signal-engine parity preserved, capital fully funded,
risk/cash exposure audited, three new coherent risk
architectures compared. A portfolio-level return/risk
tradeoff is observable. NO strategy has been
independently proven to deliver future stable profits.

Preserve `risk_managed_gate` as the baseline candidate.
Preserve `gate_cap` as a lower-volatility/lower-growth
defensive candidate. Do NOT promote `gate_weekly`
or the month-end crash-guard as universally better.
No live orders, risk-size increases or production merge.

Next genuinely valuable research is to (a) validate on
fresh market dates acquired AFTER this strategy freeze,
(b) use an ETF/survivorship-free total-return dataset for
stocks, (c) verify live spot pricing and fills in paper
execution with a hard portfolio exposure limit, and (d)
test an independently predetermined risk-matched
passive benchmark with cash yield / funding / cost scenarios.
