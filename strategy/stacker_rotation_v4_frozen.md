# Stacker rotation v4: pre-registered multi-angle ablation study

Frozen 2026-10-12 BEFORE all v4 benchmark results. This is our
own research code, not AGOS proprietary formulas. No user funds,
live credentials, Telegram, Supabase or existing Track B/E systems touched.

## Question / anti-overfitting design
Prior AGOS-inspired mean-reversion Stacker had near-zero or negative
5y crypto profit, and v3 partial TP + rebuy + lower stop worsened crypto
even while improving stock slightly. Can the LOSS MECHANISM be reduced
by (i) requiring a real bounce, (ii) requiring higher-timeframe momentum,
(iii) locking in prior realised profit, (iv) reducing added exposure,
or (v) keeping a trailing runner instead of rebuying?

V4 freezes seven candidates *before* checking the output. We compare
all markets and annual subperiods without retrospectively selecting only
the winners. Treat the past evaluation window as in-sample comparative
research, NEVER independent prospective OOS.

## Common structure and risk, frozen from v3
- Existing Stacker 4H Bollinger(20,2) mean reversion signal and
  prior-complete-day benchmark/asset EMA200 filter, RTH US stock LONG,
  BTC/ETH crypto LONG/SHORT.
- Entry at next 1H OPEN after signal; 4H support pivot confirmed with
  2 completed bars each side, structural SL beyond pivot by 0.25 ATR,
  fixed absolute EMA20/50 structural profit target.
- Initial 4 levels first + adverse 1/2/3 ATR, weights 1/1.25/1.5/1.75,
  unless a single explicit ablation changes the ladder.
- Conservative OHLC: genuine gap stop fills at open; hard stop priority
  for intrabar ambiguities; no same-hour rebuy or TP after an add.
- Total planned loss INCLUDING stress-fee estimate (10bp per side)
  limited to 0.75% of the entry marked equity for the full initial
  planned grid; notional limited to 70% of entry equity, max 2
  simultaneous positions. Actual gap loss can exceed planned risk.
- Max cycle hold 14 days crypto /70 RTH hourly bars stocks;
  no more than TWO completed rebuys, partial TP 50% of then-open units,
  first rebuy at frozen initial TP minus 1 ATR LONG / plus 1 ATR SHORT.
- Runner exits: first TP + another 1.5 ATR favorable if no rebuy,
  48 crypto hrs or 14 RTH hourly bars rebuy expiry otherwise.
- On any rebuy and optional SL movement require worst overall
  completed-cycle net PnL at proposed SL (including previous partial
  realisation, fees and funding) >= -0.75% initial budget, including
  stressed 10bp final exit estimate. Reject unsafe rebuy, no exception.
- Crypto approximate historical settlement funding; execution costs
  6bp each side baseline, 10bp each side stress.

## Seven predeclared arms
1. `static`: entire quantity exits at initial structural TP. No rotation.
2. `rotate_support`: frozen v3 immediate 1ATR pullback-limit rebuy,
   SL changed ONLY if a newly confirmed 4H pivot lower (LONG) / higher
   (SHORT) exists and worst-case risk remains bounded.
3. `confirm_support`: after price touches rebuy limit, previous 1H
   bar must CLOSE at least +0.25 ATR above it (LONG) / below SHORT,
   AND directional CLV >=0.65. Rebuy only at NEXT 1H bar OPEN, no
   chase of >1.25ATR above/below the trigger. Still requires fresh
   confirmed support + risk headroom to move the stop.
4. `trend_support`: same frozen v3 rebuy but require last two
   *completed* 4H EMA20 values slope toward trade and last completed
   4H close on correct EMA20 side.
5. `protect_profit`: on first TP, tighten stop toward original entry
   minus 0.25 ATR (LONG, reversed SHORT), then permit limit rebuy
   only with that tighter stop unchanged and with the same worst-case
   risk/notional guard. This ablation deliberately does not lower SL.
6. `light_ladder`: only initial levels 0 and 2 ATR adverse with
   weights 1:1.3, re-risk-sized for the same fee-inclusive 0.75%
   worst-case cycle loss. Rebuy uses the same confirmed pivot and
   worst-case guards as arm 2.
7. `trail_runner`: on first TP, take 50% profit and **do not rebuy**.
   Manage remaining core with confirmed 4H EMA20 +/-0.5 ATR,
   stop only tightens on LONG / lowers SHORT and only from the NEXT
   bar, plus existing runner TP or time exit.

## Validation gates
- BTCUSDT+ETHUSDT Binance USDT-M historical 1H 2021-09-28 to
  2026-09-28 exclusive; 29 selected stock/ETF symbols RTH
  2021-09-28 to 2026-04-01 exclusive.
- Same underlying OHLCV adapters, cost stress, initial equity 20,000,
  position event ordering, and historical fixed order of symbols.
- Compare each variant to BOTH control arms; report profit factor,
  net return, 1H-close mark-to-market MDD, total trades, number
  of realised rebuys, number of actual stop changes and fee stress.
- Inspect 2021-2023 vs 2024+ results, loss years and symbol breadth.
  Static results can differ slightly from historical v2 because v3
  reserves expected stress transaction costs on all initial fills.
- Do not adopt if overall edge is close to zero, fails cost stress,
  depends on a single year or one symbol, or disjoint future OOS fails.
- Limitations: HF current stock selection introduces survivorship bias,
  1H OHLC adverse-first path ambiguity, funding proxies use close not
  exact futures mark, no exchange margin/liquidations, gaps can exceed
  planned stop and 1H-close drawdown misses intrabar extremes.
