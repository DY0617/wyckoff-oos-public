# Entry First v10 — FINAL three-cohort engineering and research review

Run dated 2026-10-12, all GitHub Actions jobs SUCCESS:
https://github.com/DY0617/wyckoff-oos-public/actions/runs/38237159212
13 standalone causal/portfolio invariant tests PASS.
The full 8-arm strategy code, independent from any proprietary AGOS
implementation, is on research/entry-v10-expansion. Prior to results
the hypotheses, markets, stop/TP sizing and fee stress were locked in
[entry_expansion_v10_frozen.md](entry_expansion_v10_frozen.md).
Two crypto cohorts documented separately in
[entry_expansion_v10_crypto_results.md](entry_expansion_v10_crypto_results.md).

This is **historical research, NOT actual account performance**.

## Historical setup and risk

Each cohort uses an independent 20,000 USD/USDT research account.
Same exact Entry First v8 portfolio engine for all v10 arms,
fixed +2R take profit, stop beyond previous 7 closed 1H swing
extreme by 0.2 ATR, 0.65..3.5 ATR initial stop distance,
max three positions, max 70% marked-equity notional per trade,
worst planned loss <=0.5% marked equity with stressed fee reserve,
no leverage multiplier, averaging or circular rebuys.
One-hour OHLC stop-first and actual-open gap fills, historical
funding rate proxy for USDT-M perpetual futures, fee/slippage
6bp EACH fill side or 10bp with predeclared cost stress.
MDD is at 1H CLOSE only, not worst intra-hour floating drawdown.

Different cohorts and DATES: BTC/ETH Sep 2021–Sep 2026;
BNB/SOL/XRP Jun 2022–Sep 2026;
29 selected US RTH shares/ETFs Sep 2021–Mar 2026.
These cohorts must NOT be combined into a single claimed CAGR.

## Summary: nominal simulated return across THREE markets

| Variant | BTC/ETH | BNB/SOL/XRP | US RTH stock | Robust sign across cohorts? |
|---|---:|---:|---:|---|
| 4H Donchian range-break close | -11.76% | -13.26% | -11.74% | All negative |
| prior 12x4H compression | -11.24% | -20.55% | **+13.87%** | No |
| 4H relative-volume confirmation | -10.31% | -17.62% | -5.03% | All negative |
| prior-complete-day market EMA200 regime | **+8.01%** | -1.20% | -12.28% | No |
| completed prior-day relative strength | -4.90% | -14.72% | **+12.48%** | No |
| compression + volume | -10.19% | -16.25% | +6.57% | No |
| compression + volume + market | -5.51% | -9.44% | +2.62% | No |
| one completed 1H followthrough | -3.32% | -8.77% | -3.07% | All negative |

All eight compared with exactly the same predeclared portfolio
engine and transaction cost assumptions.

## US stock cohort detailed

| Variant | Trades | Return | PF | 1H-close MTM MDD | +4bp EACH side stress |
|---|---:|---:|---:|---:|---:|
| raw_break | 523 | -11.74% | 0.921 | 19.22% | -19.80% |
| compression | 237 | **+13.87%** | **1.217** | **7.58%** | **+8.66%** |
| volume_confirm | 274 | -5.03% | 0.939 | 13.82% | -8.86% |
| market_regime | 439 | -12.28% | 0.902 | 19.71% | -19.31% |
| relative_strength | 448 | **+12.48%** | **1.093** | **7.81%** | **+3.50%** |
| compression_volume | 69 | +6.57% | 1.381 | 3.62% | +5.38% |
| triple_gate | 56 | +2.62% | 1.172 | 3.57% | +1.65% |
| followthrough | 337 | -3.07% | 0.968 | 14.47% | -8.97% |

**Selection / concentration warnings:**
- Stock `compression` made ~+2,773 US dollars gross-net
  realised over entire sample, of which **2023 alone ~+2,723**
  (near 98% of total!). It lost in 2022 (-445),
  2025 (-412) and early 2026 (-673). This is not smooth,
  evidence-backed compounding.
- Stock `relative_strength` made ~+2,495 total
  but a substantial +2,255 is attributed to partial 2021;
  it lost in 2022, 2025, 2026. The early+late
  split is a post-hoc diagnostic, NOT untouched OOS.
- Stock `compression_volume`: PF 1.381 on ONLY 69 trades;
  making only 69 observations in ~4.5 years is too thin
  to claim statistically robust transferable alpha.
- Stock research universe was selected from contemporary
  survivor names and cash equities are not the same as
  the intended stock futures execution; dividends,
  split treatment, margin and corporate-action data
  require independent ground truth.

## Crypto-specific findings

BTC+ETH:
- `market_regime` 216 cycles +8.01%, PF 1.123,
  MDD 5.79%, cost stress +4.70%.
- BTC accounted for +1,639.66 USDT while ETH
  contributed -37.54 USDT. Candidate's apparent success
  depends on a single asset; its 5-year annualised
  return is modest relative to buy-and-hold opportunity.
- `compression` 114 cycles -11.24%, `triple_gate`
  37 cycles -5.51%: multiple technical confirmations
  made entries less frequent but worse.

New crypto BNB+SOL+XRP:
- ALL eight lose money even before extra cost stress.
- Best nominal among evaluated `market_regime` still
  -1.20% net (PF 0.986) and -5.13% under higher costs.
- `compression` -20.55%, `triple_gate` -9.44%,
  `volume_confirm` -17.62% across that universe.

## Overall decision

**DO NOT promote v10 or merge into production.** Every new
price-action entry model failed to show portable profitability
across all three research cohorts. Its most credible lesson
is a MARKET-SPECIFIC economic mechanism worth further
study: trend-gated BTC directional breakouts, and compressed
stock consolidation breaks / relative strength. Choosing
the current best of these after observing results would be
post-selection and must NOT be called independent validation.

Also note that versions v1-v10 repeatedly searched the same
2021–2026 calendar periods; very substantial data snooping
now exists. Pre-register a fresh calendar period and new
symbols/venues with automatic exclusion/embargo, robust
split/dividend and survivorship-free stocks, real exchange
fees/slippage, futures funding and liquidation, and 1-minute
or tick-level event path validation to obtain honest evidence.
Benchmark against risk-equal cash/passive holdings as well as
other models.

No background tasks promised. Production Wyckoff tracks,
Telegram, Binance order routing and Supabase are UNCHANGED.
