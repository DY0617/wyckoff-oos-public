# Stacker rotation v3 — pre-results research rules (2026-10-12)

This independent strategy combines our previously tested **4H confirmed pivot
support-based stop + EMA20/50 take-profit** with cyclic partial realisation.
It does NOT replicate or claim access to any AGOS proprietary trading code.

## Meaning of "순환매"
On a filled structural EMA target, sell 50% of current open units. Keep the
rest as a live core and place a NEW rebuy trigger at target - 1 ATR (LONG);
for SHORT, target + 1 ATR. If this level is touched after the profit-taking
candle, buy back the exact number of units just sold, at the better of the
resting limit and open, provided hard-risk/notional guards pass. Repeat
at most **two completed buy-back cycles**. On next structural TP after
the second buy-back, exit all remaining units.

Rebuy orders do not fill in the same bar as the partial TP. Existing stop
wins all same-bar stop / rebuy ambiguities. On the rebuy candle the OLD
stop remains effective; any lower stop only becomes effective once the
hour closes. No short-side profits are assumed before price hits the bid.

If there is no rebuy, a remaining profitable core can exit at an additional
1.5 ATR favorable from the original TP, or after 48h crypto / 14 RTH hour
bars stock, or via existing hard stop. Global max hold: 14 calendar days
crypto or 70 RTH hourly bars (~10 sessions) stocks.

## Comparison: four *predeclared* variants
1. `static`: identical structural entry, ladder and hard stop but all units
   exit on first structural EMA target. Risk-inclusive sizing below applies.
2. `rotate_fixed`: partial TP/rebuy cycles but original structural SL stays fixed.
3. `rotate_lower`: rebuy cycles with stop LOOSENED 0.25 * frozen ATR
   after each approved rebuy (LONG lower, SHORT higher), if risk budget permits.
4. `rotate_support`: rebuy cycles with dynamic 4H CONFIRMED lower pivot
   for LONG (higher for SHORT) as revised SL, separated from old stop
   by at least 0.25 ATR. No qualifying support or insufficient risk
   reserve => skip the rebuy and keep managing core, rather than invent SL.

The key difference between 3 and 4 is that 3 measures pure risk-funded
stop loosening, whereas 4 additionally requires confirmation from recent
**closed 4H candles** at the rebuy decision timestamp. Pivots have 2 candles
to the left and right; never use future data. Initial stop and absolute EMA
TP come from structure frozen at the ORIGINAL 4H signal close.

## Initial setup / risk
Use existing Stacker v2 `sr_ema` initial setup: Bollinger 20/2 4H band
crossing, prior completed daily EMA200 bullish/bearish regime, next 1H
open first entry. Fixed four-fill ladder at entry, 1/2/3 ATR adverse
with weights 1/1.25/1.5/1.75; initial stop at valid confirmed 4H pivot
minus 0.25ATR (LONG; reversed SHORT), 3.5..8 ATR distant; favorable TP
at the closest valid 4H EMA20/50 0.5..8 ATR above entry LONG
(below SHORT). No valid structure => skip.

- Initial equity 20,000 USDT/USD. Full four-fill worst-case stop loss
  INCLUDING estimated 10bp fee/slippage each side <=0.75%
  contemporaneous marked portfolio equity (excluding gaps/funding).
- Maximum full-cycle gross notional 70% equity, max 2 simultaneous cycles.
- Once partial take profit occurs, unused initial DCA ladder is CANCELLED.
- On any rebuy and possible stop change, estimate total cycle PnL if *all
  remaining units exit at revised stop*, including all previously realised
  gross profits, historical fees, accrued funding and pessimistic 10bp
  future exit fee. Must be >= **minus initial 0.75% risk budget**.
- Per-cycle post-rebuy notional must remain <=70% entry equity; no infinite
  averaging, profit compounding or external leverage.
- If lower-stop extension cannot fit that bound, do NOT extend the stop.
  Modes 3/4 reject the rebuy entirely; no invisible SL widening.
- Funding uses Binance historical settlement rates with hourly close
  mark proxy; 6bp fee+slippage each entry/exit side and 10bp cost stress.
- Sizing and stops cannot guarantee an actual exchange loss floor when
  stops gap, liquidation occurs, spreads widen or funding spikes.

## Data, diagnostics and acceptance
- Crypto BTC/ETH USDT-M continuous hourly candles 2021-09-28 to
  2026-09-28 exclusive; stock research-universe US RTH
  2021-09-28 to 2026-04-01 exclusive.
- 520-day indicator warmup, strictly completed 4H pivots and daily EMA200.
- Multi-symbol chronological 1H simulator with positions marked to
  market including partial realised PnL and outstanding cost bases.
- Track returns, PF, marked equity MDD, longest losing streak,
  cost stress, yearly/symbol exposure, *realised* number of rebuys
  and risk-compliant SL moves. Do not count mere reentry signals as fills.
- No live orders, no Supabase or Telegram changes.
- All thresholds frozen BEFORE reviewing v3 results; no posthoc
  reoptimization on the same evaluation dates.
- MTM MDD sampled at hourly closes only; stock post-selection bias,
  approximate corporate actions and funding, lack of exchange margin,
  order book, liquidation and exact stop execution remain limitations.

The purpose is to test whether recycling profits to fund a lower stop
produces genuinely better expectancy, rather than disguising an
unlimited martingale or pushing losses into the future.
