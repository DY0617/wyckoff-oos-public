# Entry First v8 — frozen causal entry pattern research

2026-10-12: frozen BEFORE examining v8 return/PF/drawdown results.
This code is our INDEPENDENT research, not an AGOS algorithm
and not merged with any existing live trading/alerts.

## Research question

Stacker v1-v7 repeatedly changed TP/SL and position averaging without
establishing a high-quality entry edge. The last v7 historical study
improved on some crypto subuniverses by skipping extreme 4H signals,
but US stocks remained unprofitable, and prior "new retest entries"
underperformed. Instead isolate market STRUCTURE entries and objectively
compare adverse/favorable excursions at fixed entry risk.

Five **predeclared entry signal mechanisms** evaluated independently:

1. `sweep` — on a fully CLOSED 4H candle, price briefly breaks a
   previously confirmed swing pivot (2 left, 2 right) by >=0.10
   completed 4H ATR and then CLOSES back in the range by >=0.05 ATR.
   Directional candle CLV >=0.55. Enter next available 1H OPEN,
   not at the swept extremum. A previous confirmed pivot only may
   be used; scan latest 60 eligible closed 4H bars.
2. `choch` — 1H CLOSE breaks the most recently confirmed 1H
   pivot high (LONG) or low (SHORT), by >=0.08 1H ATR, whereas
   previous 1H CLOSE is still on the other side. Directional CLV
   >=0.60. Enter next 1H OPEN. Requires 2 fully closed 1H
   candles to each side of pivot before considering it confirmed.
3. `breakout_retest` — detect the above 1H pivot breakout but
   don't enter; track up to 16 subsequent completed 1H candles.
   A LATER 1H candle touches former pivot from the correct
   side (within 0.15 ATR) and closes favorably at least 0.10 ATR
   beyond that pivot, directional CLV >=0.60. Enter NEXT 1H OPEN.
   Never count the breakout bar as its own retest.
4. `sweep_choch` — must see completed 4H liquidity sweep and
   then the same-direction 1H structural breakout within 36
   subsequent 1H bars. Enter following 1H OPEN.
5. `sweep_choch_retest` — combine all three steps in sequence:
   4H sweep, subsequent 1H structural break (within 36 bars),
   then a later 1H confirmed retest (within 16 bars).
   Enter next 1H OPEN. Do not fabricate trades if there are
   no 3-stage opportunities; empty samples must be reported.

Crypto may LONG/SHORT, US stock RTH LONG only. No spread-type or
indicator-combination filters; these versions measure the RAW
information content of price structure under common exits.

## Frozen exit & portfolio accounting, ALL variants equal

- Enter at ACTUAL next 1H bar OPEN, never same signal candle. If
  OPEN has chased >0.75 completed 1H ATR from signal CLOSE, SKIP.
- Initial STOP: for sweep / combo, beyond the observed SWEPT
  4H extreme (if also CHoCH/retest, the more distant extreme);
  for pure 1H CHoCH/retest, beyond minimum of last 8 completed
  1H lows / maximum highs. Add 0.20 completed 1H ATR buffer.
- Stop distance must be between 0.65 and 3.50 completed 1H ATR
  or the opportunity is skipped. No covert stop widening.
- Take profit: FULL EXIT at +2.00 initial R for all modes,
  with stop and TP FROZEN at first entry. No DCA, no partial TP,
  no break-even moving stop, and no cyclical reentry.
- Time stop: 120 1H candles for 24/7 crypto (~5 days), 35
  observed RTH 1H stock candles (~5 sessions).
- STOP wins on any 1H candle where it and TP both touch;
  a gap beyond the existing stop fills at ACTUAL gap OPEN.
  Entry candle may hit hard stop, but TP cannot fill until
  a subsequent candle (conservative 1H sequencing).
- Simulated notional per trade <=70% of marked equity; ex-ante
  initial STOP risk INCLUDING stressed 10bps estimated entry+exit
  fees <=0.50% of current marked equity. At most three
  simultaneous trades, one per symbol. No unbounded leverage.
- Estimate 4bps commission +2bps slippage each side
  (6bps/side) and additional 4bps/side cost stress;
  crypto historical funding rates via hourly-close proxy.
- Account equity marked to market HOURLY including fees and
  funding and outstanding floating PnL.
- MAE and MFE in units of initial stop R captured from hourly
  high/low; the stop priority assumption forbids crediting
  favorable wick to trade in a stopping candle. These are
  CANDLE-BASED excursions, not intrabar market replay.
  A gap stop MAE uses observed OPEN exit, not undiscounted low.
- Main evaluation metrics: trade count, average / median MAE,
  average / median MFE, percentage MAE <= 0.5R, percentage
  full +2R target hits, average actual net trade R,
  PF, return, 1H-close marked max DD, fee stress, symbols/years,
  valid signals skipped for stop geometry or chase gap.

## Fixed universe / research integrity

A. BTCUSDT + ETHUSDT historical 1H Binance USDT-M,
   2021-09-28..2026-09-28 exclusive.
B. BNBUSDT + SOLUSDT + XRPUSDT new futures-symbol research cohort,
   2022-06-01..2026-09-28 exclusive, BTC as reference only.
C. 29 selected US stock/ETF names in RTH, SPY is a reference,
   2021-09-28..2026-04-01 exclusive.
For all, raw data sourced via existing repo adapters; 520-day
indicator warmup; same research reference initial cash 20,000
units, NOT one pooled USD+USDT account.

**No untouched calendar OOS**: dates have been examined many times
in prior strategies. There is a large multiple-comparisons risk.
BNB/SOL/XRP were newly introduced to the Stacker research series
in v7, so even they are now previously studied instruments.
No claims of future profitability or production readiness.

Known limitations: stock survivorship bias and cash-vs-futures
difference, corporate actions, approximate funding/mark price,
one-hour OHLC intrabar path, omitted order book/margin/liquidation,
gap/slippage loss beyond intended limits, taxes and exchange outages.

**Acceptance criterion**: favor entry modes with genuinely lower
MAE at comparable enough trade counts, positive net average R
and PF after added fee stress ACROSS instruments and years. Do
not claim a model is better merely because it has fewer trades,
high win rate or no valid signals. No post-results retuning
of the predefined thresholds on these known periods.
