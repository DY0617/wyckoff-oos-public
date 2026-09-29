# Wyckoff Track-B Runner 60% Check v1 — Frozen

Frozen before results are inspected.

## Scope
TRACK_B_V1_0_FROZEN signal logic unchanged.
Entry, SL, TP1, TP2, costs, trigger logic, and 4H pivot runner unchanged.

## Modes
Baseline:
- 20% TP1
- 30% TP2
- 50% runner

60% runner candidates:
- 15% TP1 / 25% TP2 / 60% runner
- 10% TP1 / 30% TP2 / 60% runner

## Management
- TP1 hit -> remaining stop moves to break-even
- TP2 hit -> remaining stop moves to TP1
- runner exits via existing confirmed 3-bar 4H pivot trailing stop +/- 0.30 ATR

## Data / execution
- BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT
- Binance USD-M perpetual
- 2021-09-23T00:00:00Z through 2026-09-21T20:00:00Z
- 1D/4H signal context, 15m execution
- 4 bps fee + 2 bps slippage per fill
- conservative STOP-first same-bar ordering

## Metrics
Compare total R, avg R, PF, MDD, max losing streak, win rate,
yearly/symbol/direction breakdown, hold time.

No signal or filter parameter changes.
