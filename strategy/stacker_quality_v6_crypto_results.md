# Stacker v6 — entry-quality study: BTC/ETH complete results

2026-10-12 GitHub Actions run
https://github.com/DY0617/wyckoff-oos-public/actions/runs/38223756081

Original research strategy, NOT AGOS proprietary algorithm or verified
real account performance. Existing live systems unaffected.

Period 2021-09-28 through 2026-09-28 exclusive; BTCUSDT and ETHUSDT
USDT-M futures; starting 20,000 USDT; max two parallel cycles,
<=0.75% initially planned risk per cycle INCLUDING 10bp fee reserve,
<=70% of account equity gross notional per cycle. Nominal 6bp
per entry/exit side incl estimated slippage, historical funding proxy.
Max drawdown uses 1H candle-CLOSE marked equity, not worst intrabar.

| Variant | Trades | Return | PF | 1H-close MTM MDD | +4bp/side stress return |
|---|---:|---:|---:|---:|---:|
| control/static EMA TP | 207 | +0.67% | 1.026 | 4.35% | -0.85% |
| stronger prior-daily EMA trend | 157 | -5.43% | 0.754 | 6.30% | -6.53% |
| exclude high-volatility 4H ATR/close top quintile | 175 | **+3.32%** | **1.155** | **3.46%** | **+1.93%** |
| target >=0.65 original stop R | 3 | -1.24% | 0.160 | 1.94% | -1.30% |
| half-size high-vol cycles | 207 (32 reduced) | +1.99% | 1.084 | 3.79% | +0.54% |
| skip after 3 consecutive losses | 207 | +0.67% | 1.026 | 4.35% | -0.85% |
| daily+vol+target geometry filters | 2 | -1.47% | 0.0 | 1.94% | -1.52% |

### Vol-skip interpretation

- Its two underlyings both were positive in the selected historical
  period: BTC approx +530.58 USDT, ETH +132.48 USDT.
- Whole sample annual realised PnL assigned to entry year:
  2021 partial +168.20, 2022 +117.70, 2023 -212.23,
  2024 +206.23, 2025 +797.97, 2026 partial -414.80 USDT.
- It removed 35 high-volatility candidate entries; total accepted
  cycles decreased from 207 to 175. Cost stress +4bp per side
  remained positive (+1.93%) in the model.
- It does not establish attractive CAGR or consistency:
  +3.32% over five years is economically weak and 2026 is negative.
- `vol_scale` halved sizes of 32 cycles and reduced simulated
  risk, but was less profitable than skipping high-volatility entries.

### Other experiments
- Reward-to-stop minimum 0.65R is overly restrictive at this
  frozen level (3 trades); combined filter had only 2.
  Do NOT lower the threshold post-hoc and claim untouched OOS.
- `loss_cooldown` never triggered (zero 3-loss streak).
- Stronger EMA trend alone worsened PnL; it may miss legitimate
  oversold mean-reversion entries.
- All reported returns are research portfolio model outputs;
  2021-2026 windows had been explored in prior strategy tests.
  Cross-sample confirmation with stock, genuinely new future
  market data, gap simulation, execution fees, stock survivorship
  and funding/liquidation models is mandatory before live use.

**Decision on BTC/ETH:** mark volatility-skipping as a research
candidate ONLY. All other variants either lose money, offer
very small net profit or almost no trade sample.
