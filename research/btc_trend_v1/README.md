# BTC trend independent research

Research only. No live execution, service credentials, Telegram or database writes.

See `PROTOCOL.md`, `BASELINE_SPEC.md`, `ENTRY_SPEC_V1.md`, and `reports/PHASE_2_REVIEW.md`. Results were actually executed locally. The selected entry-candidate retrospective holdout is still locked in code at 2025-01-01.

## Reproduce
Python 3.12; `pip install -r requirements.txt`. Paths below are relative to this directory.

```bash
python scripts/audit_data.py
python scripts/collect_mark_price.py
python scripts/collect_execution_1h.py
python scripts/inspect_execution_anomalies.py
python scripts/build_canonical_execution.py
python scripts/baseline.py
python scripts/entries_v1.py
python scripts/verify_execution_1h.py
python scripts/entry_robustness.py
python scripts/compare_entry_risk.py
python scripts/test_causal_engine.py
```

Official original archives remain in `raw/`; committed manifests record URLs and checksums. Raw ZIP files are reproducible downloads and are not committed. The pinned original repository spot-daily snapshot is committed. Canonical 4H execution data are rebuilt from original monthly archives plus the explicitly documented daily correction. Do not silently skip any failed archive or change thresholds to recover a desired result.

`baseline.py` describes past benchmark periods including 2025–2026. `entries_v1.py` and `verify_execution_1h.py` refuse candidate performance periods after 2024. Baseline exposure-risk matching uses train-only volatility estimates; future realized risk is not forced equal. Fees and slippage are assumptions; funding rates are observed but funding mark valuation uses a boundary proxy.

`research_workflow.yml` is an unactivated GitHub Actions workflow source: manual, research-only, with read-only repository permissions and artifact upload. It is preserved inside the research directory for review; it is not installed under `.github/workflows`. No merge into main or production workflow modification is performed.
