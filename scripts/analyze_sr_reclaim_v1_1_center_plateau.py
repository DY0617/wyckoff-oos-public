import json
from collections import defaultdict
from pathlib import Path

import backtest_sr_reclaim_v1_1_retest as rt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/validation/sr_reclaim_v1_1_center_plateau.json"

CONFIGS = [
    ("baseline_r2_valid3", 2.00, 3),
    ("target_r1_75", 1.75, 3),
    ("target_r1_50", 1.50, 3),
    ("target_r1_25", 1.25, 3),
    ("valid6", 2.00, 6),
    ("valid12", 2.00, 12),
]


def aggregate_stats(details):
    o = defaultdict(float)
    for d in details.values():
        for k, v in d["stats"].items():
            if isinstance(v, (int, float)) and k != "fill_rate":
                o[k] += v
    return dict(o)


def main():
    cache = {sym: rt.sr.core.load_15m(sym) for sym in rt.sr.SYMBOLS}
    candidates = {}
    candidate_stats = {}
    for sym, b15 in cache.items():
        cs, st = rt.find_candidates(b15)
        candidates[sym] = cs
        candidate_stats[sym] = st

    results = []
    for name, min_r, valid_bars in CONFIGS:
        rt.MIN_TARGET_R = min_r
        rt.ENTRY_VALID_BARS = valid_bars
        alltr = []
        details = {}
        for sym, b15 in cache.items():
            ts, st = rt.simulate_variant(sym, b15, candidates[sym], "zone_center")
            alltr += ts
            details[sym] = {"metrics": rt.sr.core.metrics(ts), "stats": st}
        result = {
            "name": name,
            "min_target_r": min_r,
            "entry_valid_4h_bars": valid_bars,
            "summary": rt.sr.core.metrics(alltr),
            "directions": rt.grouped_metrics(alltr, "direction"),
            "symbols": rt.grouped_metrics(alltr, "symbol"),
            "stats": aggregate_stats(details),
            "details": details,
        }
        results.append(result)
        print("RESULT", name, json.dumps({"summary": result["summary"], "stats": result["stats"]}), flush=True)

    out = {
        "strategy": "SR Reclaim v1.1 zone-center single-axis plateau",
        "candidate_stats": candidate_stats,
        "configs": results,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("FINAL", json.dumps([
        {"name": r["name"], "summary": r["summary"], "stats": r["stats"]} for r in results
    ], indent=2), flush=True)


if __name__ == "__main__":
    main()
