# Elliott Wave 3 v3 — Stock30 RTH 1H vs 1D Cross-Asset OOS

Exact frozen crypto v3 logic transferred to US stocks. No stock-specific tuning.

## Common rules
- confirmed Elliott 5-wave impulse + ABC correction
- ATR(14) ZigZag reversal = 1.50 ATR
- entry = B-wave extreme breakout after C confirmation
- SL = C extreme +/- 0.15 ATR
- TP1 = C +/- 1.0 x macro Wave 1 impulse
- TP2 = C +/- 1.618 x macro Wave 1 impulse
- 50% exit TP1, remainder to breakeven, 50% TP2
- costs = 4 bp fee + 2 bp slippage per fill
- 15m RTH execution
- common split adjustment

## Timeframe A: RTH 1H
- six complete 60m bars per full session: 09:30-15:30 ET
- final 15:30-16:00 ET remains execution-only
- entry validity = 12 1H signal bars
- max hold = 48 1H signal bars

## Timeframe B: RTH 1D
- one full regular-session bar 09:30-16:00 ET
- entry validity = 12 daily signal bars
- max hold = 48 daily signal bars

Universe and evaluation window are identical to the previous Stock30 4H cross-asset OOS.
