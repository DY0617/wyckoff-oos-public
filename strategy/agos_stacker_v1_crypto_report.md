# AGOS-inspired Bounded Stacker v1 — BTC/ETH initial research outcome

Evaluation completed 2026-10-12 on locked pre-result rules.
Source: GH Actions run 38214821516, artifact `agos-stacker-v1-crypto`,
https://github.com/DY0617/wyckoff-oos-public/actions/runs/38214821516
Period: 2021-09-28 to 2026-09-28 EXCLUSIVE. Initial cash: 20,000 USDT.
Two symbols: BTCUSDT and ETHUSDT futures, LONG and SHORT, 1H execution,
4H band signals, maximum two concurrent cycles, full-candle MTM equity.
4bps fee + 2bps slippage on entry/exit fills and historical settlement funding
(using hourly-close proxy).

| Version | closed cycles | win rate | net return on initial cash | max hourly-close MTM DD | PF |
|---|---:|---:|---:|---:|---:|
| single no averaging | 1,014 | 83.43% | -34.75% | 35.39% | 0.647 |
| bounded 4-fill stacker | 1,122 | 89.93% | -26.69% | 27.03% | 0.639 |
| stacker + yesterday EMA200 regime | 508 | 91.34% | -9.54% | 11.20% | 0.707 |

The most selective variant had 44 stop exits and 508 total closed cycles.
Mean profitable cycle +9.926 USDT versus mean losing cycle -148.051 USDT,
so break-even win frequency is ~93.72% rather than the measured 91.34%.

- 2021 +129 USDT (partial)
- 2022 -572 USDT
- 2023 -77 USDT
- 2024 -906 USDT
- 2025 -76 USDT
- 2026 -406 USDT (partial)

Research conclusion: **reject the frozen default as a standalone tradable
strategy**. High realised win frequency alone does not establish positive
expectancy, and realised-only scoreboards can hide floating drawdowns.

This is NOT a measurement of AGOS proprietary code, settings or real-user
portfolio performance; these numerical assumptions were independently set.

Implementation limitations still apply: only hourly close MTM (not intrabar
peak-to-trough), stop-versus-add ambiguity, historical funding based on the
hourly close rather than exact Binance mark, simplified slippage, no forced
liquidation/margin modelling. Follow-up research must freeze a genuinely
different architecture and test unseen periods/symbols without fitting to
these observed losses.
