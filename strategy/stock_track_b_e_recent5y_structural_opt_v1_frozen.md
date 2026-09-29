# Stock Track B-E Recent-5Y Structural Parameter Optimization v1 — Frozen

Frozen before structural-optimization results are inspected.

## Goal
Test the previously frozen Track-B structural numeric parameters on the current stock strategy, using the exact recent five-year window:
- 2021-04-01 through 2026-04-01

This creates a research candidate only. The production frozen Track B remains unchanged unless a later independent validation passes.

## Fixed components
To isolate structural parameters:
- stock universe: current 53-symbol research universe
- LONG only
- stock overlay fixed at current baseline:
  - SPY regime >= 2/3
  - relative strength lookback = 20 sessions
  - stock ret20 >= SPY ret20
  - breadth >= 50%
- management fixed at 15/25/60
- TP1 -> BE
- TP2 -> TP1
- confirmed RTH 4H pivot runner +/- 0.30 ATR
- fee 4 bps/fill + slippage 2 bps/fill
- fixed reference risk $400

## Stage 1 — one-axis sensitivity screening
Baseline is the current frozen Track-B structural configuration.

For every parameter below, test one lower and one higher value while every other structural parameter stays at baseline.

| parameter | low | baseline | high |
|---|---:|---:|---:|
| range_max_atr | 8.0 | 12.0 | 16.0 |
| range_er_max | 0.60 | 0.80 | 0.95 |
| penetration_min | 0.15 | 0.25 | 0.40 |
| penetration_max | 1.75 | 2.50 | 3.25 |
| test_overlap_atr | 1.00 | 1.50 | 2.00 |
| test_spread_max | 1.00 | 1.25 | 1.50 |
| test_volume_max | 0.85 | 1.05 | 1.25 |
| entry_buffer_atr | 0.00 | 0.05 | 0.10 |
| stop_buffer_atr | 0.15 | 0.25 | 0.40 |
| rr_long_min | 0.90 | 1.10 | 1.30 |
| rr_long_max | 1.75 | 2.00 | 2.50 |
| target_distance_atr | 2.50 | 3.50 | 5.00 |
| return30_min | -0.10 | -0.05 | 0.00 |
| ema_gap_atr_max | 1.50 | 2.00 | 3.00 |
| trigger_window | 6 | 9 | 12 |

Total Stage-1 configurations = 31 (baseline + 30 one-axis variants).

The SHORT RR parameters remain frozen because stock Track B-E v1 is LONG-only.

## Splits
- early: 2021-04-01 to 2023-10-01
- late: 2023-10-01 to 2026-04-01
- full: all five years

## Stage-1 survival
A configuration is viable only if:
- full trades >= 40
- early net R > 0
- late net R > 0
- early PF >= 1.20
- late PF >= 1.20
- max DD <= 10R
- max consecutive losses <= 7

## Stage-1 influence selection
For each parameter, select the better of its low/high variants only when it:
1. survives, and
2. improves the robustness score versus baseline, and
3. does not make either early or late net R negative.

Rank parameters by robustness-score improvement.
At most the top 5 influential axes advance to Stage 2.

## Stage 2 — interaction check
For each selected axis, use two states only:
- baseline
- Stage-1 preferred value

Evaluate the complete binary factorial:
- maximum 2^5 = 32 configurations.

No new values may be invented after Stage 1.

## Robustness score
score =
  0.30 * full avg R
+ 0.15 * min(early avg R, late avg R)
+ 0.15 * full PF
+ 0.15 * min(early PF, late PF)
+ 0.10 * log(1 + full trades)
- 0.10 * max DD R
- 0.05 * max losing streak
- instability penalty

instability penalty =
  0.10 * abs(early avg R - late avg R)
+ 0.05 * yearly avg-R dispersion

## Final selection rule
Do not choose solely by the maximum score.
Prefer a Stage-2 candidate only if:
- it survives all constraints,
- it improves on baseline in score,
- adjacent/one-toggle Stage-2 neighbors are mostly viable,
- performance is not concentrated entirely in only one half of the sample.

If no structural candidate shows a broad, stable improvement, keep the frozen baseline.

## Important limitation
This is optimization on the same recent five-year sample. Any selected structural candidate requires validation on untouched long-horizon / alternate-universe data before replacing the frozen strategy.
