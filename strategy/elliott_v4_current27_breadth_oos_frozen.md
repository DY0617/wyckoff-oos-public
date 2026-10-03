# Elliott v4 Current27 25Y — Breadth Candidate Validation

The candidate filter was discovered post-hoc on the separate DJIA2000 frozen universe and is frozen before this run.

Common strategy:
- US RTH 1H
- LONG only
- exact Elliott v3 5-wave + ABC + B-wave breakout rules
- same costs, stop, TP1/TP2, entry validity and max hold

Variants:
1. BASELINE
2. MID_BREADTH_60_75: prior completed RTH day breadth of the current27 individual-stock universe is >=60% and <75%, with at least 10 names having valid 200-day state.

Universe: 27 individual US large-cap equities from the existing Current30 dataset; SPY, QQQ and IWM are excluded.

This is a cross-universe filter validation but remains survivorship-biased because the current large-cap roster is projected backward.
