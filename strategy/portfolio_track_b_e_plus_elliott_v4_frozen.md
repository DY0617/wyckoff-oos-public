# Portfolio Test — Stock Track B-E v1.0 + Elliott v4

Frozen inputs:
- Stock Track B-E v1.0 production candidate: LONG + E filter + 15/25/60 management.
- Elliott v4: US RTH 1H LONG, frozen 5-wave + ABC + B-wave breakout.
- Same DJIA2000 frozen universe and 2000-01 through 2026-01 period.
- Same 1R reference = $400 on $20,000 capital.

Comparisons:
1. Track B-E standalone at 1R/trade.
2. Elliott v4 standalone at 1R/trade.
3. Raw combined, each strategy 1R/trade.
4. Equal-strategy risk normalization: 0.5R Track B-E and 0.5R Elliott per trade.
5. Raw combined with maximum five simultaneously open initial-R positions, first-come; exact entry-time ties prioritize Track B-E.

Diagnostics:
- monthly and annual realized-R correlation, with inactive months/years set to zero
- maximum concurrent positions
- Elliott overlap with any Track B position and same-symbol Track B position
- full 2000-2025 and descriptive 2014+ slices

No portfolio weights are optimized from results.
