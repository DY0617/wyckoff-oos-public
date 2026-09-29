# CAT-Core v0.4 — Initial ATR Stop Sweep

Frozen before results.

Purpose: isolate the initial-stop distance while leaving CAT-Core v0.4 unchanged.

Common rules:
- LONG only
- symbol momentum: at least 2 of 20D/60D/120D returns > 0
- close > EMA200
- ER20 >= 0.30
- signal close > highest high of prior 20 completed daily bars
- market filter: BTC/SPY at least 2 of 20D/60D/120D returns > 0
- entry = next daily/session open
- trailing stop = highest completed close since entry - 3 ATR14
- no fixed TP
- no time stop
- one position per symbol
- 4 bps fee + 2 bps slippage per fill

Only variable:
- ATR 1.5: initial stop = entry - 1.5 * signal-day ATR14
- ATR 2.0: initial stop = entry - 2.0 * signal-day ATR14
- ATR 2.5: initial stop = entry - 2.5 * signal-day ATR14
- ATR 3.0: initial stop = entry - 3.0 * signal-day ATR14

Evaluation:
- same 8-crypto and 30-stock data pipelines already used by CAT-Core v0.4
- compare trades, win rate, total R, average R, profit factor, max drawdown in R, maximum losing streak
- no portfolio risk/correlation cap in this sensitivity file; those remain a separate realism layer
