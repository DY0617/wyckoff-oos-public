# CAT-Core v0.4 Entry A/B/C Test

Frozen before seeing results. Signal logic is identical to CAT-Core v0.4 ER20.

A_NEXT_OPEN
- current behavior
- enter at the next completed-day/session open after the signal

B_RETEST
- breakout level = prior 20-day high from the signal day
- valid for the next 3 daily/session bars
- fill only if low <= breakout level <= high
- fill price = breakout level
- otherwise expire

C_HYBRID
- breakout level = prior 20-day high
- max acceptable gap = breakout + 0.50 * signal-day ATR14
- valid for next 3 daily/session bars
- if a candidate bar opens above max acceptable gap: cancel signal immediately
- if it opens between breakout and max gap: enter at that open
- if it opens below breakout but trades up through breakout: stop-entry at breakout
- otherwise continue until expiry

All modes
- LONG-only CAT-Core v0.4 signal and market filter unchanged
- 2 ATR14 initial stop based on signal-day ATR
- 3 ATR14 trailing stop from best completed close
- no fixed TP
- 4 bps fee + 2 bps slippage per fill
- one position per symbol
- conservative same-bar ambiguity: if a retest/reclaim entry bar also touches the initial stop, count the stop
- no parameter sweep
