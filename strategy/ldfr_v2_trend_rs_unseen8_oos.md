# LDFR v2.0 — Unseen 8-Symbol OOS

Exact frozen v2 rules. No threshold or logic changes after seeing the design-universe result.

Target symbols:
- LTCUSDT
- BCHUSDT
- ETCUSDT
- TRXUSDT
- XLMUSDT
- DOTUSDT
- FILUSDT
- UNIUSDT

BTCUSDT is fetched only as the daily market / 30-day relative-strength benchmark and is **not traded** in this OOS run.

Selection, 4H alignment, structural liquidity, MSS, FVG, entry, stop, management, intrabar convention, and transaction costs are unchanged from `ldfr_v2_trend_rs_frozen.md`.

Purpose: falsification / cross-symbol generalization test. The design-universe v2 result was borderline rather than a clean pass, so this OOS run is used to decide whether the architecture deserves further work, not to select favorable symbols.
