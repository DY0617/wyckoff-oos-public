# Entry First v8 — complete 3-cohort research decision

Final observed 2026-10-12. Successful GitHub Actions test and all three
backtests run #38227833803:
https://github.com/DY0617/wyckoff-oos-public/actions/runs/38227833803
13 causal/execution invariant tests PASS. This is independently
implemented research, NOT AGOS proprietary code or live financial PnL.

For design and methods:
[entry_first_v8_frozen.md](entry_first_v8_frozen.md).
For BTC/ETH and BNB/SOL/XRP details:
[entry_first_v8_crypto_results.md](entry_first_v8_crypto_results.md).

## US RTH selected contemporary stock/ETF cohort

Historical 2021-09-28 to 2026-04-01 exclusive (approximately 4.5 years),
20,000 USD initial research equity, risk 0.5% of current marked
account per trade INCLUDING 10bps/side pre-estimated fees,
maximum 3 open positions, 70% equity notional each,
no DCA, no partial exit or moving SL, fixed 2R target.
Default fee/slippage 6bps per side, stress 10bps per side.
Drawdown from 1H-close marked equity; selection bias and
cash-to-stock-futures basis must be considered.

| Entry mode | Trades | Return | PF | MTM MDD | Mean net R | Mean MAE R | Mean MFE R | +4bp/side cost-stress return |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| sweep | 878 | +0.63% | 1.002 | 13.37% | +0.007 | 0.776 | 1.080 | -16.99% |
| pivot-break CHoCH proxy | 1015 | -8.78% | 0.968 | 20.35% | -0.017 | 0.758 | 1.045 | -23.71% |
| breakout_retest | 1131 | -18.79% | 0.940 | 24.26% | -0.037 | 0.775 | 1.074 | -36.03% |
| sweep_choch | 406 | -1.50% | 0.986 | 11.80% | +0.001 | 0.752 | 1.009 | -7.81% |
| sweep_choch_retest | 273 | -6.40% | 0.907 | 10.72% | -0.041 | 0.746 | 0.993 | -10.39% |

Stock sweep gross net profit especially sensitive to selected date:
realised trade PnL (USD) by entry year 2021 +373, 2022 +83,
2023 +304, 2024 +1273, 2025 +589, partial 2026 -2496.
Even the best stock headline profit is near-zero and heavily
dominated by the adverse 2026 sample.

## All three cohorts: the same sweep alone

| Cohort | Period | Trades | Return | PF | MDD | +4bp/side |
|---|---|---:|---:|---:|---:|---:|
| BTC/ETH | 2021-09..2026-09 | 1139 | +20.40% | 1.058 | 19.43% | -8.58% |
| BNB/SOL/XRP | 2022-06..2026-09 | 1414 | -8.95% | 0.977 | 16.52% | -32.52% |
| 29 selected US stocks | 2021-09..2026-03 | 878 | +0.63% | 1.002 | 13.37% | -16.99% |

The CHoCH and retest proxy variants did not improve mean
per-trade favorable excursion or MDD-adjusted expectancy across
the cohorts. The "CHoCH" test is a mechanical recent pivot
break proxy and should not be confused with a guaranteed
discretionary market structure shift.

## Decision

**REJECT all five as ready-to-trade entry engines.**

One cohort's promising headline sweep return was not replicated
on other assets and sign-flipped under a modest fee/impact stress.
Heavy 1H adverse excursions (about 0.75..0.81 initial R on most
arms) and lack of portable positive net R are the crucial
diagnostics. Adding more sequential confirmations reduced
frequency but did not establish entry edge.

Possible **separate, preregistered** next hypothesis (not yet
tested or implemented): compare execution near reclaimed support
using causal waiting LIMIT orders with explicit nonfill/cancellation,
rather than immediate market entry after sweep; quantify
unfilled orders, stop distances, MAE and all trade
opportunity costs at nonoptimistic fills. Avoid retuning on
these already-observed periods and claim of new blind OOS.

Research constraints: previous strategy exploration has
exposed all calendar date ranges and many instruments;
future-date data and genuinely disjoint instruments are needed.
1H OHLC unknown exact fill order, fixed cost proxies, futures
margin/liquidation, corporate actions/survivorship and gaps
can change realized outcomes. NO production services,
Telegram, Supabase, exchange keys or live strategy was changed.
