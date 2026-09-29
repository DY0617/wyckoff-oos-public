# CAT-Core v0.4 — Trailing ATR Sweep

Frozen before results.

Purpose: isolate the trailing-stop distance after fixing the initial stop at 2.5 ATR14.

Common rules:
- LONG only
- symbol momentum: at least 2 of 20D/60D/120D returns > 0
- close > EMA200
- ER20 >= 0.30
- signal close > highest high of prior 20 completed daily bars
- market filter: BTC/SPY at least 2 of 20D/60D/120D returns > 0
- entry = next daily/session open
- initial stop = entry - 2.5 * signal-day ATR14
- no fixed TP
- no time stop
- one position per symbol
- 4 bps fee + 2 bps slippage per fill

Only variable:
- Trail 2.5: highest completed close since entry - 2.5 * current ATR14
- Trail 3.0: highest completed close since entry - 3.0 * current ATR14
- Trail 3.5: highest completed close since entry - 3.5 * current ATR14

Evaluation:
- same 8-crypto and 30-stock pipelines used by CAT-Core v0.4
- compare trades, win rate, total R, average R, profit factor, max drawdown R,
  maximum losing streak, and average holding bars
- no portfolio caps or correlation filter in this diagnostic sweep
