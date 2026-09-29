# Wyckoff Track-B 15/25/60 Alt-Coin OOS v1 — Frozen

Frozen before any OOS result is inspected.

## Purpose
Validate the already-selected Track-B management on coins that were NOT used to choose the 15/25/60 split.

## OOS universe
- XRPUSDT
- ADAUSDT
- DOGEUSDT
- LINKUSDT

These symbols were not part of the BTC/ETH/BNB/SOL runner-allocation optimization.

## Strategy
Signal/setup logic:
- TRACK_B_V1_0_FROZEN unchanged.

Management:
- TP1: 15%
- TP2: 25%
- Runner: 60%
- TP1 hit -> remaining stop to break-even
- TP2 hit -> remaining stop to TP1
- Runner -> existing confirmed 3-bar 4H pivot trailing stop +/- 0.30 ATR

No signal/filter/target/stop/trigger parameter changes.

## Data / execution
- Binance USD-M perpetual
- evaluation: 2021-09-23T00:00:00Z through 2026-09-21T20:00:00Z
- 1D / 4H signal context
- 15m execution
- fee 4 bps + slippage 2 bps per fill
- conservative STOP-first same-bar ordering
- fixed reference capital $20,000
- fixed risk $400 per trade

## OOS pass criteria
Primary survival criteria, frozen before results:
1. combined net R > 0
2. combined profit factor > 1.30
3. at least 3 of 4 symbols have positive net R

Secondary diagnostics:
- max drawdown
- maximum losing streak
- win rate
- yearly stability
- long/short split
- per-symbol PF and R

No post-result tuning is allowed inside this OOS version.
