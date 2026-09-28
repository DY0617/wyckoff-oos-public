# CAT-Core v0.4 Stop E — Breakout Support with 2–3 ATR Clamp

Frozen before seeing results.

Everything else remains identical to CAT-Core v0.4:
- LONG-only signal
- BTC/SPY market filter
- next daily/session open entry
- 3 ATR14 trailing stop from highest completed close
- no fixed TP
- 4 bps fee + 2 bps slippage per fill

Initial stop E:
1. breakout support = signal-day prior 20-day high
2. raw structural stop = breakout support - 0.5 * signal-day ATR14
3. raw stop distance = actual next-open entry - raw structural stop
4. final stop distance is clamped to [2.0 ATR14, 3.0 ATR14]
5. final initial stop = entry - clamped distance

Purpose:
Preserve structural meaning while preventing the ~1.2 ATR over-tight stop seen in Stop D and preventing very wide structural stops.
No threshold sweep is performed.
