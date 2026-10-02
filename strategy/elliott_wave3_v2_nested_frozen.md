# Elliott Wave 3 v2 — Nested 1-2 Entry Frozen Spec

This version keeps the v1 macro Elliott structure unchanged and changes only entry timing.

## Macro structure
- Exact v1 frozen 5-wave standard impulse + ABC zigzag rules.
- Signal structure timeframes: 1H and 4H.
- Realtime ATR(14) ZigZag reversal: 1.50 ATR.
- No Wyckoff, Track B, EMA, RSI, volume, or trend filter.

## Nested entry
After macro C is confirmed:
- For 1H macro structure, search a 15m nested Wave 1-2.
- For 4H macro structure, search a 1H nested Wave 1-2.
- Nested Wave 1 must be at least 1.00 ATR.
- Nested Wave 2 retracement: 23.6%-78.6%.
- Nested Wave 2 cannot break nested Wave 1 origin.
- Nested Wave 2 duration <= 2.5x nested Wave 1 duration.
- Nested setup must confirm within 48 lower-timeframe bars of macro C confirmation.
- If price breaks the macro C extreme before nested setup confirmation, invalidate the macro setup.

## Order / exits
- Entry: nested Wave 1 extreme breakout, only after nested Wave 2 pivot is confirmed.
- Entry validity: 12 lower-timeframe bars.
- Stop: nested Wave 2 extreme +/- 0.15 ATR.
- TP1: nested Wave 2 +/- 1.0x nested Wave 1 length.
- TP2: nested Wave 2 +/- 1.618x nested Wave 1 length.
- 50% exit at TP1, move remainder to breakeven, exit remainder at TP2.
- Max hold: 48 lower-timeframe bars.
- Execution: 15m bars, conservative stop-first intrabar convention.
- Costs: 4 bp fee + 2 bp slippage per fill.

## Validation groups frozen before results
- DEV: BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT
- OOS1: XRPUSDT, ADAUSDT, DOGEUSDT, LINKUSDT
- OOS2: LTCUSDT, BCHUSDT, ETCUSDT, DOTUSDT

No parameter changes are allowed between DEV/OOS groups.
