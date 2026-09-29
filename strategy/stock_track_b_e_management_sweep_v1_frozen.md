# Stock Track-B E Management Sweep v1 — Frozen

Frozen before management-sweep results are inspected.

## Stock signal/filter
Base signal:
- existing frozen Track-B exact-touch signal logic
- US regular trading hours (RTH) structure / entry
- LONG only

Pre-entry stock filter E:
1. SPY bull regime is true on the prior completed RTH daily bar:
   - at least 2 of 3:
     - SPY close > EMA50
     - SPY EMA20 > EMA50
     - SPY 20-session return > 0
2. Stock 20-session return >= SPY 20-session return
3. Breadth >= 50%:
   - at least half of available 53-symbol universe closes above EMA50

No filter threshold search in this experiment.

## Management modes
A. 30/30/40
- TP1 30% -> stop to BE
- TP2 30% -> stop to TP1
- 40% confirmed RTH 4H pivot runner

B. 20/30/50
- TP1 20% -> stop to BE
- TP2 30% -> stop to TP1
- 50% same pivot runner

C. 15/25/60
- TP1 15% -> stop to BE
- TP2 25% -> stop to TP1
- 60% same pivot runner

Entry, SL, TP1, TP2, runner stop path, signal selection and filters are identical across modes.

## Evaluation
- current 53-stock research universe
- 2006-04-01 through 2026-04-01
- historical US RTH minute data already used by the 20Y Track-B validation
- fee 4 bps + slippage 2 bps per fill
- fixed $400 risk/trade
- conservative existing execution semantics

## Metrics
- trades, net R, avg R, PF
- MDD in R and fixed-$20k reference
- maximum losing streak
- win rate
- yearly stability
- 4-year shard stability

Important: this universe has survivorship/post-selection bias because today's stock universe is projected backward. Management selection must later be checked on a separate universe/time sample.
