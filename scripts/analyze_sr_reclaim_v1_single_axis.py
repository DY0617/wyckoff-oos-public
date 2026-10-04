import json
from collections import defaultdict
from pathlib import Path

import backtest_sr_reclaim_v1_crypto as sr

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/validation/sr_reclaim_v1_single_axis_diagnostics.json"

BASE = {
    "MIN_TARGET_R": 2.00,
    "MIN_RISK_ATR": 0.35,
    "MAX_RISK_ATR": 2.00,
}

CONFIGS = [
    ("baseline", {}),
    ("target_r_1_75", {"MIN_TARGET_R": 1.75}),
    ("target_r_1_50", {"MIN_TARGET_R": 1.50}),
    ("target_r_1_25", {"MIN_TARGET_R": 1.25}),
    ("max_risk_atr_2_50", {"MAX_RISK_ATR": 2.50}),
    ("max_risk_atr_3_00", {"MAX_RISK_ATR": 3.00}),
    ("min_risk_atr_0_20", {"MIN_RISK_ATR": 0.20}),
]


def aggregate_stats(per_symbol):
    out = defaultdict(float)
    for x in per_symbol.values():
        for k, v in x["stats"].items():
            if isinstance(v, (int, float)) and k != "fill_rate":
                out[k] += v
    return dict(out)


def run_one(name, changes, cache):
    for k, v in BASE.items():
        setattr(sr, k, v)
    for k, v in changes.items():
        setattr(sr, k, v)

    alltr = []
    per_symbol = {}
    for sym, b15 in cache.items():
        ts, st = sr.execute(sym, b15)
        alltr += ts
        per_symbol[sym] = {"metrics": sr.core.metrics(ts), "stats": st}

    result = {
        "name": name,
        "changes": changes,
        "effective": {
            "MIN_TARGET_R": sr.MIN_TARGET_R,
            "MIN_RISK_ATR": sr.MIN_RISK_ATR,
            "MAX_RISK_ATR": sr.MAX_RISK_ATR,
        },
        "summary": sr.core.metrics(alltr),
        "stats": aggregate_stats(per_symbol),
        "symbols": per_symbol,
    }
    print("RESULT", name, json.dumps({"summary": result["summary"], "stats": result["stats"]}), flush=True)
    return result


def main():
    cache = {sym: sr.core.load_15m(sym) for sym in sr.SYMBOLS}
    results = [run_one(name, changes, cache) for name, changes in CONFIGS]

    out = {
        "strategy": "SR Reclaim v1 single-axis diagnostics",
        "baseline": BASE,
        "configs": results,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("FINAL", json.dumps([
        {"name": x["name"], "summary": x["summary"], "stats": x["stats"]} for x in results
    ], indent=2), flush=True)


if __name__ == "__main__":
    main()
