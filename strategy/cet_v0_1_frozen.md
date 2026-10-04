# CET v0.1 — Frozen Before Results

Compression -> Expansion Transition standalone strategy.

This is a clean break from horizontal S/R as the primary signal.

## State

On the completed 1H bar immediately before breakout:
- ATR14 / ATR50 <= 0.80
- ER20 <= 0.35

This defines low-volatility, low-directional-efficiency compression.

## Trigger

Current completed 1H candle:
- close breaks prior 20-bar high/low by >=0.05 ATR
- body >=0.80 ATR
- volume >=1.50x SMA20
- CLV >=0.75 for long / <=0.25 for short
- candle direction agrees with breakout

## Trade

- entry next 15m open, gap <=0.30 ATR
- stop beyond breakout candle opposite extreme +0.15 ATR
- initial risk 0.50–2.50 ATR
- TP1 1R, 30%; remainder stop to BE
- TP2 2.5R, remaining 70%
- max hold 120h
- 24h signal cooldown
- conservative 15m stop-first path
- standard fee/slippage model

Frozen before first result inspection.
