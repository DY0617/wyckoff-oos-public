# Stacker v7 — pre-results innovation / new-instrument holdout study

Frozen: 2026-10-12, BEFORE checking v7 outcomes.
Independent research strategy, NOT AGOS internal algorithm.
No new exchange orders, live trading, Telegram or Supabase changes.

## Motivation and research integrity
- Past BTC/ETH 5-year v6: 4H ATR/close top-20% skip = +3.32% net,
  PF 1.155 and hourly-close MTM MDD 3.46%, but 2023/2026 losses.
- Past US stock v6: same skip = -2.94%, worse than its already losing
  -3.17% base only slightly; additional market differences matter.
- All previous experiments used the SAME historical dates. There is
  substantial multiple-comparisons/data-snooping exposure.
- Avoid parameter tuning on these dates; to falsify the volatility
  intuition use **unseen underlying markets** BNB, SOL, XRP, with
  own historical futures funding. This is instrument-holdout, not a
  blind future-date or untouched trading period. Do not call it OOS
  in the time-split sense.

## Data and cohort splits (each one separate simulated account)
- Known crypto, *development comparator*: BTCUSDT+ETHUSDT, Binance
  USDT-M 1H 2021-09-28 to 2026-09-28 exclusive, 520d prior warmup.
- New **instrument holdout**: BNBUSDT+SOLUSDT+XRPUSDT, Binance
  USDT-M 1H 2022-06-01 to 2026-09-28 exclusive, BTCUSDT only
  as benchmark (do not trade BTC in holdout). 520d prior warmup,
  each month must exist or fail rather than invent missing data.
- US stock selected 29 equity/ETF RTH instruments: 2021-09-28 to
  2026-04-01 exclusive, reference SPY, current research universe
  with survivorship, post-selection and split-approximation biases.
- Do NOT compare raw holdout and known group account returns as though
  they have equal dates or equal number of traded instruments.

## Unchanged bounded Stacker core
- 4H Bollinger 20/2 outside-band cross; previous completed daily
  asset + benchmark EMA200 regime. LONG on US stocks, LONG/SHORT
  BTC/ETH/holdout crypto.
- First entry at next 1H bar OPEN, confirmed 4H pivot structural
  STOP 0.25 ATR beyond previous support/resistance, valid
  3.5..8.0 ATR distance. Frozen EMA20 or EMA50 nearest valid
  favorable 4H structural TP from same signal, 0.5..8 ATR.
- 4 fixed-stage fills first and adverse 1/2/3 ATR, weights
  1/1.25/1.5/1.75. Full liquidation at stop, TP, or time limit.
  0.75% of then-marked equity maximum *planned* cycle risk
  including stressed estimated 10bps/side exit+entry fees; max
  70% notional per cycle and 2 concurrent cycles.
- No synthetic average-down beyond the four levels, no leverage
  amplification, never relax stop after loss, no post-TP rebuys.
- Exit hard stop takes priority on ambiguous OHLC; exit gaps
  fill actual OPEN for preexisting positions. Only 1H-close MTM
  drawdown can be reported; intrahour drawdown can be worse.
- Binance historic funding settlement proxy, nominal 4bp fee +
  2bp slippage per side, stress +4bp/side.

## Eight predeclared isolated regime/entry tests
1. control — frozen v6 static (no new filter).
2. asset_vol_skip — do not trade when prior completed 4H
   asset ATR14/close exceeds the historical 80th percentile of
   latest 80 completed 4H ATR14/close observations.
3. benchmark_vol_skip — exact same test on benchmark BTC/SPY;
   the actual traded instrument's volatility is NOT used.
4. either_vol_skip — reject if either asset OR benchmark volatility
   is in its top historical quintile.
5. bb_rejection — 4H BB break bar must exhibit a contrary wick,
   directional close location (CLV) >=0.35. LONG (close-low)/
   (high-low); SHORT (high-close)/(high-low). The relevant
   4H candle is EXACT the fully closed signal candle.
6. asset_vol_rejection — BOTH asset_vol_skip and bb_rejection.
7. shock_skip — reject if completed 4H signal candle's full range
   >2.25 * its completed ATR14, avoiding news-like expansion.
8. graded_size — high-vol state => cut full DCA ladder and
   planned worst-stop budget to HALF, near-high if ATR/close
   >0.85*80th-percentile => multiply risk and all fills by
   0.75. Never increase exposure above control.

All decisions at entry OPEN use only previously fully closed 4H
and DAILY indicators; no future 1H high/low. The optional signal
source check enforces 4H close timestamp = recorded signal close.
The holdout cohort uses three crypto positions competing for a
common two-cycle portfolio cap, so headline performance may also
differ from simply adding individual annual trades.

## Acceptance or rejection
- Run all 8 variants across all 3 cohorts, two transaction-cost
  assumptions (6bp nominal vs 10bp stressed EACH SIDE).
- Report net return, PF, 1H close MTM MDD, number of cycles,
  signaled/skipped reasons, risk reduction, symbols and years.
- No live adoption based on positive **sample** returns.
  A true unseen future test, independently priced execution,
  alternate timestamps / data vendor, proper margin and
  funding mark treatment and full stock symbol selection
  would still be required.
- No re-tuning thresholds based on these holdout assets; report
  failures equally, never cherry-pick only winners.
- Include only BTC/ETH for established crypto-comparator,
  do not mistakenly include the BTC BENCHMARK as a traded
  symbol in holdout returns.
