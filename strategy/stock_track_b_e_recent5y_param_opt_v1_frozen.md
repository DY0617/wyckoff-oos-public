# Stock Track B-E Recent-5Y Parameter Optimization v1 — Frozen Search Space

Frozen before optimization results are inspected.

## Evaluation window
2021-04-01 through 2026-04-01.

## Base strategy held fixed
Track-B structural Wyckoff rules remain unchanged.
Reason: this experiment optimizes only the stock-specific overlay and management.
Changing structural Track-B parameters at the same time would create a very high-dimensional search and materially increase overfit risk.

## Universe
E53 stock universe used by the validated 5Y stock study.

## Search dimensions

### SPY regime votes
- 2 of 3
- 3 of 3

Votes are:
- SPY close > EMA50
- SPY EMA20 > EMA50
- SPY lookback return > 0

### Relative-strength lookback
- 10 sessions
- 20 sessions
- 30 sessions
- 40 sessions

Require stock return over the selected lookback >= SPY return over the same lookback.

### Breadth threshold
- 40%
- 50%
- 60%

Breadth = share of available E53 universe above EMA50 on the prior completed RTH daily bar.

### Management
- 30/30/40
- 20/30/50
- 15/25/60
- 10/30/60

Common stop-management rules:
- TP1 -> remaining stop to BE
- TP2 -> remaining stop to TP1
- Runner -> existing confirmed RTH 4H pivot trailing stop +/- 0.30 ATR

Total grid: 2 * 4 * 3 * 4 = 96 combinations.

## Validation splits
Full 5Y:
- 2021-04-01 to 2026-04-01

Early:
- 2021-04-01 to 2023-10-01

Late:
- 2023-10-01 to 2026-04-01

Calendar robustness:
- per-year stats for 2021 partial, 2022, 2023, 2024, 2025, 2026 partial

## Eligibility constraints
Reject combinations with:
- fewer than 40 full-period trades
- PF < 1.20 in either early or late split
- net R <= 0 in either early or late split
- maximum losing streak > 7
- full-period max DD > 10R

## Ranking score
Among surviving combinations:
score =
  0.35 * full-period avg_R
+ 0.20 * min(early_avg_R, late_avg_R)
+ 0.15 * min(early_PF, late_PF)
+ 0.10 * full-period PF
- 0.10 * full-period max_DD_R
- 0.10 * instability_penalty

instability_penalty is based on dispersion of yearly avg_R and large gaps between early and late performance.

The score is a research ranking device only.
Final selection should prefer a parameter plateau / neighborhood rather than the single numerical maximum.

## Baseline reference
Current frozen stock strategy:
- SPY votes >= 2/3
- RS lookback = 20
- breadth >= 50%
- management = 15/25/60

No post-result changes to this v1 grid are allowed.
