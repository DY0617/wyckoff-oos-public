# Track B + HTF S/R Integration v1 — REJECTED

Date: 2026-10-04

## Question

Can the mechanized 4H/1D support-resistance zone engine from SR Reclaim v1 improve frozen Wyckoff Track B by filtering entries or validating Track B targets?

## Frozen components

- Track B signal/setup logic unchanged.
- 15/25/60 management used for evaluation.
- Fee: 4 bps/fill.
- Slippage: 2 bps/fill.
- Existing 15m conservative execution semantics unchanged.
- SR zones use only information confirmed before each trade entry.

SR zone definition:
- 4H + 1D pivot candle body-edge levels.
- ATR-clustered neutral zones.
- Minimum two distinct interactions.
- Confirmed-pivot/known-time discipline to prevent lookahead.

## Core-4 research universe

BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT.

Baseline:
- Trades: 132
- Win rate: 64.39%
- Net R: +29.27R
- Avg R: +0.222R
- PF: 1.608
- MDD on $20k reference: 13.95%
- Max losing streak: 3

### Structural SR variants

Backing zone:
- Rule: active HTF SR overlaps Entry-to-SL corridor.
- Present on 130/132 trades, so it has almost no discriminatory value.
- Net R +27.73R, PF 1.576. No improvement.

Clear to TP1:
- Rule: reject if an active HTF SR zone lies between Entry and Track-B TP1.
- Trades: 26 (19.7% retained)
- Win rate: 80.77%
- Net R: +9.30R
- Avg R: +0.358R
- PF: 2.786
- MDD: 5.12%
- Max losing streak: 3
- Looked promising in the research universe, so this was the only rule advanced to fresh symbol OOS.

Clear to TP2:
- Trades: 8
- Net R: +0.74R
- PF: 1.238
- Too restrictive and materially worse.

TP2 inside active SR zone:
- Trades: 120
- Net R: +24.16R
- PF: 1.561
- MDD: 15.52%
- Worse than baseline. Target-confluence validation did not improve Track B.

## Preselected alt-4 symbol OOS

Fresh symbol OOS universe:
- XRPUSDT
- ADAUSDT
- DOGEUSDT
- LINKUSDT

The only rule tested was the already-selected Core-4 rule:

> Reject a Track B trade when an already-confirmed active 4H/1D SR zone lies between Entry and Track-B TP1.

No threshold or parameter was changed after viewing OOS results.

### OOS baseline

- Trades: 116
- Win rate: 59.48%
- Net R: +5.25R
- Avg R: +0.045R
- PF: 1.109
- MDD: 16.66%
- Max losing streak: 4

### OOS with SR clear-to-TP1 filter

- Trades: 13 (11.2% retained)
- Win rate: 69.23%
- Net R: +0.28R
- Avg R: +0.022R
- PF: 1.069
- MDD: 5.84%
- Max losing streak: 2

The lower drawdown is primarily explained by removing 88.8% of trades. Expected trade quality did not improve: average R and profit factor both declined.

## Decision

REJECT the HTF SR filter as a Track B alpha filter.

Do not add the SR clear-to-TP1 rule to live/shadow Track B.
Do not change frozen Track B signal logic based on these results.

Also reject:
- generic Entry-to-SL SR backing as a useful discriminator;
- requiring Track-B TP2 to sit inside an HTF SR zone;
- clearing the whole path to TP2.

The SR zone engine may remain available for chart annotation, diagnostics, or explanatory context, but it has not demonstrated robust incremental alpha for Track B.

## Evidence files

- data/validation/track_b_sr_filter_ab_core4_v1.json
- data/validation/track_b_sr_clear_tp1_alt4_oos_v1.json
- data/validation/sr_reclaim_v1_crypto_5y.json
- data/validation/sr_reclaim_v1_1_unseen8_oos.json

## Change-control note

This rejected experiment does not modify TRACK_B_V1_0_FROZEN.
