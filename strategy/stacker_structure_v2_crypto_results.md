# Stacker v2: BTC / ETH structural exits — frozen research outcome

Evaluation on 2026-10-12, run:
https://github.com/DY0617/wyckoff-oos-public/actions/runs/38217483473

Independent AGOS-inspired strategy, NOT AGOS proprietary model.
Initial 20,000 USDT; BTCUSDT/ETHUSDT USDT-M futures,
2021-09-28 to 2026-09-28 exclusive, Binance Vision historical
1H, completed 4H structures, 0.75% total planned cycle risk,
two concurrent cycles, gross notional cap 70% per cycle, Binance
historical funding approximate, 6 bps per fill/side.

| Exit mode | Trades | Win rate | Net return | PF | Marked 1H-close MDD | Extra 4bps/side return |
|---|---:|---:|---:|---:|---:|---:|
| baseline fixed ATR + prior-day EMA200 regime | 507 | 91.52% | -8.84% | 0.724 | 10.51% | -11.40% |
| swing S/R SL + EMA20/50 TP | 207 | 82.61% | +0.34% | 1.012 | 4.78% | -1.29% |
| swing S/R SL + opposing S/R TP | 197 | 77.66% | -2.89% | 0.909 | 10.27% | -4.52% |
| pivot / EMA-envelope SL + nearest structure TP | 355 | 81.97% | -0.82% | 0.983 | 8.79% | -3.71% |

For S/R SL + EMA TP, realised cycle USD PnL by entry year:
2021 partial +184.81, 2022 -141.69, 2023 -176.25,
2024 +37.97, 2025 +740.74, 2026 partial -577.52.

Observations:
- Selecting structurally well-located exits can reduce the
  drawdown in THIS sample, but also skips signals; not a pure
  randomised apples-to-apples comparison of exit placement.
- +0.34% aggregate over 5 years, PF ~1.012, turns to a loss
  under small additional transaction costs; statistically and
  economically weak. Do not present this as a validated edge.
- EMA wins in 2025 but weak in most other years, notably 2026.
- Direct opposing structural S/R and mixed stops/targets do
  not improve risk-adjusted profitability enough.
- The code also fixes old baseline portfolio lookahead:
  reserve same-hour entries BEFORE applying that hour's OHLC
  to old positions. Consequently baseline may differ modestly
  from older v1 report even under otherwise frozen settings.
- Known limitations: only 1H-close mark-to-market drawdown;
  futures liquidation/margin and precise intrahour fills
  unmodelled; funding approximate using close; selected stock
  universe survivorship; parameter selection and a single
  historical evaluation period do not constitute unseen OOS.

**Research verdict (crypto): NOT LIVE READY.** Keep the rejected
and near-flat variants archived; do not use real orders without
independent validation.
