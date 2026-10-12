# Tactical v13 — next-session drift risk control and passive cash slices

Predeclared 2026-10-12 before seeing v13 backtest outcomes.
No live orders. No production files, Supabase, Telegram, exchange
keys or existing Track B/E / Wyckoff settings changed.

## Research question: better control with honest opportunity cost

v12 actual Binance SPOT monthly capital allocation demonstrated
market-dependent risk/growth tradeoffs. Original `gate_cap` restricted
TARGET risky weights to <=50% gross and <=20% per symbol at monthly
rebalancing, but marked exposure subsequently DRIFTED above
those limits (peak ~57.4% on five-coin spot, ~56.2% in selected
US stocks). Calling 50% a hard always-on cap would be FALSE.

v13 specifically tests **causal next-session liquidation of
breached target weight**, not a miraculous protective stop.
Compare against the prior unchanged monthly strategy and a simple
passive cash-funded benchmark chosen BEFORE the results.

## Exactly five PREDECLARED portfolio arms per market

All use the same true Binance SPOT daily data (for crypto)
and the same previously selected HF RTH US-equity bars.
Entire portfolio fully paid for: no margin, no short,
no incremental outside cash deposits.

1. `risk_managed_gate` — unchanged v11/v12 monthly dynamic
   BTC/SPY EMA200+63d momentum gate, rank and trailing vol
   size, no explicit 50% investment cap.
2. `gate_cap` — unchanged v12 monthly risk gate with risky
   rebalance TARGET at most 50% total, 20% each asset.
   It permits drift between monthly rebalances.
3. `gate_cap_daily` — EXACT same `gate_cap` monthly
   selection/weights. On EVERY other reference trading-day,
   inspect holdings' **last FULLY CLOSED daily mark**;
   if last day gross risky exposure is >50%, OR ANY
   single asset is >20%, SELL at NEXT day's actual
   opening price to targets <=48% total and <=19%
   each symbol. No unearned fill at the prior CLOSE.
   Any untradable name cannot be sold until an
   actual execution session; count such cases.
   No buys between scheduled monthly rebalances.
   No triggers based on current day's HIGH/LOW/CLOSE
   before its opening price.
4. `passive_25_bench` — one-time long-only initial purchase
   of exactly 25% nominal benchmark BTC/SPY at first
   evaluation day OPEN; hold remaining 75% as zero-yield
   CASH until sample end; no ongoing trading/rebalancing.
5. `passive_50_bench` — same but 50% BTC/SPY / 50%
   cash. This is a precommitted reference, not a
   retrospectively chosen exact volatility-matched
   portfolio. In BTC cohorts 25% is near the v12 five
   crypto's mean risky exposure; in stocks 50%
   is near v12 stock gate mean exposure, but exact
   time-variation and correlation differ.

No optimization of 50/20/48/19 numbers once results
are inspected. These are operationally meaningful
human-readable control thresholds; NOT guaranteed
optimal statistical parameters.

## Causal and execution honesty

- At month-open, all target weights derived from prior
  completed DAY only; buys and sells use that
  month's NEXT available actual daily open.
- On non-monthly trade dates in arm 3, if YESTERDAY's
  holdings exceed caps by last completed CLOSE, compute
  CURRENT OPEN pre-sale equity and sell down
  to 48%/19% buffers by **current OPEN quotation**.
  If there are no valid OPEN prints, log inability to sell
  and DO NOT synthetically execute any sale.
- Open gap can push current exposure above desired limits
  even before the next opportunity to act. Intraday prices
  can push exposure above cap again after order execution.
  This is a NEXT-SESSION reactive control, **NOT 24/7
  hard guaranteed worst-case risk protection**.
- Preserve v12 1% monthly no-trade band. Extra sells
  under the drift rule are not subject to that band,
  so very small overflows may create additional fees.
- Same fixed nominal 6bp commission+slippage each
  buy/sell side, severe 20bp each side; same
  cash-held 0% annual yield in baseline and
  purely illustrative 3% rate scenario.
  Cash interest assumed between observed reference
  trading days only. This 3% is NOT verified
  historic bank/broker availability.
- One-time buy-and-hold cash slice reference does not
  top-up its weight or borrow money. Any cash
  constraints violated => FAIL test.

## Three separate retrospective cohorts (same as v12)

A. BTC+ETH actual Binance SPOT daily, Sep 28 2021
   to Sep 28 2026 EXCLUSIVE.
B. BTC+ETH+BNB+SOL+XRP actual Binance SPOT,
   Jun 1 2022 to Sep 28 2026 EXCLUSIVE.
C. Original 29 selected US-stock/ETF HF RTH,
   Sep 28 2021 to Apr 1 2026 EXCLUSIVE,
   SPY benchmark (NOTE survivorship bias).

Each starts at 20,000 USD or USDT independently.
Daily-close marked equity, realized trade logs,
annual year returns, max DD, CAGR, time exposed,
fees, total executions, calendar days above
50%/any name >20%, and missed no-open cap trades
are compared. Severe fixed cost stress and 3%
illustrative cash yield are separate scenarios.

## Falsification gates and important limitations

1. Before market-wide results, test V13 against
   unmodified V12 trade ledger on ALL ten existing
   modes with the same synthetic candles; for main
   two v12 modes also require exact real-dataset
   return, DD, fees and execution-count parity.
2. The daily cap does NOT get credit solely for
   reducing MDD by holding less cash-adjusted risk;
   compare to 25% and 50% benchmark + cash.
3. More daily selling is itself a disadvantage:
   report turnover/execution count and 20bp
   adverse fee-cost scenario. If daily control
   reduces returns while providing little DD
   protection, reject and keep monthly.
4. Not a guaranteed continuous cap, no exact
   tick/intraday mark-to-market, no exchange
   downtime/halts/liquidity shocks, no taxes
   or partial fill/slippage depth.
5. Crypto data are actual SPOT price bars, NOT
   a Binance USDT-M perpetual future simulation.
   No funding, margin, forced liquidation or
   futures execution assumptions are supplied.
6. Equities retain serious look-ahead
   survivorship/corporate-action and
   cash vs futures execution concerns.
7. 2021–26 prices are extensively mined through
   v1–v12; not unseen OOS, and selection of the
   most profitable new variant after results
   is NOT evidence of future return.
8. The correct standard for live use remains
   frozen prospective paper testing on truly
   unseen time, delisted-aware stock source,
   broker/account-specific fill and all costs.

**Nothing shall be promoted to live orders solely because
a retrospective backtest produces a positive total.**
