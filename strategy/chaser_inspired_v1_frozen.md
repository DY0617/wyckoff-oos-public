# Chaser-inspired v1 — frozen independent trend-continuation hypothesis

Frozen 2026-10-12 BEFORE outcomes. This is not AGOS proprietary Chaser code.
AGOS https://agos.me/auto-trading lists a "Chaser" bot but does not disclose
its exact decision rules; a breakout/continuation interpretation is OUR
hypothesis, NOT a verified description of AGOS's implementation.

**Do not deploy.** Research branch only. Existing Track B, CAT, ARM, Stacker,
Supabase and Telegram remain unchanged.

## Three predeclared arms (same execution engine, exit and portfolio risk)
A `breakout`: Price continuation without market filter.
B `trend`: same breakout, must align with yesterday's benchmark and symbol
daily EMA trends and a **completed** 4H local trend.
C `trend_compression`: B plus a short 1H range compression and high-participation
expansion requirement. Do not change thresholds after seeing v1 results.

## Frozen signal
- 1H completed candle closes beyond prior 20 completed 1H highs
  (LONG) or lows (crypto SHORT) by at least 0.05 * signal ATR14.
- Directional CLV >= 0.65.
- A supports stock LONG, crypto LONG/SHORT; B,C same sides.
- Higher-timeframe for B and C:
  * prior COMPLETED daily SPY/BTC close > EMA200 (LONG) or < EMA200 SHORT;
  * prior completed asset daily close > EMA50 > EMA200 (LONG), inverted SHORT;
  * latest *completed* 4H asset close > EMA20 > EMA50 (LONG), inverted SHORT.
- Extra for C: range of previous 10 1H candles <= 5 * signal ATR14;
  breakout candle range >= 1 * ATR14, body/range >=0.50,
  volume >=1.20 * SMA(previous 20 1H volumes).
- Next 1H open entry only, never enter on the signal bar itself.
- Reject an entry if next open has already moved unfavorably in chase
  direction by more than 0.75 * signal ATR14 beyond signal close.
  Gaps in the other direction are allowed if entry and stop remain valid.

## Exits and portfolio / realism
- STOP fixed at 2.0 * signal ATR14 below actual entry long, above short.
- TP1 +1.5R 50%, then stop moves to break-even **at bar close**, effective
  next bar only. TP2 +3.0R on remaining 50%.
- Time exit: 120 completed 1H crypto candles, 35 completed 1H RTH stocks.
- Exact conservative same-1H OHLC: adverse stop FIRST, even with TP touch.
- Existing-position stop gap exits at real bar OPEN, not pre-entry bar open.
- Entry size risks <=0.5% of then-current marked equity, also full
  notional <=75% of equity; max 3 simultaneous trades, one per symbol.
- Chronological multi-symbol simulator: admits new trades at the hour open
  BEFORE resolving that hour's high/low exits; no later-event freeing slots.
- Cash ledger includes actual partial exits, entry/exit costs, settled funding.
- Costs: fee 4bps + slippage 2bps **per fill/side**;
  stress additional 4bps/side. Binance historical funding rate on
  BTCUSDT/ETHUSDT positions using 1H close approximate notional.
- Mark-to-market equity sampled at each 1H close; full trade ledger and
  year/symbol breakdown; max DD, PF, avg R, longest loss streak.
- Stock source: HF `mito0o852/OHLCV-1m` aggregated official US regular hours
  to 1H; evaluate 2021-09-28..2026-04-01 exclusive; current selected
  stock29 + SPY reference (survivorship and selection bias).
- Crypto: Binance USDT-M BTCUSDT/ETHUSDT 1H, evaluate
  2021-09-28..2026-09-28 exclusive, UTC completed daily/4H/1H.
- Warmup: 520 calendar days. Anti-lookahead from prior daily and confirmed 4H.
- Subperiod split pre-2024 and 2024+ is descriptive diagnostic; **not**
  an independent OOS dataset after viewing whole v1 results.

## Research gates
- Compare all A/B/C rather than cherry-picking.
- No success claim unless positive risk-adjusted performance survives cost
  stress, diverse years and unseen symbols/time; in-sample profit is not
  evidence of future profitability.
- Until validated, no production alerts, notifications or automatic trades.
- Remaining weaknesses: cash-to-stock-futures basis, order-book and market
  impact, missing liquidation and margin, within-hour extremes, funding
  settlement based on approximate notional, equity universe survivorship
  and corporate-action adjustment approximations.
- Explicitly separate source concepts from all invented numerical rules.
