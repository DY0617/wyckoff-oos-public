import json
from collections import defaultdict
from pathlib import Path

import backtest_sr_reclaim_v1_1_retest as rt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/validation/sr_reclaim_v1_1_unseen8_oos.json"

# Reuse the repository's previously frozen unseen-8 crypto universe.
SYMBOLS = ("LTCUSDT", "BCHUSDT", "ETCUSDT", "TRXUSDT", "XLMUSDT", "DOTUSDT", "FILUSDT", "UNIUSDT")
CONFIGS = [
    ("valid6_r2", 6, 2.0),
    ("valid12_r2", 12, 2.0),
]


def aggregate_stats(details):
    out = defaultdict(float)
    for d in details.values():
        for k, v in d["stats"].items():
            if isinstance(v, (int, float)) and k != "fill_rate":
                out[k] += v
    return dict(out)


def main():
    cache = {}
    candidates = {}
    candidate_stats = {}

    for sym in SYMBOLS:
        b15 = rt.sr.core.load_15m(sym)
        cache[sym] = b15
        cs, st = rt.find_candidates(b15)
        candidates[sym] = cs
        candidate_stats[sym] = st
        print("CANDIDATES", sym, len(cs), json.dumps(st), flush=True)

    results = []
    for name, valid_bars, min_r in CONFIGS:
        rt.ENTRY_VALID_BARS = valid_bars
        rt.MIN_TARGET_R = min_r
        alltr = []
        details = {}

        for sym in SYMBOLS:
            ts, st = rt.simulate_variant(sym, cache[sym], candidates[sym], "zone_center")
            alltr += ts
            details[sym] = {"metrics": rt.sr.core.metrics(ts), "stats": st}

        result = {
            "name": name,
            "entry_valid_4h_bars": valid_bars,
            "min_target_r": min_r,
            "summary": rt.sr.core.metrics(alltr),
            "directions": rt.grouped_metrics(alltr, "direction"),
            "symbols": rt.grouped_metrics(alltr, "symbol"),
            "stats": aggregate_stats(details),
            "details": details,
        }
        results.append(result)
        print("RESULT", name, json.dumps({"summary": result["summary"], "stats": result["stats"]}), flush=True)

    out = {
        "strategy": "SR Reclaim v1.1 zone-center unseen8 symbol OOS",
        "selection_history": "valid6 and valid12 selected on BTC/ETH/BNB/SOL research universe before this run",
        "symbols": list(SYMBOLS),
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
