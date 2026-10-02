# Elliott Wave 3 v3 — B-wave Breakout Frozen Spec

This version keeps the entire v1 Elliott structure unchanged and changes only entry timing.

## Macro structure
- Exact v1 frozen 5-wave standard impulse + ABC zigzag.
- Signal timeframes: 1H and 4H.
- ATR(14) realtime ZigZag reversal = 1.50 ATR.
- No Wyckoff, Track B, EMA, RSI, volume, or trend filters.

## Entry
After the C pivot is confirmed:
- Long: entry stop = B-wave high.
- Short: entry stop = B-wave low.
- The order is valid for 12 signal bars.
- If the C extreme is hit before entry, cancel the setup.

## Stop / targets
- SL = C extreme +/- 0.15 ATR.
- TP1 = C +/- 1.0x the macro Wave 1 impulse length.
- TP2 = C +/- 1.618x the macro Wave 1 impulse length.
- Exit 50% at TP1.
- Move remaining stop to breakeven after TP1.
- Exit remaining 50% at TP2.
- Max hold = 48 signal bars.
- Execution = 15m, conservative stop-first intrabar convention.
- Costs = 4 bp fee + 2 bp slippage per fill.

## Frozen validation groups
- DEV: BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT
- OOS1: XRPUSDT, ADAUSDT, DOGEUSDT, LINKUSDT
- OOS2: LTCUSDT, BCHUSDT, ETCUSDT, DOTUSDT

No parameter changes are allowed between groups.
