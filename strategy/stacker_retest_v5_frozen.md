# Stacker v5 — independent post-TP retest trades: frozen before results

Date frozen: 2026-10-12. Model is original research; NOT AGOS proprietary
algorithms. No production, alerts, Supabase, credentials or live orders.

## Why change the mechanism?
v1-v4 repeatedly demonstrated: after taking partial TP, rebuying simply
because the price has moved 1ATR adverse rarely improves total equity.
Crypto v4: static +0.67% / PF 1.026 versus strongest stop/rebuy filtering
still net negative. US stock v4: rotate_support +2.26% but 2022 alone
lost about 809 USD. Weak overall and differing markets.

V5 is a predeclared event-driven hypothesis: CLOSE the old position at
original frozen 4H EMA target in full. Afterward, if and only if a NEW
1H reclaim signal develops, open a SEPARATE trade with new support stop,
positive predeclared 2R payoff and a separate smaller budget.

This avoids the obsolete thesis of extending the OLD stop as a new trade's
justification. It is not "add more because underwater." We DO NOT call
2021-26 evaluation out-of-sample; prior v1-v4 research already exposed
many years and names.

## Locked four variants
1. control: v4 static full exit at frozen EMA TP; NO child trades.
2. retest: after target close, maintain a watch for 48 crypto hourly
   candles or 14 regular stock RTH candles. At a full 1H candle close:
   low touches frozen parent TP minus 1 parent ATR for LONG (reverse SHORT);
   close recovers >=0.25 * current 1H ATR above retest line;
   close above current completed 1H EMA20 (reverse SHORT);
   directional close-location-value >=0.65.
3. retest_htf: identical + last two completely CLOSED 4H EMA20 values
   slope in trade direction, recent closed 4H close on correct EMA20 side.
4. retest_htf_barrier: identical + prior CONFIRMED opposing 4H swing
   resistance/support cannot fall within 1.5 new stop risk of reentry.
   If no valid opposing swing, skip.

No reentry earlier than **NEXT 1H OPEN** after the confirming close.
Reject late gaps in the favorable chasing direction >0.75 current ATR.
If a watch expires or candidate is rejected, move on; never chase it.

## Fresh child trade sizing, stop and target
- Child is wholly separate, no transfer of old basis or old SL.
- Stop: minimum of the previous 6 completed 1H candle lows minus
  0.25 current ATR (LONG; SHORT uses max highs +0.25 ATR).
- Entry-to-stop risk must be within 0.75..3.0 current 1H ATR.
- Target: +2.0 times **actual fresh entry-to-stop distance**. No
  averaging down on a child, 100% exit at target.
- Stop ratchets ONLY toward break-even after a bar CLOSES beyond +1R,
  effective on the NEXT bar. Never lower old/new stop to enable more risk.
- Max child age: 72 hourly crypto candles /21 RTH stock candles.
- Child notional <=70% marked equity and initial stop-risk
  INCLUDING estimated 10bp each-side fees <=0.375% marked equity.
  Parent pre-existing limited risk 0.75%, max two active cycles
  portfolio-wide. One new child candidate per completed parent-TP
  watch, old watch expires when a new parent entry supersedes it.
- Parent is EXACT v4 static logic: 4H BB cross + yesterday's EMA200
  regime gate; swing 4H pivot SL; frozen 4H EMA20/EMA50 TP;
  4-step DCA with fee-inclusive 0.75% risk, 70% cycle notional.
- For parent and child stop/TP ambiguity in 1H OHLC stop ALWAYS wins.
  True existing-position gap losses fill at the actual OPEN.
- Cost 4bp estimated commission +2bp slippage per fill/side,
  stressed at 10bp/side. Binance historical funding rate/close
  notional proxy for BTCUSDT and ETHUSDT.

## Research evaluation
- BTC/ETH USDT-M 2021-09-28..2026-09-28 exclusive, 5 years;
  US equity/ETF selected RTH universe from 2021-09-28 through
  2026-04-01 exclusive. Starting cash 20,000 separately each market.
- Compare full-account return/PF, hourly CLOSE marked-to-market MDD,
  trade count, parent vs child PnL, child PF and missed retests,
  year-by-year and per symbol returns, +4bps/side cost stress.
- Comparative results are NOT untouched OOS. No post-results
  threshold fine-tuning based on this historical period.
- Critical limitations: stock survivorship bias/current research
  universe; no futures stock-basis execution model; omitted exchange
  liquidations/order-book/gap stress; funding settlement price proxy;
  hourly-close DD misses intra-hour excursions; one BTC+ETH sample.
- **Acceptance:** child substrategy should independently have PF well
  above 1 and survive cost stress and multiple years, NOT just
  increase raw win ratio or exploit more initial risk exposure.
- No real-time execution or notification changes in this branch.
