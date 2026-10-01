# EasyChart public-concept synthesis v0.1

This experiment converts recurring public concepts from the EasyChart/쉽알남 channel ecosystem into objective, backtestable rules.

## Source concepts mapped to rules

- Liquidity / fakeout / trap -> Track A liquidity sweep and reclaim.
- Order block / FVG -> FVG first-retest entry; order-block overlap is diagnostic only.
- Trendline / channel -> objective 80-hour regression-channel alignment or outer-band fakeout quality.
- Breakout / Turtle-style continuation -> Track B Donchian-style breakout.
- S/R Flip -> breakout-level retest that closes back on the breakout side.
- Moving average / top-down analysis -> daily EMA trend plus completed weekly/monthly regime context.
- Risk/reward / stop / position sizing -> structural stop, fixed-R exits, no target stretching except when completed higher-TF context is aligned.
- Clean-chart / S-grade setup idea -> quality score is separated from raw signal generation.
- Chart patterns (cup-and-handle, diamond, Adam-and-Eve) are intentionally not traded in v0.1 because objective definitions are much more fragile; test later as standalone diagnostics.

## Track A — Liquidity Fakeout + FVG

1. Daily regime: LONG when daily close > EMA50 and EMA20 > EMA50; SHORT inverse.
2. 1H liquidity sweep of the previous 20 bars, then close back inside.
3. Displacement within the next 1–3 hours:
   - body >= 0.80 ATR
   - close through the sweep candle extreme
   - directional CLV >= 0.70
4. Classic 3-candle FVG >= 0.10 ATR.
5. First FVG midpoint retest within 8 hours.
6. Stop beyond sweep extreme + 0.15 ATR.
7. 2R target normally; 3R when completed weekly price vs EMA20 and completed monthly price vs EMA4 both align.
8. Quality diagnostics:
   - higher-TF alignment
   - regression-channel outer-band fakeout
   - displacement volume expansion

## Track B — Breakout + S/R Flip

1. Same daily trend regime as Track A.
2. 1H close beyond prior 20-hour extreme by >= 0.10 ATR.
3. Breakout candle:
   - body >= 0.65 ATR
   - directional CLV >= 0.75
   - volume >= 1.10 x 20-hour average
4. Within 8 hours, price retests the breakout level and closes back on the breakout side.
5. Entry at next 15m open after the completed retest hour.
6. Structural stop beyond retest swing / breakout level with ATR buffer.
7. Risk must be 0.40–3.50 ATR.
8. 2R normally; 3R under completed weekly+monthly alignment.
9. Regression-channel slope is a separate quality/filter test.

## Validation

- Binance USDT-M 15m data.
- BTC, ETH, BNB, SOL, XRP, ADA, DOGE, LINK.
- Evaluation: 2021-09-01 through 2026-09-01.
- Train/holdout split: 2025-01-01.
- Costs: 6 bps per side.
- Same-symbol overlapping positions suppressed.
- Report overall/train/holdout/year/symbol/track/leave-one-symbol-out metrics.

This is an objective derivative of publicly observable concepts, not a claim to reproduce any creator's proprietary or discretionary method exactly.
