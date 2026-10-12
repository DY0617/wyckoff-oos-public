# Stacker v4 — 7-way initial BTC/ETH research results

Historical research executed 2026-10-12 on frozen branch.
Run: https://github.com/DY0617/wyckoff-oos-public/actions/runs/38221062119
These are **our own rules**, NOT AGOS proprietary performance.

BTCUSDT+ETHUSDT Binance USDT-M 1H, from 2021-09-28 through
2026-09-28 (exclusive), 20,000 USDT starting equity, 0.75% maximum
planned cycle loss (with stressed fee allowance), 70% cycle notional cap,
two simultaneous positions, historical funding approximate and
6bps fee/slippage per entry/exit side. Drawdown is 1H-close MTM.

| Ablation | Cycles | Completed rebuys | SL moves | Total return | PF | MTM MDD | Added 4bps/side return |
|---|---:|---:|---:|---:|---:|---:|---:|
| static | 207 | 0 | 0 | +0.67% | 1.026 | 4.35% | -0.85% |
| rotate_support (v3 comparator) | 178 | 61 | 61 | -2.71% | 0.896 | 8.31% | -4.07% |
| confirm_support (bounce then next open) | 180 | 24 | 24 | -1.57% | 0.934 | 7.10% | -2.92% |
| trend_support (completed 4H EMA20 slope) | 179 | 21 | 21 | -2.63% | 0.894 | 8.45% | -3.96% |
| protect_profit (tighten SL post 50% TP) | 205 | 44 | 166 | -1.14% | 0.956 | 4.77% | -2.76% |
| light_ladder (2 instead of 4 initial levels) | 178 | 61 | 61 | -3.01% | 0.894 | 7.50% | -4.48% |
| trail_runner (no rebuy; confirmed 4H EMA) | 202 | 0 | 563 | +0.57% | 1.023 | 4.34% | -0.91% |

Notes:
- More selective confirmed bounce cut actual rebuys from 61 to 24
  and loss from -2.71% to -1.57%; not a positive edge.
- Trailing a post-TP runner was near-flat and reduced drawdown,
  but static full exit had a slightly higher total return.
- ALL seven variants fail additional 4bp/side cost stress.
- Partial 2026 losses offset much of strong 2025 returns for
  static and trail-runner; this is not robust long-term growth.
- Never optimise these predefined thresholds on this known
  evaluation sample and call it out-of-sample.
- Event-time basis: confirmed 4H bars only; bounce close must
  precede confirmation rebuy at next 1H open; stop-first ambiguity,
  terminal liquidation, same initial planned risk/notional bounds.
- Caveats: selected two crypto symbols only; Binance hour OHLC
  ambiguity, estimated funding close-mark, omitted exchange
  liquidation/margin, and MDD excludes within-hour extremes.

**Crypto verdict: keep research only; not ready for live trading.**
