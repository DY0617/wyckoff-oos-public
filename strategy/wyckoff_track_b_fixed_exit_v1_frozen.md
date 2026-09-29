# Wyckoff Track-B Fixed Exit v1 — Frozen

Frozen before results are inspected.

## Scope
Reuse the existing TRACK_B_V1_0_FROZEN signal/setup logic unchanged.
Only position management is changed to make Entry / SL / TP prices fully fixed before entry.

## Setup logic — unchanged
- 4H local trading range from Track B
- Spring / UTAD penetration of frozen range
- reclaim
- low-spread / low-volume Test
- existing Track-B filters unchanged:
  penetration_min 0.25
  test_spread_max 1.25
  test_volume_max 1.05
  rr_long 1.10–2.00
  rr_short 1.10–1.80
  range_max_atr 12
  range_er_max 0.80
  test_overlap_atr 1.50
  entry_buffer_atr 0.05
  stop_buffer_atr 0.25
  target_distance_atr 3.50
  return30_min -0.05
  ema_gap_atr_max 2.0
  trigger_window_4h 9

## Prices fixed at setup
LONG
- Entry = Test high + 0.05 * Test ATR
- SL = Spring extreme low - 0.25 * Test ATR
- TP1 = existing Track-B pre-existing liquidity/Fibonacci-confluence target
- TP2 = frozen opposite range resistance

SHORT = exact inverse.

No level changes after entry.

## Exit modes to compare
A. FIXED_50_50
- 50% at TP1
- 50% at TP2
- initial SL remains fixed
- NO break-even move
- NO trailing
- NO runner

B. FIXED_TP2
- 100% at TP2
- initial SL remains fixed
- NO partial exit
- NO break-even move
- NO trailing
- NO runner

Reference C. Existing frozen Track B
- 30% TP1 -> remaining stop to BE
- 30% TP2 -> remaining stop to TP1
- 40% 4H confirmed-pivot runner

## Execution / data
- BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT
- Binance USD-M perpetual
- exact same 5Y evaluation window as existing Track-B Futures validation:
  2021-09-23T00:00:00Z through 2026-09-21T20:00:00Z
- 1D/4H signals, 15m execution
- fee 4 bps + slippage 2 bps per fill
- same-bar ordering remains conservative: STOP before TP

## Evaluation
Compare:
- trades
- win rate
- net R
- average R
- profit factor
- max drawdown
- max consecutive losses
- TP1 / TP2 hit behavior
- long / short and symbol breakdown
- average holding duration if available

No signal/filter parameter may be changed based on these results.
