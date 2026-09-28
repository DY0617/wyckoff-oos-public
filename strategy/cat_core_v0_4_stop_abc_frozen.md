# CAT-Core v0.4 Stop A/B/C Test

Frozen before seeing results. Entry remains the current CAT default: next daily/session open after a valid signal.

## Common signal / entry / exit management
- CAT-Core v0.4 ER20 LONG-only signal unchanged
- BTC/SPY market momentum filter unchanged
- entry = next daily/session open
- trailing stop after entry = highest completed close - 3 ATR14
- no fixed TP
- 4 bps fee + 2 bps slippage per fill
- one position per symbol

## Stop A — ATR baseline
- initial stop = entry - 2.0 * signal-day ATR14

## Stop B — 10-day structural low
- support = lowest low of the last 10 completed bars, including signal day
- initial stop = support - 0.5 * signal-day ATR14
- no clamp

## Stop C — confirmed swing low
- find the most recent confirmed 2-left / 2-right pivot low within the last 20 completed bars
- a pivot at j is valid only if low[j] is strictly below lows at j-2, j-1, j+1, j+2
- j+2 must be <= signal bar index, so no lookahead is used
- raw stop = pivot low - 0.5 * signal-day ATR14
- convert to stop distance from actual next-open entry
- clamp distance to [1.2 ATR14, 2.5 ATR14]
- if no confirmed pivot exists in the last 20 completed bars, skip that signal in mode C

No threshold sweep is performed.
