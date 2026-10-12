# V10 capital-constraint audit — COMPLETE research verdict

2026-10-12 GitHub Actions successfully completed:
https://github.com/DY0617/wyckoff-oos-public/actions/runs/38251062100

All **6** dedicated audit invariants PASSED, including:
- original v8 simulator == independently forked cash auditor
  when cash restriction disabled (exact metrics/trade parity);
- 3 concurrent 70%-notional stock positions can exceed fully
  paid-for cash in original simulator;
- enforced stock cash reservations NEVER finance more
  gross purchase amount plus entry fees than realised cash;
- futures are untouched by stock-specific cash requirements;
- smaller funded positions correctly reduce entry cost loss;
- one-share group with available cash produces baseline parity.

**This is retrospective and hypothetical, not audited live PnL.**
Same predeclared v10 expansion/volume/compression signals and
2R structure stop as original; no re-optimization/reselection.

## Direct re-simulation: 29 selected US RTH stocks, 2021-09-28
through 2026-04-01 exclusive, $20,000 initial equity

| Arm | Original margin-implicit net | Cash-funded net | Cash-funded with +4bp each side | Trades | Down-sized due to insufficient unreserved cash | No-cash rejected |
|---|---:|---:|---:|---:|---:|---:|
| compression | **+13.8648%** | **+13.0864%** | **+7.9977%** | 237 | 7 | 0 |
| relative_strength | +12.4747% | +11.7196% | +2.8924% | 448 | 10 | 0 |
| compression_volume | +6.5677% | +6.5677% | +5.3821% | 69 | 0 | 0 |
| range_break control | -11.7441% | -12.1543% | -20.1208% | 522 | 11 | 1 |

The auditor reuses ALL original confirmed daily/4H signals,
same chronological 1H next-open entry, stop-first priority,
cost and equity marking. When a new stock order would exceed
cash available after reserving every other outstanding
position's **original full purchase notional and entry fee**,
the new fill is scaled down to available cash. If no funds
remain, the order is skipped. Fractional shares assumed.
No artificial stock leverage or silent margin borrowing.

## Concentration is worse than headline still-positive return

- Cash-funded compression net is ~$2,617.28 after 4.5y.
- Of this, 2023 entry-year gains represent almost all.
- **Excluding 2023 entry-year PnL leaves only +$11.80**
  across all other evaluated years (this is an additive
  trade-attribution sensitivity, NOT a re-simulated strategy).
- Excluding the best ten CASH-FUNDED trade PnLs leaves
  just +$541.26 total, again additive sensitivity without
  re-simulation.
- No claim of smooth profitability or prospective OOS.
- Newer years 2025 and early 2026 lost money on the
  historically best-performing v10 stock variants.
- The selected contemporary 29 stocks have survivorship
  and universe post-selection bias. Split detection was
  heuristic and no dividend/broker/share-borrow/corporate-action
  settlement model can guarantee the research outcomes.
- The more permissive old v10 source displayed up to
  $31,024 in simultaneous purchase notional for stock
  `compression` on $20,000 initial cash, at one moment
  ~132% of contemporaneous marked account equity.

## Additional monthly distribution audit

Recomputed from original v10 full trade ledgers (no live data):
- Stock compression: month-block resampling 12k replicates,
  total PnL 2.5%–97.5% quantiles approximately
  **-$1,544 to +$7,413** (55 historical entry months).
- BTC/ETH market regime: approximately
  **-2,427 to +5,740 USDT** (61 months).
- New-asset market regime: approximately
  **-4,677 to +4,085 USDT** (52 months).
These are not frequentist confidence intervals and NOT
formal future-profit probabilities: monthly resampling
ignores serial dependence, overlapping positions, trade
risk changes, multiple-hypothesis search and year-regime
nonstationarity. They only illustrate fragility of an
already repeatedly mined historical sample.

## Interpretation and launch criterion

**Audit PASSED on engineering; statistical profitability NOT
validated.** The original +13.86% stock return shrinks to
+13.09% under cash funding and +8.00% under extra costs, but
profit outside 2023 is effectively zero. No valid claim
of a robust stable growth engine.

Further required before any live order:
- collect a truly *new* calendar interval, survivorship-free
  stock constituent history and split/dividend ground truth;
- exact 1m/tick sequencing for stop/TP same bar,
  simulated queue/book depth and realized entry/exit fees;
- unlevered passive/cash risk-equal comparisons,
  return concentration diagnostics and funding/margin model;
- prospectively freeze ONE hypothesis and run in paper mode
  without post-hoc feature selection.

Original Track B/E, Binance execution, Telegram and Supabase
remain **UNMODIFIED**.
