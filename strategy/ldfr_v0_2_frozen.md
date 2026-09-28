# LDFR v0.2 — Frozen Before Test

This version changes exactly one structural assumption from v0.1.

## Single change vs v0.1

v0.1 required the qualifying FVG to exist on the same bar used as the displacement bar.

v0.2 allows the qualifying FVG to form on the displacement bar or within the next **2 completed 1H bars**.

Everything else remains unchanged:
- same 4H regime
- same 20-bar liquidity sweep
- same displacement thresholds
- same FVG minimum size (0.15 ATR)
- same 8-bar retest window, measured from the FVG bar
- same confirmation rule
- same entry timing
- same stop
- same TP1/TP2
- same fee/slippage assumptions
- same BTCUSDT/ETHUSDT 5Y test window
- same one-position-per-symbol rule

## Reason

v0.1 diagnostics showed 178 regime-aligned displacement events but only 12 same-bar FVGs across BTCUSDT and ETHUSDT. The purpose of v0.2 is to test whether separating displacement from immediate imbalance formation increases sample size without changing any threshold values.

No v0.2 result may be used to redefine v0.2 in place. Any additional change must be versioned v0.3+.
