# LDFR v1.0 — Unseen 8-Symbol OOS

The v1.0 rules are frozen exactly as defined in `ldfr_v1_structural_frozen.md`.

These symbols were not used when designing the v1 structural redesign:
- LTCUSDT
- BCHUSDT
- ETCUSDT
- TRXUSDT
- XLMUSDT
- DOTUSDT
- FILUSDT
- UNIUSDT

No strategy threshold, timeframe, entry rule, stop rule, target rule, or management rule is changed for this run.

The only data-loader difference is that missing months *before a contract first appears in Binance Vision* are skipped; once data begins, a missing completed month is treated as an error.

Purpose: test cross-symbol generalization before any further rule changes.
