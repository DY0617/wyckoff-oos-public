# Entry First v9 — paired crypto results and adverse fill-selection

Pre-frozen strategy definitions:
[strategy/entry_execution_v9_frozen.md](entry_execution_v9_frozen.md)
GitHub Actions run:
https://github.com/DY0617/wyckoff-oos-public/actions/runs/38232291484

All results are hypothetical historical, non-live, and use an
independently coded liquidity-sweep proxy rather than proprietary
AGOS methods. Existing production trading pipelines unchanged.

Common initial capital 20,000 USDT; 0.5% maximum planned
stop risk including stressed estimated fees; <=70% notional
per position; <=3 active+reserved positions; hard initial
structural stop and +2R full exit; Binance historical funding
proxy and 6bps nominal / 10bps stress per fill side.
MDD sampled at 1H closes.

## BTC+ETH known development sample, Sep 2021—Sep 2026

| Arm | Closed trades | Filled / submitted limits | Net return | PF | MDD | Cost stress +4bps/side |
|---|---:|---:|---:|---:|---:|---:|
| market | 1139 | n/a | +20.40% | 1.058 | 19.43% | -8.58% |
| market_shock (4H signal spread<=2.25ATR) | 1140 | n/a | +30.08% | 1.082 | 18.35% | -1.56% |
| limit_half | 991 | 991/1338 (74.1%) | -13.48% | 0.950 | 22.77% | -35.55% |
| limit_reclaim | 856 | 856/1440 (59.4%) | -33.19% | 0.839 | 36.01% | -50.49% |
| limit_deep | 804 | 804/1721 (46.7%) | -34.63% | 0.815 | 37.79% | -53.97% |
| limit_half_shock | 973 | 973/1318 (73.8%) | +3.26% | 1.012 | 14.62% | -23.42% |
| limit_reclaim_shock | 839 | 839/1357 (61.8%) | -29.99% | 0.855 | 32.27% | -48.05% |
| limit_half_2h | 777 | 777/1442 (53.9%) | -27.13% | 0.863 | 32.08% | -42.22% |

`market` output matches prior v8 BTC/ETH baseline EXACTLY
(including trade count, return, PF, MDD), validating the common
market comparison engine.

## BNB+SOL+XRP new instrument sample, Jun 2022—Sep 2026

BTC was not traded in this separate 20k account.

| Arm | Closed trades | Net return | PF | MDD | Cost stress +4bps/side |
|---|---:|---:|---:|---:|---:|
| market | 1414 | -8.95% | 0.977 | 16.52% | -32.52% |
| market_shock | 1413 | -5.86% | 0.985 | 15.91% | -30.37% |
| limit_half | 1224 | -2.04% | 0.994 | 21.10% | -29.64% |
| limit_reclaim | 1043 | -21.44% | 0.924 | 26.55% | -43.01% |
| limit_deep | 1017 | -35.35% | 0.855 | 39.13% | -56.74% |
| limit_half_shock | 1215 | -1.80% | 0.995 | 19.28% | -29.71% |
| limit_reclaim_shock | 1035 | -22.79% | 0.919 | 26.47% | -44.03% |
| limit_half_2h | 956 | -12.94% | 0.949 | 22.14% | -32.85% |

## Interpretation

- Buying nearer a support/extreme after a confirmed sweep does
  NOT automatically create a higher-quality entry. Deeper
  retracements are often adverse selection (a setup failing,
  not simply a bargain) at least in these bar-simulation samples.
- Fixed 8-bar `limit_half` filled 74.1% of orders on BTC/ETH,
  but those 991 filled cycles were unprofitable. The filling
  mechanism itself was not a robust expected-value improvement.
- Dynamic market shock skip improved nominal known-crypto
  results but still failed 10bps/side cost stress. New
  alt instruments still lose money; this does not generalize.
- Alt `limit_half` moved closer to breakeven but still lost
  and had higher drawdown than the market baseline. Every
  alt execution policy failed high-cost stress badly.
- No extra risk/leverage added to chase headline return.
- Price touching a limit in a 1H candle is assumed a complete
  fill (optimistic market queue, even though STOP first if
  that same hour also touches the stop). This assumption
  requires much better execution validation before ANY live use.
- Historical dates are heavily explored; these are not untouched OOS.
  Even positive nominal outcomes should be treated as hypotheses
  rather than expected future rates.

Crypto conclusion: **no production-ready entry execution edge**.
Wait for stock cohort results; don't call one-market success
a portable trading strategy.
