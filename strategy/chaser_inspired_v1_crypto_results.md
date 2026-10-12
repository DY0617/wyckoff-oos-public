# Chaser-inspired v1 — completed BTC/ETH 5-year results (research)

Recorded 2026-10-12 from GitHub Actions run
https://github.com/DY0617/wyckoff-oos-public/actions/runs/38216072720
(frozen code from commit ae190bbd70199d112aea9c980577a299833bfc9a).

These results are from an ORIGINAL, hypothetical trend-breakout system.
They are NOT official AGOS Chaser settings or reported AGOS performance.

Market: Binance USDT-M BTCUSDT + ETHUSDT, 2021-09-28 through
2026-09-28 exclusive, 1H signal and fill, completed daily /4H filters.
Account: initial 20,000 USDT; max 0.5% planned risk per trade and three
simultaneous positions. Fees 4bp + slippage 2bp per entry/exit,
historical funding with 1H-close notional approximation.
DD is 1H-close mark-to-market, not an intrabar worst-tick bound.

| Variant | Trades | Profit factor | Net return | Max 1H-close MTM DD | Extra 4bp/side stress net return |
|---|---:|---:|---:|---:|---:|
| A: raw breakout | 2,188 | 0.9310 | -36.56% | 45.23% | -64.10% |
| B: aligned daily +4H trend | 566 | 0.8217 | -26.49% | 35.42% | -36.17% |
| C: B + consolidation/expansion | 496 | 0.8352 | -21.96% | 32.78% | -31.19% |

C by underlying: BTC -2,043.02 USDT; ETH -2,349.00 USDT.
C fees/slippage: 2,995.48 USDT, historical funding cost 391.85 USDT.
C annual realised PnL attributed to entry year: 2021 partial -321.95;
2022 -3233.01; 2023 -1651.75; 2024 -327.45; 2025 +213.43;
2026 partial +928.70. 2024+ combined +814.68 USDT but pre-2024
-5,206.70 USDT. These are NOT independent untouched OOS data after
seeing full-window performance.

**Decision for crypto: reject.** All variants are unprofitable on
the selected historical evaluation data and particularly fragile under
increased transaction cost. Do NOT optimize thresholds to rescue the
same dates; lock failures and only test a distinctly pre-registered
market hypothesis on genuinely unseen markets/times.

Limitations: sample has two crypto symbols; price-bar ambiguity and
funding mark approximation; no trading venue liquidation, mark price,
spread depth, exchange outage, partial fills or taxes. Historical
performance is no guarantee of future results. Existing production
strategy, keys, signals and trading pathways have not been modified.
