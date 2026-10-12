# Entry First v10 — frozen NEW expansion/participation strategy

Frozen on 2026-10-12 before examining v10 backtest outcomes.
This research is **independently developed**, not AGOS proprietary logic.
No Binance API, Supabase, Telegram, Track B/E, production pipelines, or
user live funds touched.

## Distinct economic thesis

Versions v1-v9 failed to find an after-fee, portable **reversal** edge:
buying an oversold Bollinger break, pivot sweep, a supposedly good
retest, or deeper limit-order dip often selected persistent adverse
moves. Do not optimize those loss-making signals again on the same
period. V10 instead tests the OPPOSITE: **directional price discovery
after a completed multi-session range breakout**, ideally preceded
by volatility compression and confirmed by abnormal traded volume.

Directional break requires fully completed 4H candle CLOSE above
the maximum HIGH of its preceding **20 closed 4H candles**
(+0.10 of the breakout 4H ATR14), for LONG. Symmetrically,
SHORT requires CLOSE below minimum prior 20 lows (-0.10 ATR14).
Breakout candle's directional CLV must be >= 0.65.
All five crypto USDT-M symbols may long and short; selected
US stocks/ETFs are LONG-ONLY. Trade at **next available 1H OPEN**,
not inside the 4H breakout candle.

## Eight preregistered, comparable hypotheses

1. `range_break`: raw directional 20×4H Donchian close breakout.
2. `compression`: require prior completed 4H candle's
   trailing **12×4H range width / ATR14** <= 35th percentile of
   the prior 60 fully completed reference 12-bar ranges.
   Never use current 4H breakout range in its own contraction test.
3. `volume_confirm`: require breakout's per-hour-normalized 4H
   total volume >= 1.30× mean of prior 20 completed 4H volumes.
   Stock 4H buckets may differ in 1H count, hence normalize
   volume by aggregated count; never use incomplete current 1H.
4. `market_regime`: previous completed DAILY BTC/SPY close
   above its EMA200 for long (below for short).
5. `relative_strength`: completed prior-day traded asset
   20-day return exceeds the prior-day BTC/SPY return for
   long (reverse short); for BTC benchmark itself require
   sign*BTC 20-day return > 0.
6. `compression_volume`: predeclared 2 and 3 combined.
7. `triple_gate`: predeclared 2,3,4 combined.
8. `followthrough`: after the qualifying 4H breakout, wait
   until the immediately following **complete 1H** candle
   also CLOSES at least +0.10 1H ATR beyond the original
   channel boundary (reverse short) with directional CLV >=0.55.
   Enter ONLY at the next 1H OPEN after THAT confirmation.
   The 1H followthrough CLOSE may not be used as fill price.

The only variant differences are SIGNALS. Not risk budget,
stop size, exit policy, fee assumption, or sample universe.

## Shared risk and order simulation (reuses v8 engine)

For each accepted signal the last seven fully CLOSED 1H
candles define an opposing swing extreme, LONG low/SHORT high.
Set STOP 0.20 of most recent completed 1H ATR beyond that level,
and only admit if expected entry-to-stop lies within 0.65..3.5
times that 1H ATR. Price must not chase >0.75 ATR favorable
relative to the fully completed signal candle's CLOSE.
Targets: fixed **2.00R from actual next 1H OPEN**, no moving
stop, partial TP, martingale, DCA, mean-reversion averaging,
unbounded re-entry or increasing leverage.

Maximum ex-ante **0.5% marked portfolio equity stop risk
INCLUDING estimated stressed 10bps entry + exit costs**, max
70% marked equity notional per trade, max 3 active positions.
Crypto holds no more than 120 1H candles (~5 days); stocks
35 RTH 1H candles (~5 sessions). Existing positions GAP through
a stop at true OPEN, stop-first when both stop and target
touch same OHLC candle. Entry bar cannot hit TP (conservative).
One-hour close marked-to-market DD, adverse/favorable excursion
MAE/MFE proxies, historical crypto funding rate charged with
1H closing notional proxy. Nominal 6bps cost per fill SIDE
(4bps fee + 2bps slippage), +4bps/SIDE extra stress.

## Research cohorts and chronologic diagnostics

- Development comparison: BTCUSDT + ETHUSDT perpetual USDT-M,
  2021-09-28 to 2026-09-28 exclusive.
- Cross-instrument comparison: BNBUSDT + SOLUSDT + XRPUSDT,
  same USDT-M archive, 2022-06-01 to 2026-09-28 exclusive,
  BTC benchmark only (not a traded holdout asset).
- US selected 29 equities/ETFs RTH one-hour OHLC, historical
  2021-09-28 to 2026-04-01 exclusive, SPY benchmark.
- 520-day indicator preparation warmup. All three accounts
  use independent initial simulated 20,000 USD/USDT equity.
- Also report per-entry calendar year, instrument, trades,
  loss concentration, average R, MAE/MFE, TP2 hit fraction,
  cost-stress net return. A chronological early/late
  split is a *diagnostic*, NOT untouched future-date OOS
  because 2021-26 periods and some symbols were already
  viewed in v1-v9.
- Reject apparent winners if thin sample, return sensitive
  to +4bps/side, one symbol/year drives outcome, or new
  cross-market universe fails. Do NOT change frozen
  parameters based on this batch and claim validation.

## Critical limitations and future validation requirements

Source OHLCV is 1H (stock aggregated from HF 1m historical data).
No true intrahour tick order path, limit queue, market impact,
variable spreads, slippage shocks, exchange outages, futures
margin / mark liquidation or accurate intrahour DD. Stock
universe was selected from later/current survivors and has
corporate-action, cash-vs-futures and survivorship biases.
Crypto monthly Binance funding is an estimate on 1H close marks,
and past backtest exposures create material multiple-testing
risk. Even profitable rows are exploratory and NOT a promise
of future earnings.

No existing live strategy or notification is changed.
