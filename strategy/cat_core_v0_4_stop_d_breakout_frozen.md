# CAT-Core v0.4 Stop D — Breakout Support

Frozen before seeing results.

Everything else remains identical to CAT-Core v0.4:
- LONG-only signal
- BTC/SPY market filter
- next daily/session open entry
- 3 ATR14 trailing stop from highest completed close
- no fixed TP
- 4 bps fee + 2 bps slippage per fill

Initial stop D:
- breakout support = signal-day prior 20-day high
- initial stop = breakout support - 0.5 * signal-day ATR14
- no clamp in this test
- if stop >= actual next-open entry, signal is skipped as invalid
- position sizing remains risk-normalized by actual entry-to-stop distance

Purpose:
Test whether the broken-resistance / new-support level provides a meaningful invalidation point with better risk efficiency than 2ATR or 10-day-low stops.
