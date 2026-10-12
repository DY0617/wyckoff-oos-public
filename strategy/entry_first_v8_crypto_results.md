# Entry First v8 — crypto structure-only signal research results

Recorded 2026-10-12 from the successful GitHub Actions
[run 38227833803](https://github.com/DY0617/wyckoff-oos-public/actions/runs/38227833803).
Frozen rules: [entry_first_v8_frozen.md](entry_first_v8_frozen.md).

Independent research. **Not AGOS proprietary strategy / not actual live PnL.**
Initial simulated equity $20,000; no averaging or cycling;
fixed 2R exit, structural stop 0.65..3.5 ATR; planned initial worst
stop incl stressed 10bp/side <=0.5% marked equity per trade, 70%
position notional cap and max 3 concurrent. Fee/slippage 6bp each
fill/side, 10bp stress, historic funding close-mark proxy.
DD from hourly-close marked equity, not intrabar maximum.

## Known BTCUSDT + ETHUSDT, 2021-09-28 to 2026-09-28 (exclusive)

| Signal | Trades | Total return | PF | MTM MDD | Mean net R | Mean MAE R | Mean MFE R | +4bps/side stressed return |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| sweep alone | 1,139 | +20.40% | 1.058 | 19.43% | +0.037 | 0.774 | 1.154 | -8.58% |
| 1H pivot break (CHoCH proxy) | 1,815 | -48.90% | 0.862 | 50.66% | -0.077 | 0.796 | 1.062 | -64.71% |
| breakout retest | 1,658 | -56.07% | 0.830 | 57.03% | -0.113 | 0.808 | 1.065 | -70.25% |
| sweep then CHoCH | 513 | -28.08% | 0.781 | 31.87% | -0.140 | 0.800 | 1.088 | -34.78% |
| sweep then CHoCH then retest | 318 | -11.40% | 0.874 | 17.10% | -0.086 | 0.799 | 1.105 | -16.50% |

## New symbol cohort BNBUSDT + SOLUSDT + XRPUSDT, 2022-06-01
to 2026-09-28 exclusive, BTC benchmark only (not traded).

| Signal | Trades | Total return | PF | MTM MDD | Mean net R | Mean MAE R | Mean MFE R | +4bps/side stressed return |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| sweep alone | 1,414 | -8.95% | 0.977 | 16.52% | -0.011 | 0.793 | 1.126 | -32.52% |
| 1H pivot break | 2,327 | -6.31% | 0.990 | 30.90% | -0.000 | 0.782 | 1.087 | -36.68% |
| breakout retest | 2,260 | -46.96% | 0.888 | 57.91% | -0.058 | 0.793 | 1.080 | -65.92% |
| sweep then CHoCH | 655 | -2.00% | 0.989 | 19.30% | -0.001 | 0.779 | 1.078 | -12.05% |
| sweep then CHoCH then retest | 443 | -13.55% | 0.887 | 19.81% | -0.066 | 0.788 | 1.050 | -19.41% |

**Interpretation: no portable positive expected R found.**
The best-looking BTC/ETH sweep result fails an out-of-instrument
test and fails execution cost stress; 2R target hit rate was
~35.2% BTC/ETH vs ~33.2% new coins. Most entries exhibit
~0.8R average adverse excursion, and median observed MAE
was 1R on known BTC/ETH: stopouts dominate. Merely adding
structural breakout and retest filters does not fix this.

These are **heuristic proxies** for discretionary market structure,
not guarantees that all truly have liquidity grabs or institutional
change of character. Entry First v8 signals often overtrade.
This result is evidence against taking this implementation live,
not evidence that every conceivable sweep or retest rule must fail.

Technical caveats: hourly OHLC path ambiguity, no order-book
or dynamically stressed fills, gap losses beyond budget, historical
funding proxy, same historical dates already researched in prior
releases; alt instruments were already introduced in v7 and therefore
are not novel blind markets anymore. No prospective/OOS validation.
No real exchange or production changes were made.
