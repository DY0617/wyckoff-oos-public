# SR Flip v2 — Frozen Baseline Before Results

Purpose: replace SR Reclaim v1's direct-bounce/reclaim logic with a true support/resistance role-flip state machine.

## Core idea

4H/1D HTF zone -> strong 1H breakout -> first 1H retest from the new side -> confirmed hold -> next-15m-open entry.

The zone is neutral. A resistance zone may become support after an upside break; a support zone may become resistance after a downside break.

## Frozen baseline

- Zones: existing SR v1 confirmed 4H + 1D body-edge pivot clusters.
- Minimum zone interactions: 2.
- Signal timeframe: 1H.
- Regime: 4H EMA20/EMA50 alignment and close on EMA20 trend side.
- Breakout: close >= 0.10 ATR beyond zone; candle body >= 0.60 ATR; CLV >=0.70 long / <=0.30 short.
- Retest window: 1 to 12 completed 1H bars after breakout.
- Retest proximity: within 0.25 ATR of near zone edge.
- Retest failure: close more than 0.20 ATR through far edge.
- Retest hold: close back beyond new-side edge, CLV >=0.55 long / <=0.45 short.
- Entry: next 15m open after completed retest candle.
- Maximum entry gap: 0.25 ATR.
- SL: beyond retest extreme or far zone edge plus 0.15 ATR.
- Allowed initial risk: 0.40 to 2.50 ATR.
- TP1: 1.0R, 50%; remaining stop -> breakeven.
- TP2: 2.5R, remaining 50%.
- Maximum hold: 72h.
- Zone signal cooldown: 48h.
- Fees/slippage and stop-first execution match the existing crypto research engine.

No parameter was selected from SR Flip v2 results before this file was frozen.
