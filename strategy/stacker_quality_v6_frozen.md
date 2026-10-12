# Stacker v6 — 7 predeclared entry-quality and portfolio risk ablations

Frozen 2026-10-12 BEFORE v6 trading results; independent Stacker
research, NOT the proprietary AGOS algorithm. This is a NEW
mechanistic hypothesis, NOT tuning previous Stacker v5 retest thresholds.

## Evidence prompting change

- v4 initial S/R stop + EMA target: BTC/ETH five years +0.67%,
  PF 1.026; US selected stock universe four-plus years -3.17%.
- v5 independent child reentry BTC/ETH added 24 new trades and
  -501 USDT, child-only PF 0.55; higher-timeframe filter did
  not establish reproducible child edge. Therefore stop adding
  new trades after TP merely to pursue quantity.
- v3-v5 stock performance differs by year and regime. Need understand
  the PRE-ENTRY risk/reward quality and broad-market state.

## Same non-rotating parent mechanics for ALL seven arms

- Previous complete daily asset+SPY/BTC close above EMA200 for LONG,
  below EMA200 for crypto SHORT. Original Stacker 4H completed
  Bollinger(20, 2 sigma) outside-band cross. No future candles.
- First entry at next 1H actual OPEN; capped four-step adverse ladder
  at 0/1/2/3 ATR, nonmartingale frozen weights 1/1.25/1.5/1.75.
- STOP from 4H pivot confirmed with two completed bars to left
  and right; 0.25ATR buffer beyond pivot, constrained 3.5-8 ATR.
  TP nearest favorable EMA20 or EMA50 from the same completed 4H
  signal; 0.5-8 ATR distance. If no structure exists, no entry.
- All stages at worst stop INCLUDING stressed 10bp estimated
  transaction costs <=0.75% of then marked equity, notional <=70%
  marked equity per cycle, maximum two simultaneous positions.
  A stop gap can exceed this pre-estimated bound.
- Full exit at absolute frozen TP, no post-TP rebuy and no widening
  SL. Hard stop wins ambiguous 1H OHLC outcomes. 10-session stock
  and 14-calendar-day crypto maximum hold unchanged.
- Crypto historical funding settlement proxy with hourly-close
  notional, fees+slippage nominal 6bps each side; stress 10bps
  each side (additional 4bps/side).

## Seven arms — one dimension at a time

1. `control` — original Stacker v4 static baseline; identical event
   simulator plus identical fees, signals and risk model.
2. `daily_trend` — previous completed day's asset and benchmark
   EMA50 > EMA200 for LONG (reverse SHORT), plus asset EMA50 in
   trade direction vs previous fifth COMPLETE daily sample.
3. `vol_skip` — skip new cycles when latest CONFIRMED 4H
   ATR14/close > 80th percentile of the latest 80 completed
   4H ATR14/close observations; values frozen before 1H entry.
4. `reward_floor` — reject when frozen structural EMA target
   yields less than +0.65 initial-entry-to-hard-stop R.
   (It is an entry-geometry filter; it does not guarantee payoff.)
5. `vol_scale` — still enter the high-volatility regimes but
   halve every initial planned DCA fill, related fee budget and
   effective planned worst-stop budget. Do not change SL or TP.
6. `loss_cooldown` — after 3 consecutive losing FULL cycles
   across the market, skip all new entries for 72 subsequent
   chronological crypto 1H event bars or 35 RTH stock 1H
   event bars (~5 sessions). Never look ahead to know future losses.
7. `quality_combo` — PREDECLARED daily_trend + vol_skip +
   reward_floor together. No extra hand-tuned parameters or
   per-market cherry-picking. It is not selected after results.

## Validation and rejection policy

- Market 1: Binance USDT-M BTCUSDT and ETHUSDT, 2021-09-28 to
  2026-09-28 EXCLUSIVE, hour OHLCV, funding rate archives.
- Market 2: selected 29 US stock/ETF names and SPY benchmark,
  RTH 1H, 2021-09-28 to 2026-04-01 EXCLUSIVE.
- Same 20,000 initial USD/USDT simulated capital separately.
- Equal starting equity, exposure limits and stress testing;
  scale version reduces actual risk by design, no hidden leverage.
- Report actual cycles, net return, PF, hourly-close marked
  equity drawdown, average R, fees/funding, skip reasons,
  accepted/rejected signals, cooldowns, years and each symbol.
- Compare ALL seven without discarding losing variants. No success
  unless independent edge survives stress and multiple disjoint
  annual/symbol partitions; 2021-26 historical dates ARE KNOWN
  from v1-v5 and cannot be advertised as an untouched OOS set.
- Before ANY live use, require new symbol markets, walk-forward
  embargoed test data, independent market regime, proper stock
  split/dividend and futures funding/basis models.
- Within-hour drawdown, exact fills, liquidation, margin, orderbook,
  market impact, tax are NOT modelled. Only research branch changed.
