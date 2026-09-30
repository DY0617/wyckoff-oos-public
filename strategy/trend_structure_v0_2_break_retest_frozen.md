# Trend Structure v0.2 — Breakout + Retest Research

Frozen before v0.2 results are inspected.

## Motivation
Trend Structure v0.1 showed:
- Pivot-line pullback and regression-channel pullback were negative.
- Breakout + retest was positive in both crypto and stock pilots, but sample sizes were small.

v0.2 isolates only the breakout + retest family and expands the sample.

## Shared logic
1. Build a mechanical trendline from the latest 3 confirmed pivots.
2. Require a close through the projected line.
3. Require breakout participation by volume.
4. Do not enter immediately.
5. Wait for a later retest of the broken line.
6. Enter only after the retest bar closes back on the breakout side.
7. Use the same structural stop and 20/20/60 exit family from v0.1.

No pullback-only or regression-channel entries are allowed.

## Crypto universe
BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT, ADAUSDT, DOGEUSDT, LINKUSDT.

- 4H directional regime
- 1H trendline signal
- 15m execution
- evaluation: 2021-09-01 through 2026-09-01 UTC where data exists
- completed bars only

## Stock universe
Existing stock53 RTH universe.

- previous completed RTH daily bar = directional regime
- RTH 1H = trendline signal
- RTH 15m = execution
- evaluation target: 2006-04-01 through 2026-04-01
- warmup begins 2005-09-01
- symbols naturally enter the sample only after listing/data availability

## Frozen baseline
- pivot radius: 3
- pivot lookback: 120 1H bars
- minimum pivot span: 12 bars
- line RMSE <= 0.35 ATR
- normalized slope: 0.01 to 0.25 ATR per 1H bar
- breakout lookback for retest: 8 completed 1H bars
- breakout close buffer: 0.10 ATR
- breakout volume: >= 1.20 x volume SMA20
- retest distance: 0.35 ATR
- confirmation RSI: LONG >= 50 / SHORT <= 50
- entry buffer: 0.05 ATR
- accepted planned risk: 0.70 to 2.80 ATR
- pending entry expiry: 4 hours

## Exit
- TP1: 20% at +1.5R
- after TP1: stop to entry
- TP2: 20% at +2.5R
- remaining 60% Runner
- runner uses completed signal-timeframe EMA20 and confirmed pivot structure
- conservative adverse-first same-bar handling
- costs: 4 bps fee + 2 bps slippage per fill-equivalent

## One-axis robustness sweep
All variants change one axis only relative to baseline.

### Breakout volume axis
- vol_100: 1.00 x SMA20
- baseline: 1.20 x SMA20
- vol_140: 1.40 x SMA20

### Retest distance axis
- retest_025: 0.25 ATR
- baseline: 0.35 ATR
- retest_050: 0.50 ATR

### Breakout close-buffer axis
- break_005: 0.05 ATR
- baseline: 0.10 ATR
- break_015: 0.15 ATR

### Momentum confirmation axis
- rsi_loose: LONG >= 48 / SHORT <= 52
- baseline: LONG >= 50 / SHORT <= 50
- rsi_strict: LONG >= 52 / SHORT <= 48

## Evaluation rule
Do not select a setting from highest return alone.
Look for a plateau across neighboring values using:
- trade count
- avg R
- PF
- max DD R
- losing streak
- long/short consistency
- symbol breadth
- year consistency

The baseline remains the reference until the robustness sweep is reviewed.
