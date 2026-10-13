# Final selection v2 — predeclared before new exit tests and candidate holdout

2026-10-13. Objective: select the most defensible BTC long-trend research strategy among a finite set, not maximize one backtest total. Native sizing is 0.5% cost-inclusive stop risk for entries and the previously defined daily volatility strategy. No live orders or deployment.

## Candidates and exits
- Entries: frozen D and C_simple. A/B lost in training; C had insufficient trades. Do not retune them.
- Shared daily regime and signal availability remain unchanged.
- Six exits per entry: original 2ATR initial / 3ATR full-position trail; fixed 2R; fixed 3R; structural SL (lowest low of last 5 closed 4H bars minus 0.25ATR) / 3ATR trail; 20/20/60 (1R, 2R, runner; BE after first target's 1H close, lock 1R after second target's 1H close, 3ATR runner trail after TP2); initial 2ATR stop with daily-regime-only positive exits.
- Fixed R targets use entry adverse fill minus initial reference stop as price R. Fees reduce realized R. Same-hour ambiguity: carried stop first, targets second. Stops raised by targets become active only next 1H; 4H trailing updates activate only after 4H close. Funding uses remaining quantity.
- One position, no pyramiding. Hourly zero-volume bars are not executable. Structure-stop invalidation rejects entry if stop is at/above its fill. Notional cap is 1x at entry after fees.
- Include daily trend and daily vol_trend as eligible fallbacks; daily hold/vol_hold remain controls, not eligible trend strategies.

## Ranking and robustness
Train: 2020-2022; validation: 2023-2024. Ranking never consumes candidate 2025+ performance.
1. Use each model's training realized annual volatility to set a constant multiplier targeting 2% annual training volatility (no upward scaling: multiplier <= 1). This is a common low-risk reference, not the final live risk target. Re-run costs under actual resized quantities rather than multiplying an equity curve.
2. Require positive train and validation net returns under both base (5/2 bps) and doubled (10/4 bps) execution costs; entry strategies require >=20 completed trades in each period and <10% native MDD in each period. Baselines use episodes as descriptive counts, not 20-trade gate (different turnover model).
3. Rank by the lower of train and validation CAGR/absolute MDD at common training risk. Ties: better doubled-cost lower-period Calmar, then fewer fills. Guard near-zero MDD numerically. Report baseline controls and realized future risk as well.
4. Fixed one-at-a-time entry neighbors: lookback 16/24 around 20; initial ATR 1.75/2.25 around 2 for nonstructural stops; trail 2.5/3.5 around 3 for trailing modes; ADX 18/22 around 20 for D. Structure neighbors use 3/7 prior bars around 5. Do not select a neighbor's return as a new optimum. Eligible center must have >=75% neighbors profitable in BOTH train and validation with doubled costs. Test all centers and retain failures in logs.
5. Freeze the first ranked eligible center and its exposure multiplier before holdout. Also freeze comparator identities (daily vol_trend and the original D/C_simple centers) as descriptive controls; controls cannot replace the winner after inspecting holdout.

## Candidate holdout and verdict
Acquire 2025-01 through 2026-09 hourly data, audit sources, and preserve observed discrepancies before performance inspection. Evaluate frozen winner and frozen controls once over 2025-01-01 to 2026-10-01. The old engine's holdout lock remains unchanged. A separate v2 runner checks a saved selection registry and creates an opening record before holdout simulation.
This is an internally reserved retrospective holdout, not provably untouched OOS across the user's earlier projects. If the selected center fails holdout, report failure; do not promote a different strategy on the same holdout.
Live eligibility requires positive net holdout return, doubled-cost nonnegative return, MDD <=10% at declared native risk, and at least 15 holdout trades for a 4H strategy. Even passing this screen is only a paper-trading candidate: no historical precision/depth/liquidation model or genuine forward OOS has been validated. If no candidate passes, name a research reference but say no live-qualified winner exists.

Before holdout, also register the selected winner at native sizing (scale 1) to report interpretable 0.5% stop-risk results and test that declared native risk gate. This is a predeclared sizing sensitivity, not a choice made after inspecting holdout performance. Selection ranking remains at common train-risk scale. Native daily benchmark risk is its fixed prior formula, not a stop-risk claim.

Before any holdout return is calculated, also freeze the train/validation runner-up at common and native sizing as a descriptive control. This does not alter the primary winner or authorize swapping to the runner-up after opening holdout.

No further parameter or exit search after opening this holdout. Actual rates and boundary mark valuation remain distinct. No fixed TP for the daily fallback: its exit is the closed daily regime, not an invented price target.
