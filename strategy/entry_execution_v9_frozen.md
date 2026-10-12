# Entry First v9 — pre-registered better-entry execution study

Frozen October 12, 2026 BEFORE observing ANY v9 backtest outcomes.
Research-only, no live orders/production notifications. Independently
designed price-action trading system, not proprietary AGOS implementation.

## Core problem and research hypothesis

v8 tested sweep/CHoCH/retest under exactly one bar-open entry and +2R TP.
All 5 variants failed to generalise and/or transaction-cost stress.
Best known-coins sweep: +20.40% over ~5y, PF 1.058, but -8.58%
if fees/slippage increased by +4bps per side. On new-asset cohort
BNB/SOL/XRP sweep -8.95%. Mean adverse excursion ~0.77..0.79R,
consistent with consistently poor entry placement.

Hypothesis: *keep exactly the same confirmed 4H sweep signal and
hard stop*, but wait for a cheaper **resting limit fill** at
previously known prices; record all missed, expired and unsafe
orders, actual entry-to-stop distances and TP/SL outcomes.
This tests order price vs signal identity without hiding
abandoned opportunities. Hard reject a strategy if unfilled
signals cause poor opportunity cost or unrealistically assume
tick-perfect fills.

## Eight PREDECLARED arms (one variable / combined versions)

1. `market`: v8 identical next-1H-open execution; baseline.
2. `market_shock`: market entry, but skip if completed 4H
   signal-bar range / completed 4H ATR14 > **2.25**.
   2.25 is a prior v7 research observation, NOT new OOS.
3. `limit_half`: place LONG buy LIMIT at completed signal
   close -0.50 * completed 1H ATR14 (SHORT inverse).
   Wait up to 8 complete 1H bars (incl earliest next-open).
4. `limit_reclaim`: LONG limit at previously confirmed
   swept support pivot +0.10 * completed 1H ATR14
   (SHORT inverse at swept resistance -0.10 ATR).
5. `limit_deep`: LONG limit at swept 4H extreme +
   0.70 * completed 1H ATR14 (SHORT inverse).
6. `limit_half_shock`: arm 3 with arm 2's shock skip.
7. `limit_reclaim_shock`: arm 4 with arm 2's shock skip.
8. `limit_half_2h`: arm 3 but limit order expires after
   2 completed 1H bars instead of 8.

For every limit: if planned limit price would be WORSE
than the completed signal CLOSE, reject it. Price,
quantity, TP/SL and order expiry are frozen by data
available when next 1H OPEN arrives. Never move an
unfilled order to fit the observed future candles.

**Execution convention and simulation realism**
- STOP = original 4H swept extremum +/-0.20 * signal 1H ATR,
  frozen from v8. Only admit risk distances 0.65..3.50 * ATR.
- TP = entry price +/- 2.0 times ORIGINAL ENTRY-TO-STOP
  distance; no break-even, ladder, partials or stop widening.
- Planned stop loss including **stressed 10bps each
  side** <=0.5% of currently marked account; notional
  <=70% current equity per position; maximum 3 positions
  including RESERVED pending limits. No hidden leverage.
- At the earliest eligible bar OPEN, place a resting limit,
  not intrabar hindsight. If OPEN gaps across the stop,
  CANCEL the order before placing. If the OPEN is better
  than limit but above/below the stop, fill at OPEN;
  otherwise fill only if that hour's high/low TOUCHES
  the resting limit.
- If limit touch and stop both occur in that hour,
  assume ENTRY followed by immediate STOP, even though
  exact intrabar order is unknown. This penalises the
  strategy rather than introducing phantom profits.
  Never credit a TARGET hit on the SAME entry hour.
- Full limit quantity assumed to fill on a price touch,
  an optimistic queue/liquidity assumption. This cannot
  prove live executable results. Stress fill uncertainty
  still necessary after finding a viable edge.
- Unfilled orders reserve one portfolio slot until
  expire; don't retrospectively fill after expiration,
  and track filled / cancelled / end-of-data explicitly.
- Explicit earliest eligible 1H period (next hour after
  fully confirmed 4H sweep), max age eight hours
  default or two-hour sensitivity.
- Historical Binance funding at settlement hour with
  closing notional proxy, fees+slippage 6bps EACH side
  nominal and 10bps EACH side stress.
- Stop-gap fill at actual OPEN for existing positions,
  not optimistic stop price; trade time stop same as v8.

## Fair comparison, objective diagnostics

Markets each run as independent hypothetical 20,000 USD/USDT
accounts:
A. BTCUSDT+ETHUSDT USDT-M 2021-09-28 to 2026-09-28 exclusive.
B. BNBUSDT+SOLUSDT+XRPUSDT USDT-M 2022-06-01 to
   2026-09-28 exclusive, BTC as benchmark but not traded.
C. 29 selected US RTH stocks/ETFs from 2021-09-28 through
   2026-04-01 exclusive (SPY reference).
Historical 1H OHLCV, 520d indicator warmup.
Record ALL eight arms for each cohort plus 10bps
cost stress, annual/symbol and total trade stats,
mean MAE/MFE in R, target-hit rate, original candidates,
submitted orders, filled and cancelled, fill delay,
risk geometry rejects, costs and 1H-close MTM DD.

**Pre-declared rejection criteria**:
- Do not claim entry edge based on few fills or good win rate.
- Must beat fixed-cost market benchmark on risk-adjusted metrics
  WITHOUT using future price to decide when to place an order.
- Must stay profitable under 10bps/side stress, at least one
  new instrument cohort and multiple annual regimes.
- 2021-26 dates have been repeatedly seen; *nothing* here is
  truly calendar held-out OOS even if names were fresh in v7.
- If a limit works only by always missing losers and doing
  zero trades, not a useful executable strategy.
- Any favorable outcome needs additional true future-date
  OOS, exchange queue/partial-fill/volume checks, detailed
  funding/mark/margin modelling and stock survivorship correction
  BEFORE manual or automated live use.

NO existing Track B/E, Supabase, Telegram or exchange order
pipeline has been modified in this branch.
