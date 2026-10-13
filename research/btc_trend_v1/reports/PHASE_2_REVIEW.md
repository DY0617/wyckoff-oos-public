# BTC research phase 2: actual baseline and entry screening

Executed 2026-10-13. No live orders, database or Telegram changes. Candidate performance after 2024 remains locked. All returns below are simulated results on acquired official BTCUSDT data, not real-account results.

## Independently defined daily benchmark (2021-01-01 to 2026-09-30)

| Market | Rule | Return | CAGR | MDD | Sharpe | Episodes |
|---|---|---:|---:|---:|---:|---:|
| spot | hold | 188.71% | 20.25% | -76.63% | 0.608 | 1 |
| spot | trend | 350.69% | 29.93% | -49.00% | 0.863 | 29 |
| spot | vol_hold | 89.52% | 11.76% | -35.86% | 0.629 | 1 |
| spot | vol_trend | 101.50% | 12.96% | -17.26% | 0.896 | 29 |
| um | hold | 55.06% | 7.93% | -79.08% | 0.419 | 1 |
| um | trend | 169.81% | 18.84% | -55.48% | 0.635 | 29 |
| um | vol_hold | 52.75% | 7.64% | -37.36% | 0.452 | 1 |
| um | vol_trend | 69.40% | 9.60% | -19.92% | 0.692 | 29 |

Fees 5 bps/side and slippage 2 bps/fill are assumptions. USD-M uses actual funding rates and 4H mark-open proxies. Futures MDD is 4H mark-close; spot MDD is daily-close, so sampling differs. The original +280.5% / +125.6% claims were not reproduced under authenticated original inputs; the previous exact source, endpoint and volatility formula are unknown. New independently defined benchmark rules are in BASELINE_SPEC.md.

Funding impact is large: trend without funding (diagnostic only) returns +351.32%; with funding +169.81%. Cash notional changes with funding and rebalancing, so this difference is not simply the dollar sum of payments divided by starting capital. A zero-execution-cost scenario still includes funding.

## Frozen 4H entries, verified against 1H execution

| Rule | Train 2020-2022 return | Validation 2023-2024 return | Validation MDD | Trades | Net R/trade | PF in R |
|---|---:|---:|---:|---:|---:|---:|
| A | -0.94% | 2.40% | -7.27% | 58 | 0.088 | 1.193 |
| B | -2.48% | 4.36% | -2.94% | 35 | 0.251 | 1.566 |
| C | 0.00% | -0.50% | -0.50% | 1 | -1.000 | 0.000 |
| C_simple | 5.94% | 13.58% | -3.39% | 94 | 0.279 | 1.732 |
| D | 0.48% | 9.08% | -1.95% | 33 | 0.534 | 2.612 |

All entries use 0.5% cost-inclusive initial stop risk, 1x entry notional cap, shared 2ATR initial stop and 3ATR trail; no fixed TP. Thus this pass isolates entry hypotheses under one exit. Risk never exceeded 0.5% in planned initial losses; gap losses and ongoing funding can exceed planned risk. One-hour prices/timing were checked on 43,848 bars. One-hour and corrected four-hour simulated PnL were identical; this does not establish real-world fill quality.

C with added trend-recovery filters produced zero train trades and only one validation loss: rejected in its frozen form. A and B passed the minimal validation screen but lost in train. D and C_simple are the two highest-ranked validation expectancy candidates, not approved trading systems. No threshold was optimized after seeing results.

## Same training-risk benchmark comparison

| Candidate reference | Validation candidate return/MDD | Daily vol-hold matched return/MDD | Interpretation |
|---|---|---|---|
| D | 9.08% / -1.95% | 9.66% / -1.69% | No clear entry advantage |
| C_simple | 13.58% / -3.39% | 13.22% / -2.28% | No clear entry advantage |

Exposure scales use only 2020-2022 realized volatility. They are frozen for validation; future realized volatility is allowed to differ. Do not compare the 0.5%-stop-risk entries with unscaled 1x daily benchmarks as if they had equal risk.

## Robustness and uncertainty

- D validation: +0.534R/trade; doubled execution costs +0.463R/trade. Validation block-bootstrap 95% intervals are positive for block sizes 3/5/10. Train expectancy is only +0.032R; all train intervals include losses. Removing the best train trade makes train total R negative. This weak training result prevents a strong persistent-edge claim.
- C_simple: positive train and validation totals; best-trade removal still leaves both positive. Validation bootstrap interval crosses zero for block sizes 3 and 5; uncertainty remains.
- A validation loses money if its best trade is removed. B train is negative. C filtering greatly suppresses sample size.
- Bootstrap intervals are descriptive, not corrected for five candidate comparisons, and may understate regime/model uncertainty. PF and net R are not a future-income guarantee.

## Data reconciliation and execution limits

- All 54 missing monthly mark-price bars were obtained from SHA256-verified official daily archives. Mark sequence is contiguous.
- 2023-11-10 12:00 UTC monthly 4H close/volume conflicted with official daily 4H and both monthly/daily 1H. Canonical execution uses the verified daily 4H bar. Originals and exact source/hash are preserved in execution_source_policy.json.
- 2024-10-28 20:00 UTC is a zero-volume 1H bar. It provides no tradable print. Hourly aggregation and fills skip it and use the first nonzero-volume hourly open. This reproduces the official 4H traded OHLC.
- One remaining 1H/4H volume mismatch is recorded; price-only entry rules do not consume volume.
- Funding uses actual rate and held quantity, but mark sampled at nominal boundary is a proxy for the true 0-47ms delayed settlement mark. Before/after-rebalance payment timing was tested for the daily benchmark.
- Continuous quantity, assumed spreads/slippage, no exchange queue or depth, no historical tick/step/maintenance-margin tiers. 1H candle sequencing is not tick-level execution validation.
- Max drawdown quoted in tables is observed 4H mark-close drawdown; intrabar drawdown can be worse.

## Decision / remaining work

**Live use: NOT APPROVED by this research.** The daily regime has useful historical behavior, but a durable incremental benefit from refined 4H entries has not been demonstrated. D and C_simple are retained as research hypotheses; C is rejected in this form.

Next, freeze candidate centers and run limited predeclared parameter-neighborhood stability, compare the requested structural stops / fixed targets / 20-20-60 exits under identical risk, then evaluate selected frozen rules on 2025-2026 retrospective holdout. Do not call that historically exposed window genuinely untouched OOS. True untouched OOS requires subsequently arriving data after rule freeze. Streak/DD guards and executable exchange rounding still need explicit testing.

## Reproduction and evidence

- README.md and requirements.txt: reproducible commands; workflow source is research-only.
- scripts/test_causal_engine.py: independent fill arithmetic, cost-aware sizing, future-perturbation invariance, availability-time and risk-cap checks, candidate holdout lock. All passed.
- baseline_v1/: all benchmark metrics, fills, funding payments, episode logs, equity and drawdown plots.
- entries_v1/: frozen entry screening, cost/risk sensitivities, chronological trade logs and bootstrap report.
- entries_1h/: actual hourly execution verification, corrected trade/fill logs and train-risk-matched baseline comparisons.
- mark_manifest.json, mark_daily_repairs.json, execution_1h_audit.json, execution_anomaly_daily.json, execution_source_policy.json: exact sources and source correction evidence.
