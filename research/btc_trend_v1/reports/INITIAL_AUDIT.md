# BTC independent research: initial data audit

Executed 2026-10-13. Study cutoff: 2026-10-01 exclusive UTC.

## Actual results

475 monthly archive requests: 463 ZIPs verified against official SHA256 checksums; 12 unavailable files returned HTTP 404 (USD-M September–December 2019, across daily, 4H and funding). No historical strategy performance has been evaluated.

| Dataset | Available start | End | Rows | Finding |
|---|---|---|---:|---|
| Spot daily | 2017-08-17 | 2026-09-30 | 3,332 | No duplicates, missing daily slots or invalid OHLC/close times |
| Spot 4H | 2017-08-17 04:00 UTC | 2026-09-30 20:00 UTC | 19,974 | 9 gaps / 17 absent slots; 19 bars fail strict candle conditions |
| USD-M daily | 2020-01-01 | 2026-09-30 | 2,465 | Basic candle checks pass in available range; requested 2019 archive months absent |
| USD-M 4H | 2020-01-01 | 2026-09-30 | 14,790 | Basic candle checks pass in available range; requested 2019 archive months absent |
| USD-M funding | 2020-01-01 | 2026-09-30 | 7,395 | No duplicates or missing nominal 8H settlement slots; timestamps are 0–47ms after nominal slot |

Spot: 3,321 complete days match aggregated 4H OHLCV within numerical tolerance. Eleven days are incomplete (including first listing day). USD-M: all 2,465 daily OHLC prices match 4H aggregation. Volume differs on 2023-08-16 and 2023-11-10. Cause is unknown. Checksums establish byte integrity, not market-data correctness.

Pinned private-repository daily snapshot has 1,825 rows from 2021-10-14 to 2026-10-12. Only 1,813 are within the study cutoff, and these pass basic daily validation. In their overlap with official monthly archives, prices agree; volume differs on 2021-12-24 and 2021-12-27. Preserve both versions and do not silently merge them.

Funding CSV schema was inspected in originals: calc_time, funding_interval_hours, last_funding_rate. Use the third field for the rate. Preserve actual milliseconds for position-at-settlement accounting. Do not interpret subsecond settlement delays as missing 8H payments.

## Decision and next gate

Data gate is CONDITIONAL, not an unconditional full-history pass. Price-only research is feasible on the continuous 2020–2026 USD-M range. Futures performance before 2020 is unavailable in the acquired archives and cannot be inferred from spot. Do not use spot 4H gaps as if continuous bars existed. Volume-dependent candidates require a pinned-source decision and discrepancy sensitivity checks before evaluation.

Next: resolve/record anomaly policy; independently reproduce daily SMA200 + 90-bar momentum with explicit next-open execution; define a volatility target for the risk-scaled baseline; then implement frozen A/B/C/D candidates. Original +280.5% return remains unverified. The old daily source/time endpoints and volatility-adjustment formula were not located in default-branch file search, which is not proof that no such code exists elsewhere.

Historical periods previously inspected are retrospective holdouts, not provably untouched OOS. True untouched performance must come from future data after rule freezing. No strategy is approved for live use at this stage.

## Evidence
- reports/data_audit.json: per-archive URL, checksum/status, cadence and candle failures.
- reports/crosscheck.json: timeframe aggregation and source mismatch details.
- scripts/audit_data.py and scripts/crosscheck.py: actual executed stdlib-only checks.
- Official archive documentation: https://github.com/binance/binance-public-data (spot microseconds from January 2025; companion SHA256 checksums; archives may be corrected later).
- Research branch: https://github.com/DY0617/wyckoff-oos-public/tree/research/btc-trend-independent-v1/research/btc_trend_v1

No real orders, operational DB updates, Telegram deployments or operational workflow execution were performed.
