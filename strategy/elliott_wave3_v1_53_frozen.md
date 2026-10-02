# Elliott Wave 3 v1 — 5-3 Structure Frozen Spec

Independent wave-only strategy. No Wyckoff / Track B filters.

## Structure
A larger Wave 1 must itself be a confirmed five-wave standard impulse:
- Long: L-H-L-H-L-H pivots; short is symmetric.
- Wave 2 does not retrace beyond Wave 1 origin.
- Wave 3 makes a new extreme beyond Wave 1.
- Wave 4 does not overlap Wave 1 price territory.
- Wave 5 makes a new extreme beyond Wave 3; truncations/diagonals excluded.
- Wave 3 is not the shortest of motive waves 1, 3, 5.

The larger Wave 2 must be a confirmed A-B-C zigzag:
- A moves against the impulse.
- B retraces 23.6%-88.6% of A without exceeding the impulse termination.
- C extends beyond A.
- C length is 61.8%-161.8% of A.
- Overall larger Wave 2 retraces 38.2%-78.6% of the five-wave impulse.
- The larger Wave 2 may not break the larger Wave 1 origin.
- Correction duration <= 2.5x impulse duration.

## Signal/execution
- ATR(14) realtime ZigZag pivot reversal = 1.50 ATR.
- Signal tested on 1H and 4H.
- Entry activates only after the C pivot is confirmed.
- Entry = breakout of the larger Wave 1 termination.
- Stop = C extreme +/- 0.15 ATR.
- TP1 = C +/- 1.0x larger Wave 1 length.
- TP2 = C +/- 1.618x larger Wave 1 length.
- 50% exits at TP1; remainder moves to breakeven and exits at TP2.
- Entry validity = 12 signal bars; max hold = 48 signal bars.
- Execution = 15m; conservative stop-first convention.
- Costs = 4 bp fee + 2 bp slippage per fill.

v1 is frozen before reading its development result. Any later tuning must be versioned separately.
