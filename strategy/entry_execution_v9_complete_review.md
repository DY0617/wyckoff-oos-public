# Entry First v9 — FINAL full-market decision (October 12, 2026)

All jobs in [GitHub Actions run 38232291484](https://github.com/DY0617/wyckoff-oos-public/actions/runs/38232291484)
completed SUCCESSFULLY: 14 causal/fee/limit/baseline-parity unit tests and
three independent cohort backtests (BTC+ETH, BNB+SOL+XRP, selected US RTH stocks).
All changes remain in `research/entry-execution-v9`; **NO LIVE orders,
Supabase, Telegram, Track B/E, or production workflows modified**.

Pre-results hypotheses: [entry_execution_v9_frozen.md](entry_execution_v9_frozen.md).
Detailed crypto attribution: [entry_execution_v9_crypto_results.md](entry_execution_v9_crypto_results.md).

## Fixed setup

All arms use the same original Entry First v8 confirmed-4H
liquidity-sweep signal, structural support/extreme STOP and frozen
+2R target; no averaging, partial targets, or stop widening.
Planned maximum stop exposure 0.5% of then-current marked
equity per trade INCLUDING stressed estimated fee; 70%
single-position equity notional cap, <=3 concurrent open
plus RESERVED pending limits, starting 20,000 USD/USDT.
Conservative OHLC stop-first execution, historical crypto funding
approximation, 6bp total transaction cost each fill side and
10bp each side stress; 1H-close MTM drawdown (not worst intrabar).

## Cross-asset headline table, NOMINAL transaction cost

| Candidate | BTC+ETH return | BNB+SOL+XRP return | US stock return | Robust across markets? |
|---|---:|---:|---:|---|
| next-open market (control) | +20.40% | -8.95% | +0.63% | NO |
| next-open market + avoid 4H shock | +30.08% | -5.86% | +0.98% | NO |
| half ATR pullback resting limit | -13.48% | -2.04% | -35.49% | NO |
| reclaimed support resting limit | -33.19% | -21.44% | -42.50% | NO |
| swept-extreme close resting limit | -34.63% | -35.35% | -36.21% | NO |
| half ATR limit + shock avoidance | +3.26% | -1.80% | -32.70% | NO |
| reclaimed support limit + shock avoidance | -29.99% | -22.79% | -44.78% | NO |
| half ATR limit only 2h validity | -27.13% | -12.94% | -35.12% | NO |

Period differs by sample:
BTC+ETH 2021-09-28..2026-09-28 exclusive (~5y);
BNB+SOL+XRP 2022-06-01..2026-09-28 exclusive (~4.3y);
US RTH 2021-09-28..2026-04-01 exclusive (~4.5y).
Returns are *not* comparable as if the same dates/instruments.

### High-cost stress defeats every arm in every market

With an additional +4bp EACH entry/exit side,
- BTC/ETH market+shock +30.08% => **-1.56%**.
- BTC/ETH unfiltered market +20.40% => **-8.58%**.
- BTC/ETH half-ATR limit -13.48% => **-35.55%**.
- New-alt market+shock -5.86% => **-30.37%**.
- New-alt half-ATR limit -2.04% => **-29.64%**.
- US market+shock +0.98% => **-16.71%**.
- US half-ATR limit -35.49% => **-47.43%**.

### Fill dynamics

BTC/ETH: half-ATR 991/1338 limit orders filled (74.1%);
reclaim-level 856/1440 (59.4%); deeper extreme 804/1721
(46.7%). Deeper discounts led to fewer fills AND worse PnL.
US: half-ATR 757/1089 fills (69.5%). Average MAE ~0.845R
vs ~0.776R with immediate market entries, consistent with
adverse selection following retracement rather than precision
buying. New alt half-ATR 1224/1635 (74.9%), but also negative.

All limit trade fills assume price TOUCH guarantees 100%
quantity: optimistic queue/market depth assumption. It is
not an actual executable fill guarantee. STOP-first when
fill and stop levels touched within the same 1H candle, and
pending orders tie up portfolio position slots.

### Why v9 is NOT ready for real trading

- Positive nominal BTC/ETH market+shock profit is fragile and
  flips negative on the preregistered +4bp/side fee stress.
- Same entry-selection filter fails on new crypto futures symbols.
- All limit-only policies are negative nominal in all three cohorts,
  except limit-half+shock mildly +3.26% on known BTC/ETH and
  it fails cost stress (-23.42%). No robust expectation edge.
- Stock selected symbols are survivorship biased; crypto
  funding settlement at hourly close is approximate; no full
  order-book queue, variable spread, liquidation, exact
  intrabar path, or bar-scale mark-to-market maximum excursion.
- MAE/MFE at limit entry-bar contains unknown high/low
  sequencing; MFE may overstate actual reachable favorable
  excursion within fill candle, even though TARGET is
  never credited on that first candle. Do not use intrabar
  MFE differences as validated alpha.
- The return on the same known 2021-26 dates is NOT untouched OOS.
  Many previous experiments exposed these dates/underlyings,
  causing material selection risk.

## Decision / engineering next steps

**REJECT all eight as production alpha.** Keep the branch and reports
as reproducible negative evidence; no strategy replacement,
automation or risk-size increase based on these outputs.

What would credibly improve research:
1. Obtain genuine NEW calendar periods/venues and disjoint symbols,
   with an enforced frozen parameter manifest / walk-forward embargo.
2. Evaluate execution using 1m or trade-tick sequence and actual
   bid/ask, marketable order types, limit queue depth and partial
   fills. Never count mere OHLC touch as guaranteed filled.
3. Benchmark trade-by-trade risk-equivalent passive trend and
   NO-TRADE cash hold alternatives, annual after-fee alpha,
   account-level portfolio MDD and tail stop-gap losses.
4. For price discovery, design an entirely independent mechanism
   (auction imbalance / realized volatility transition) rather
   than continuing to tune four existing over-explored pivot
   and Bollinger variants. Pre-register distinct economic thesis
   before exploring it.

No future results are promised; there is currently NO validated
stable-upward-equity algorithm from the tested Entry First/Stacker
family. That is an actionable conclusion and prevents avoidable
capital loss from poorly supported automation.
