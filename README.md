# Public OOS Backtest Bundle

Temporary public GitHub Actions bundle for running the frozen Track B robustness test on a market not used in the original crypto / US-equity / precious-metals development set.

## What is included

- `scripts/backtest_wyckoff_5y.py` — shared backtest engine.
- `scripts/wyckoff_status.py` — indicator and Track B setup logic.
- `scripts/wyckoff_structural_state.py` — import dependency used by the shared engine. Track A is disabled in this OOS run.
- `scripts/backtest_china_a_oos_hf_5y.py` — China A-share OOS runner.
- `.github/workflows/china-a-oos-hf-5y.yml` — manual GitHub Actions workflow.

No Supabase, Telegram, Binance, exchange API keys, service-role credentials, or live execution code is included.

## OOS design

- Market: Shanghai / Shenzhen China A-share equities.
- Source: `neigezhu/china-a-share-1min-ohlcv` on Hugging Face.
- Warmup: 2020-01-01 through 2020-12-31.
- Evaluation: 2021-01-01 through 2025-12-31.
- Track A: disabled.
- Track B: frozen production defaults, no China-specific tuning.
- Management: TP1 30% -> BE, TP2 30% -> TP1, remaining 40% confirmed 4H pivot runner.
- Same 15m candle ambiguity: STOP first.
- One symbol: one open position.
- Costs: fee 4 bps/fill + slippage 2 bps/fill.
- Fixed reference risk: $400 = 1R.

## Important caveats

The source prices are unadjusted. The OOS runner applies the same common-factor overnight corporate-action cleanup style used in the earlier US-stock robustness test. This is robustness research, not a claim that China cash-equity short selling or fills would be executable under these assumptions.

## Run

1. Put the contents of this directory at the root of a **public** GitHub repository.
2. Open **Actions**.
3. Select **China A-Share Untouched OOS 5Y**.
4. Choose **Run workflow**.
5. When complete, the workflow commits `data/validation/china_a_track_b_oos_5y.json`.

Do not add live-trading secrets to the public repository.
