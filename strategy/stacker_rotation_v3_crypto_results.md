# Stacker v3 — completed 5-year BTC/ETH cyclic TP/rebuy outcomes

GitHub Actions run [38219308656](https://github.com/DY0617/wyckoff-oos-public/actions/runs/38219308656)
on 2026-10-12. **Historical research**, not actual AGOS performance
and not a live trading system. This is our independent bounded strategy.

Data: BTCUSDT/ETHUSDT USDT-M, 2021-09-28 through
2026-09-28 exclusive. Starting cash 20,000 USDT. Per-cycle bounded
0.75% gross risk INCLUDING stressed 10bp entry/exit fee estimate,
<=70% notional, max two cycles, historical funding settlement proxy,
regular cost 6bp per side; 1H close MTM MDD.

| Variant | Cycles | Completed rebuys | SL lowers | Return | PF | MTM MDD | +4bp/side return |
|---|---:|---:|---:|---:|---:|---:|---:|
| static structural S/R SL + EMA TP | 207 | 0 | 0 | **+0.67%** | 1.026 | 4.35% | -0.85% |
| rotate_fixed | 176 | 111 | 0 | -3.93% | 0.862 | 9.12% | -5.45% |
| rotate_lower (0.25 ATR) | 175 | 110 | 110 | -2.85% | 0.898 | 8.53% | -4.35% |
| rotate_support (new completed pivot) | 178 | 61 | 61 | -2.71% | 0.896 | 8.31% | -4.07% |

Annual realised USD PnL for `rotate_lower`: 2021 partial
-208.95, 2022 -263.94, 2023 -422.68, 2024 -426.23,
2025 +986.72, 2026 partial -234.32.

## Interpretation

- The rotation engine genuinely executed numerous completed cycles and
  permitted downward/higher SL movements subject to original frozen
  worst-loss ceiling. These were *not* phantom or hypothetical alerts.
- In this historical sample recycled stop-lowering reduces the damage
  relative to rebuys with fixed SL, but underperforms selling the full
  position at the original EMA target, even before 4bp/side stress.
- The number of first-to-final trade cycles differs because position
  holding time differs; comparing only win rate is inappropriate.
- `static` uses the SAME fee-inclusive prospective ladder sizing and
  causal portfolio engine as the rotation variants. It differs slightly
  from prior Stacker v2 research due to fees-reserved size and cycle state.
- Do **NOT** cherry-pick thresholds or claim 5-year performance is OOS.
- Causality: initial pivot and EMA are confirmed at the signal;
  new SL pivot used at rebuy must have 2 confirmed right-side 4H candles
  BEFORE the 1H rebuy open; new SL activates after the rebuy bar closes;
  existing stop has first priority on that bar.
- LIMITATIONS: Funding settlement approximate on the exit hour;
  stock survivorship and corporate-action biases, hourly-close MTM
  missing intrabar extremes, exchange margin/liquidation, book spreads,
  and market impact absent.
- **Research conclusion (crypto): REJECT as a production alternative.**
