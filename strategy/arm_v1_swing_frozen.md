# ARM v1 Swing — Frozen research specification

**State:** pre-results candidate, 2026-10-12. No claims of positive backtested performance.
**Repo:** this strategy is isolated from Track B, CAT, and Supabase / Telegram / live trade paths.

## Hypothesis
Combine (1) broad-market trend, (2) asset relative momentum, (3) confirmed 4H trend,
and (4) 1H post-pullback resumption. The signal must be fully mechanical.

## Instruments, clock, universe
- US equities: existing CAT stock30 set, without SPY (benchmark); includes QQQ as a tradable ETF. Research universe is historically post-selected; survivorship bias applies.
- Stock data: HF `mito0o852/OHLCV-1m`; use US RTH 09:30-16:00 ET only.
  Aggregate 1H bars from 09:30 ET; last daily bar is 15:30-16:00 (30m).
  Stock 4H-equivalent regime buckets are 09:30-13:30 and 13:30-16:00 (2.5h).
- Stock evaluation: 2021-09-28 through 2026-03-31 (exclusive end 2026-04-01).
- Crypto: BTCUSDT and ETHUSDT Binance Vision USDT-M 1H; 24h UTC sessions and actual UTC 4H groups.
- Crypto evaluation: 2021-09-28 through 2026-09-27 (exclusive end 2026-09-28).
- At least 520 calendar days are loaded for warmup. No incomplete daily/4H bars in signal or fill eligibility.

## Selection at previous *completed* daily close
- Market long: SPY (stocks) or BTC (crypto) close > EMA200; short the inverse.
- Stocks: LONG only; daily close > EMA50 > EMA200; stock 20- and 60-session returns **both** exceed SPY's corresponding returns.
- Stock ranking: top 30% of the research universe by (20-session return + 60-session return), evaluated on the prior completed day; no rank until 10 symbols have sufficient history.
- BTC: trades independently of the self-relative-strength test.
- ETH long: daily close > EMA50 > EMA200 and 20D and 60D returns both exceed BTC; ETH short: inverse daily trend and returns both below BTC.
- 4H: most recently completed bar close > EMA20 > EMA50 for long, inverse for short.

## 1H trigger
After trend selection, previous bar has closed at/below 1H EMA20 for long
(at/above for short); current confirmed 1H bar crosses to the other side of EMA20
and closes beyond the **prior bar's high/low**. Directional CLV >= 0.65.
At least one previous 8-bar low <= its EMA20 (long; high >= EMA20 for short).

- LONG buy stop: signal high + 0.05 * signal 1H ATR14.
- SHORT sell stop: signal low - 0.05 * ATR14.
- Expiration: next three 1H bars only.
- Recheck market, selection and last completed 4H regime at prospective *fill-bar open*, not after that bar closes.
- If market gaps past the trigger, use the open as entry.
- LONG initial stop: lowest low of last 5 bars INCLUDING signal bar minus 0.25 ATR14.
- SHORT initial stop: highest high of last 5 bars plus 0.25 ATR14.
- Initial risk filter: 0.5..4.0 ATR14; recheck using actual gap-adjusted entry.

## Exits / account rules
- TP1 at 2R for 50% of original position.
- TP2 at 3.5R for remaining 50%.
- On the close of the bar that reaches TP1, move remaining stop to entry; effective from the *next* bar only.
- If STOP and TP coexist within one OHLC bar: STOP first. If entry occurs in the same bar, assume adverse-first path after fill, conservatively. Gap stop fills at actual opening price.
- Time stop: stocks after 70 1H RTH bars (~10 sessions), crypto after 10 full calendar days.
- Cost each entry/exit fill: 4 bps commission + 2 bps slippage.
- Crypto funding: Binance historical settlement funding; approximate notional by entry notional and apply long/short sign to each exited leg. Missing funding archive is a hard failure, not silently assumed zero.
- Each position risks 0.5% of initial equity. Research portfolio accepts at most three concurrent 0.5%-risk positions = 1.5% open initial risk. Equal-time ties resolved by ticker.

## Implementation notes and validation gates
- `scripts/arm_v1_swing_core.py` is the shared deterministic core.
- `scripts/backtest_arm_v1_swing.py` supplies existing HF + Binance data adapters.
- `tests/test_arm_v1_swing.py` tests stop-first, gaps, next-bar BE, strict prior-daily, confirmed HTF bars, funding sign and portfolio exposure.
- CI uploads results as run artifacts; it does not change production signals or push research back to `main`.
- Initial research reports trade count, R, PF, year/symbol coverage and constrained-portfolio closed-trade DD.
- Future phase must integrate portfolio concurrency **inside** the simulator, compare realistic stock-futures basis / crypto funding, test unseen symbols and later unseen dates, and check liquidity, events, overnight gaps, reproducibility and sensitivity to small parameter changes.
- This research version explicitly omits exchange-specific fill/book depth, liquidation, borrow availability, taxes and dividends. Stock corporate actions are handled heuristically; data continuity must be audited before real orders.
- **No parameter adjustment following the initial report without a new version and a truly untouched validation period.**
