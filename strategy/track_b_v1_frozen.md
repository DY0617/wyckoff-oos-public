# Track B v1.0 — FROZEN

Frozen on: 2026-09-26
Validation baseline commit: `0c08a69518c3b0fd9fc6169b425540a5c23555b3`

## Status

Track B is frozen for forward/live-shadow operation. Do not tune parameters or trade-management rules in response to short-term performance.

Any intentional change to a signal, entry, stop, target, filter, trigger window, or runner rule creates a new strategy version (v2+) and must be validated on data that was not used to choose the change.

## Frozen Track B parameters

```json
{
  "range_max_atr": 12.0,
  "range_er_max": 0.80,
  "penetration_min": 0.25,
  "penetration_max": 2.50,
  "test_overlap_atr": 1.50,
  "test_spread_max": 1.25,
  "test_volume_max": 1.05,
  "entry_buffer_atr": 0.05,
  "stop_buffer_atr": 0.25,
  "rr_long_min": 1.10,
  "rr_long_max": 2.00,
  "rr_short_min": 1.10,
  "rr_short_max": 1.80,
  "target_distance_atr": 3.50,
  "return30_min": -0.05,
  "ema_gap_atr_max": 2.0,
  "trigger_window": 9
}
```

## Frozen management

- Track A is disabled for the validated Track B results.
- Signal timeframes: 1D context + 4H setup.
- Entry/SL/target levels are rounded to market tick size.
- TP1: liquidity/Fibonacci-confluence target; take 30%.
- After TP1: remaining stop -> break-even.
- TP2: frozen opposite range boundary; take another 30%.
- After TP2: remaining stop -> TP1.
- Runner: final 40%, trailing on confirmed 3-bar 4H pivots with 0.30 ATR buffer.
- Execution-path convention in backtests: STOP first on same 15m bar.
- One symbol, one position at a time.

## Risk layer (operational, not alpha tuning)

- Reference 1R: $400.
- Portfolio open-risk cap: 5R.
- Risk controls may be tightened for safety without creating a new alpha version.
- Increasing risk limits does not change strategy logic but requires a separate risk decision.

## Validation evidence at freeze

The frozen rules were tested without changing Track B parameters across multiple markets and regimes, including:

- Crypto 5-year validation.
- US equities 5-year validation.
- China A-share out-of-sample validation.
- US index ETF long-horizon test.
- Current US 30-symbol long-horizon test, 2000–2025.
- DJIA-2000 frozen-universe long-horizon stress test, 2000–2025.

The long-horizon US validation files are:
- `data/validation/us_current30_track_b_25y.json`
- `data/validation/us_dow2000_track_b_25y.json`
- `data/validation/us_index_track_b_25y.json`

## Change-control rule

Allowed without changing strategy version:
- alert formatting / Telegram UI
- logging and audit fields
- data-integrity fixes
- exchange/API compatibility fixes
- monitoring/reconciliation
- stricter operational risk controls
- bug fixes that restore the documented frozen behavior

Requires a new strategy version and fresh validation:
- any Track B numeric parameter change
- adding/removing a signal filter
- changing entry or stop construction
- changing TP1/TP2 selection
- changing 30/30/40 fractions
- changing BE/TP1 stop transitions
- changing runner/pivot logic
- changing same-bar execution assumptions for performance claims

If a methodology bug is found, correct it transparently and rerun the frozen strategy. Do not tune parameters to recover the old result.
