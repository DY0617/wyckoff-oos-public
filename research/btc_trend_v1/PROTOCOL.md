# BTC trend research v1 — data gate, 2026-10-13

## Scope and provenance
- Research repository: DY0617/wyckoff-oos-public.
- Branch: research/btc-trend-independent-v1; base c556457292d87e3784c467071c30cb95c47772de.
- Private data repository snapshot: 898f7491cb64349c97888e34cf7487a6c5dbaa65.
- No live orders, operational workflows, database changes, Telegram, or exchange credentials.
- Study endpoint: 2026-09-30 inclusive UTC. October data are excluded.
- Original +166.2%, +280.5%, +125.6% returns are user-supplied exploratory claims, not independently reproduced results. Exact source, date endpoints, volatility target and execution rules remain unverified.

## Data gate
Download official monthly BTCUSDT spot daily/4H from listing and USD-M daily/4H/funding archives from September 2019. Store original ZIP SHA256 and URL. A missing file is a failure, never an empty successful month. Normalize archive microseconds to milliseconds; retain originals. Check duplicates, ordering, cadence, OHLC positivity and bounds, volume, close timestamp and study endpoint. Inspect exchange downtime gaps explicitly before any simulation. Cross-check 4H aggregate OHLCV against daily bars. Futures prices must drive futures fills; spot cannot stand in for futures. Funding must use actual settlement rates and contemporaneous position notional, including changes after partial exits. Missing funding blocks a fully costed futures result.

## Frozen evaluation design (proposal before strategy coding)
- Warmup: spot listing onward; futures trading begins only when real futures archives exist.
- Train: first eligible futures bar through 2022-12-31.
- Validation: 2023-01-01 through 2024-12-31.
- Retrospective holdout: 2025-01-01 through 2026-09-30. Do not inspect strategy performance until candidate selection is frozen.
- This historical period has prior exposure in earlier projects. It is not provably untouched OOS. True forward OOS starts after rules/code/configuration are frozen and uses only subsequently arriving bars.
- Data-quality inspection across all periods is allowed; no strategy returns on holdout before freezing.
- Daily filter: last fully closed UTC daily close > trailing SMA200 and > close 90 daily bars earlier. Attach daily signal only at its availability time, never at that day's open.
- 4H signal decisions use closed bars; first permitted market execution is next bar open plus adverse slippage. Confirmed pivots require their right-hand bars to close.
- Intrabar stop/target ambiguity: stop first initially; obtain 1H or finer execution data to assess sensitivity. Gap stops fill at adverse open. No fills inferred solely from a future bar's high/low.
- One BTC position; no pyramiding initially. Long only; 0.5% equity risk primary, 1% sensitivity. Initial notional cap 1x equity; reject size when costs exhaust risk budget.
- Fee/slippage values must be labelled assumptions until historical fee schedule and account tier are specified. Stress costs at least 2x. Never assume historical tick/step filters equal current filters.
- Compare all A/B/C/D entries under one primary exit rule before exit variants. No unbounded parameter search. Record all attempted configurations, including failures.
- Primary selection: positive validation expectancy after costs, acceptable drawdown, sufficient trades and parameter-neighborhood stability. Few trades imply inconclusive evidence.
- Report mark-to-market daily equity, CAGR, MDD, Sharpe (365-day annualization), PF, expectancy in net R, exposure, trades, annual results, block-bootstrap uncertainty and sensitivity to costs. Compare benchmark volatility using train-estimated scaling, not OOS-fitted risk scaling.

## Existing code review
The main Track B engine uses fixed reference risk and its default run states zero fee/slippage. It is not a directly comparable compounding-equity BTC trend benchmark. The funding-only analyzer approximates funding from entry notional and applies it after trade simulation; this does not fully model partial position sizes, contemporaneous marks or equity-dependent sizing. Reuse acquisition patterns only until temporal execution logic is independently audited.

## Run current data gate
`python research/btc_trend_v1/scripts/audit_data.py`

Current stage: data acquisition and audit. No A/B/C/D performance claim or live-use approval yet.
