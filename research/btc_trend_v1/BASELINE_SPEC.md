# Baseline v1 — frozen before execution, 2026-10-13

## Data policy
Primary study uses USD-M traded-price daily/4H and mark-price 4H, 2020-01-01 through 2026-09-30. Daily regime is calculated from official spot daily closes, including pre-2020 warmup. Spot daily is a separate diagnostic, never a substitute for futures fills. Ignore volume in this price-only baseline; retain known discrepancies. Spot 4H anomalies are not used. No interpolation or fabricated candles. All selected futures traded/mark bars must be complete and contiguous; missing marks/funding fail execution. Historical 2019 futures data are unavailable; no performance is claimed there.

## Rules
- Regime: most recently closed UTC spot daily close > SMA of last 200 closes and > close 90 bars earlier. Strict inequalities. Decision at next UTC daily open.
- Buy & Hold: daily weight 1.0.
- Trend: daily weight 1.0 if regime true, otherwise 0.
- Volatility trend: same regime; daily weight min(1, 0.20 / trailing-60-close-return sample volatility annualized with sqrt(365)). Twenty percent is a new, predeclared research target, not the unknown original formula.
- Volatility Buy & Hold: same volatility sizing without regime, for a common ex-ante volatility target comparison.
- One long position; no leverage above target 1x at rebalance. Daily rebalancing includes fees on quantity changes. Futures funding can change leverage between rebalances.
- Initial equity 10,000 USDT. Continuous quantities; historical tick/step filters unavailable, so no executable exchange rounding claim.
- Fees 5 bps per traded notional per side, adverse slippage 2 bps per fill: research assumptions, not verified account fees. Stress both at 2x. Zero-cost diagnostic keeps futures funding (do not call this frictionless).
- USD-M funding: actual archive rate × held BTC quantity × contemporaneous 4H mark-open proxy. Mark is sampled at nominal settlement boundary; archive settlement time can be 0–47ms later. This is a documented valuation approximation, not exact settlement-tick accounting.
- Primary convention: nominal settlement at daily rebalance boundary applies to quantity held immediately before rebalance. Also run after-rebalance convention to measure timing sensitivity. Preserve actual archive timestamps in settlement ledger.
- Price ledger is linear: equity = virtual quote balance + quantity × mark. This is an equivalent futures PnL ledger, not the exchange's margin-wallet representation. Fees/slippage and funding reduce equity; interest on collateral is zero. Liquidation and historical maintenance tiers are not modeled. 1x cap is not a live liquidation guarantee.
- Terminal position exits at last traded close with adverse costs; report terminal exit as such.
- No fixed TP or SL: this is the original regime benchmark, not the final 0.5% stop-risk strategy.

## Reporting
Fresh-equity period runs: 2020–2022 train, 2023–2024 validation, 2025–2026-09 retrospective baseline holdout, 2020–2026-09 full, and 2021–2026-09 original-claim diagnostic. All indicators warm up from earlier data, never reset at report boundaries. Baseline holdout performance is allowed for benchmark description; entry-candidate holdout remains unopened until selection. This past window is not provably untouched OOS.

Use daily-close returns for Sharpe (zero risk-free rate, sqrt(365)); MDD from observed 4H marks for futures, daily closes for spot. Also expose conservative intrabar mark-low drawdown separately. These sampling frequencies must be stated in comparisons. Completed regime episodes provide PF/expectancy; terminal liquidations are labeled, rather than called natural signals. Record all daily fills and funding payments. Yearly returns are slices of continuous equity, not sums of trade R.

Accept/reject: reproduce exact exploratory numbers only if source/endpoints/original execution match. Otherwise report new independently defined measurements and differences. Do not optimize any baseline setting against the retrospective holdout.
