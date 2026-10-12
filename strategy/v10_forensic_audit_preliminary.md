# V10 forensic robustness audit: trade-ledger findings

2026-10-12, initial review. *Not a strategy or investment recommendation.*
Original complete GitHub Actions run: 38237159212.
Trade artifacts:
- `entry-expansion-v10-known-crypto` #11741272247
- `entry-expansion-v10-new-crypto` #11740703188
- `entry-expansion-v10-stock` #11741552868

All figures were recomputed directly from trades and hourly marked curves
rather than copying published 2-decimal headline percentages. Exact
ledger accounting check PASS:
`sum(closed_trade_pnl) == last_equity - initial_equity` to
within 5 US dollars cents for all inspected variants.

## Claimed best-of-cohort research findings, before realistic cash cap

| Metric | Stock compression 2021-09..2026-03 | BTC+ETH regime 2021-09..2026-09 | BNB+SOL+XRP regime 2022-06..2026-09 |
|---|---:|---:|---:|
| Trades | 237 | 216 | 304 |
| Net PnL in $/USDT | +2,772.95 | +1,602.12 | -240.42 |
| Net % of starting 20k | +13.86% | +8.01% | -1.20% |
| 2023 entry-year PnL | **+2,723.20** | +69.74 | -887.75 |
| Net PnL *excluding 2023* | **+49.76** | +1,532.38 | +647.33 |
| Net PnL excluding best 10 winners | +683.96 | -415.3 | -2,121.5 |

For stock compression, **2023 produces 98.2% of the entire net PnL**
while 2025 and early 2026 contribute losses. Leaving out those
trades (NOT a re-simulation) means an aggregate PnL of only
+49.76 USD across the remaining entry-year categories. This
is loss-concentration diagnostics, not a literal alternative
portfolio strategy. Removing top winners is also a stress
diagnostic, NOT a causal counterfactual: compound position sizing
would differ.

The BTC/ETH market-regime arm earned about +1,639.7 USDT on
BTC and LOST about -37.5 USDT on ETH. Removing the 10 most
profitable individual closed trades leaves ~-415 USDT in
the original ledger. Again that is a concentration audit,
not a re-simulated trading strategy.

## True stock gross purchase funding problem discovered

The original Entry First v8/v10 simulator limits gross purchase
notional to 70% of equity **PER trade**, not TOTAL. It allows
up to 3 simultaneous stock LONG positions and never reserves
cash for outstanding share purchases. This can imply borrowing
without any explicit margin financing model.

Reconstructing opening share quantity from known fee model,
`quantity = realized_fill_fees/(0.0006*(entry_price+exit_price))`,
then sweeping simultaneous original stock compression trade
intervals, gives:
- **Peak outstanding stock purchase notional ~31,024 USD.**
- Initial capital 20,000 USD -> **155.1% of starting capital.**
- At the peak trade entry, most recent hourly marked portfolio
  equity ~23,446 USD -> roughly **132.3% of contemporaneous
  portfolio equity**. No stock margin cost/liquidation limits
  are modelled.
- This does **not** mean leverage was 155% every trade/hour,
  but enough to invalidate treating the historical stock
  gain as strictly cash-account executable.

### Corrected parallel rerun

Research branch `research/v10-capital-audit` includes new
`scripts/entry_v10_audited_cash_engine.py` that creates
NO more stock positions than fully fundable by realised cash
minus currently reserved opening purchase amounts and fees.
When insufficient cash remains, it REDUCES new position
quantity without exceeding existing 0.5% risk per trade;
when no cash remains it SKIPS new entries. No borrowed
stock money and no use of unrealised profits for funding
other positions. All original signals and exit/TP/SL are
unchanged. Compared with the old v8 simulator in uncapped
mode for EXACT same trades/results first, then reruns
unlevered cash-only plus 10bp/side fee stress.

Workflow: https://github.com/DY0617/wyckoff-oos-public/actions/runs/38251062100

## Monthly resampling stress (NOT formal confidence intervals)

We grouped realised PnL by original UTC entry month, inserting
zero-PnL months, then randomly resampled the same number of
months WITH replacement 12,000 times using PRNG seed
20261012. This ignores serial dependence, compounding,
selection bias, open-position spillover and volatility
clustering, so DO NOT label results a reliable probability
of future profit. It is only a mechanical sample-instability
diagnostic.

Approximate 2.5th–97.5th percentile resampled TOTAL PnL:
- Stock compression (~55 months): **-1,544 to +7,413 USD**
- BTC/ETH market regime (~61 months): **-2,427 to +5,740 USDT**
- New-asset market regime (~52 months): **-4,677 to +4,085 USDT**

All intervals contain ZERO. Evidence for reliable stable
growth is insufficient; strategy and universe were already
selected after many prior experiments.

## Immediate research priorities

1. Finish exact cash-backed stock rerun without changing signals.
2. Require 1-minute futures mark/stop and time of fees/funding,
   real spreads, liquidation/margin/risk gross caps before live use.
3. Introduce truly future unseen dates and survivorship-free
   stock universes. Historic 2021–2026 cannot become "fresh OOS"
   simply by changing threshold values.
4. Do NOT promote any of v1–v10 to operational trading or
   increase risk until falsification gates pass.

Existing trading production, Supabase, Telegram and Wyckoff
tracks are untouched.
