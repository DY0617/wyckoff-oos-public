# SR Reaction v6 / SR Engine v2 — Frozen Before Results

This version changes the level detector before changing the trade pattern.

## SR Engine v2

- No ATR ZigZag.
- 4H and 1D candle BODY fractals, radius 2.
- A level is usable only after the right-hand fractal bars have closed.
- At known time, the already-observed reaction away from the body level must be >=0.75 ATR.
- Levels cluster within 0.40 ATR.
- Same market turn across timeframes is de-duplicated; stronger observation survives.
- Event score = observed reaction strength capped at 2 ATR; 1D events receive 2x weight.
- Active zone requires >=2 distinct events and score >=3.
- Zone age max 540 days.
- Zone half-width starts at 0.20 ATR and caps at 0.60 ATR.

## v6 trade

- 1H signal.
- Approach zone from outside.
- Penetrate to zone center.
- Close back completely outside near edge.
- Bullish/ bearish reversal candle and CLV >=0.60 / <=0.40.
- Entry next 15m open.
- SL beyond signal extreme / far zone edge +0.15 ATR.
- Risk 0.30–2.50 ATR.
- TP1 1R, 50%, then BE.
- TP2 2R, remaining 50%.
- Max hold 48h.
- Zone cooldown 48h.
- Existing costs and conservative stop-first execution.

Frozen before first result inspection.
