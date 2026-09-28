# CAT-Core v0.4 — ER20 Trend-Efficiency Filter

Frozen before first v0.4 result.

Single change from CAT-Core v0.3:
- require symbol ER20 >= 0.30 on the completed signal day.

ER20:
abs(close[t] - close[t-20]) / sum(abs(close[i] - close[i-1]), 20 daily steps)

Everything else is unchanged:
- LONG only
- symbol: at least 2 of 20D/60D/120D returns positive
- symbol close > EMA200
- market benchmark: BTC/SPY at least 2 of 20D/60D/120D returns positive
- signal close > prior 20-day high
- next session/day open entry
- 2 ATR14 initial stop
- 3 ATR14 trailing stop from highest completed close
- no fixed TP
- no time stop
- one position per symbol
- 4 bps fee + 2 bps slippage per fill

No ER threshold search is performed. 0.30 is frozen before testing.
