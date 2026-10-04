# SR Sweep Failure v4 — Frozen Baseline Before Results

Standalone horizontal S/R strategy based on failed breakout / liquidity sweep behavior.

- HTF zones: confirmed 4H+1D body-edge clusters, minimum 2 interactions.
- Signal timeframe: 1H.
- Long: previous close above zone; current low sweeps below far edge by 0.10–0.80 ATR; candle closes fully above zone; bullish close; CLV >=0.70; lower wick/body >=1.0.
- Short: exact mirror; CLV <=0.30.
- Entry: next 15m open, max gap 0.25 ATR.
- SL: beyond sweep extreme +0.15 ATR.
- Initial risk: 0.35–2.00 ATR.
- TP1: 1R, 50%; remainder -> breakeven.
- TP2: 2R, remaining 50%.
- Maximum hold: 48h.
- Same zone cooldown: 48h.
- Conservative 15m stop-first execution and existing fee/slippage model.

Frozen before first result inspection.
