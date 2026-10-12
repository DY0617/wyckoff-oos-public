# Entry First v10 — independent breakout, compression and participation research

October 12, 2026. GitHub Actions tests pass (13/13) and two
crypto cohort jobs have completed successfully.
Tracked run: https://github.com/DY0617/wyckoff-oos-public/actions/runs/38237159212
Pre-frozen hypotheses: [entry_expansion_v10_frozen.md](entry_expansion_v10_frozen.md).

**Our original research, NOT AGOS's proprietary strategy or real
trading results.** Same proven v8 event-driven portfolio stop/TP,
0.5% planned per-trade risk including estimated stressed fees,
single +2R TP, 3 open positions and 70% single-position notional;
6bps per side transaction cost + 4bps/side additional stress.
Binance historical funding estimate; one-hour closing-mark MDD.
BTC+ETH 2021-09-28—2026-09-28 exclusive, new-asset BNB/SOL/XRP
2022-06-01—2026-09-28 exclusive; independent simulated
20,000 USDT portfolios with DIFFERENT dates and instruments.

## BTCUSDT + ETHUSDT: 5-year original comparison cohort

| Predeclared arm | Trades | Return | PF | MDD | +4bp/side cost-stress |
|---|---:|---:|---:|---:|---:|
| raw 4H range_break | 372 | -11.76% | 0.895 | 16.45% | -16.48% |
| pre-break compression | 114 | -11.24% | 0.701 | 13.79% | -12.79% |
| 4H breakout volume confirmation | 265 | -10.31% | 0.871 | 15.24% | -13.70% |
| **prior-day BTC EMA200 market regime** | **216** | **+8.01%** | **1.123** | **5.79%** | **+4.70%** |
| prior-day relative strength | 218 | -4.90% | 0.924 | 9.04% | -7.81% |
| compression + volume | 73 | -10.19% | 0.596 | 10.46% | -11.21% |
| compression+volume+market | 37 | -5.51% | 0.589 | 5.76% | -6.05% |
| 1H breakout followthrough | 109 | -3.32% | 0.900 | 7.26% | -4.77% |

- Prior-day market regime gave BTC about +1,639.66 USDT
  realised and ETH about -37.54 USDT, so one instrument
  generated essentially all the improvement. The five-year
  net gain is +8.01% total, which is low annualised.
- Among its 216 trades, average net R +0.084; the earlier
  entry-year block (through 2023) yielded +626.2 USDT and
  later entry-year block (2024 and onward) +975.9 USDT,
  but both blocks had uneven individual calendar-year
  results. Entry-year grouping is NOT a genuine separate
  walk-forward portfolio.
- Most compression/volume combinations showed worse MAE
  and negative R. Additional filters do not imply good entry.

## BNBUSDT + SOLUSDT + XRPUSDT: 4.3-year second cohort

| Predeclared arm | Trades | Return | PF | MDD | +4bp/side cost-stress |
|---|---:|---:|---:|---:|---:|
| raw range_break | 516 | -13.26% | 0.908 | 19.65% | -19.10% |
| compression | 147 | -20.55% | 0.568 | 21.71% | -22.16% |
| volume_confirm | 322 | -17.62% | 0.800 | 22.91% | -20.85% |
| **market_regime** | **304** | **-1.20%** | **0.986** | **16.16%** | **-5.13%** |
| relative_strength | 293 | -14.72% | 0.824 | 19.19% | -17.78% |
| compression_volume | 77 | -16.25% | 0.395 | 16.95% | -17.08% |
| triple_gate | 40 | -9.44% | 0.380 | 10.59% | -9.92% |
| followthrough | 171 | -8.77% | 0.823 | 15.07% | -10.70% |

- The market-regime gate substantially decreased the losing
  raw breakouts, but remained negative and worsened with
  higher transaction fees. BNB +105.57, SOL +400.11,
  XRP -746.10 USDT (realised closed trades).
- The negative compression variants in BOTH cohorts are
  evidence AGAINST treating a volatility squeeze as a
  self-sufficient breakout advantage on these rules.
- DO NOT select BTC long-only after seeing it succeed
  and report it as generalizable OOS; this would directly
  reintroduce selection bias.

## Current decision

The most transferable hypothesis is *avoid directional
range breakouts against the prior-day BTC market's
long-term regime*, but even that is NOT profitable in
every instrument cohort. This is a risk-control heuristic,
not a validated buy/sell signal.

The US stock cohort is evaluated in the same run; when
its job completes, append its outputs and final decision.
No live integration. No raising risk, no real orders.

Limitations: all historical calendar years have been
previously exposed to extensive v1-v9 experiment
selection; no untouched calendar holdout, stock
survivorship bias, imprecise futures funding and
execution, 1H close-only MDD, historical candle path
ambiguity and missing margin/liquidation/slippage tails.
