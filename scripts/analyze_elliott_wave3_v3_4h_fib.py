import json
from collections import defaultdict
from pathlib import Path

import backtest_elliott_wave3_v0_crypto as core

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/validation/elliott_wave3_v3_4h_fib_diagnostic.json"

INPUTS = {
    "DEV": ROOT / "data/validation/elliott_wave3_v3_bbreak_dev.json",
    "OOS1": ROOT / "data/validation/elliott_wave3_v3_bbreak_oos1.json",
    "OOS2": ROOT / "data/validation/elliott_wave3_v3_bbreak_oos2.json",
    "OOS3": ROOT / "data/validation/elliott_wave3_v3_bbreak_oos3_4h.json",
}

W2_BUCKETS = (
    ("0.382-0.500", 0.382, 0.500),
    ("0.500-0.618", 0.500, 0.618),
    ("0.618-0.786", 0.618, 0.786001),
)

B_BUCKETS = (
    ("0.236-0.382", 0.236, 0.382),
    ("0.382-0.500", 0.382, 0.500),
    ("0.500-0.618", 0.500, 0.618),
    ("0.618-0.786", 0.618, 0.786),
    ("0.786-0.886", 0.786, 0.886001),
)

CA_BUCKETS = (
    ("0.618-1.000", 0.618, 1.000),
    ("1.000-1.272", 1.000, 1.272),
    ("1.272-1.618", 1.272, 1.618001),
)


def bucket_name(x, buckets):
    if x is None:
        return None
    for name, lo, hi in buckets:
        if lo <= x < hi:
            return name
    return "OTHER"


def summarize_bucketed(grouped):
    out = {}
    for bucket, trades in sorted(grouped.items()):
        by_group = defaultdict(list)
        for t in trades:
            by_group[t["_group"]].append(t)
        gm = {g: core.metrics(xs) for g, xs in sorted(by_group.items())}
        positive_groups = sum(
            m["trades"] > 0 and m["avg_r"] is not None and m["avg_r"] > 0
            for m in gm.values()
        )
        pf_gt1_groups = sum(
            m["trades"] > 0 and m["profit_factor"] is not None and m["profit_factor"] > 1
            for m in gm.values()
        )
        out[bucket] = {
            "metrics": core.metrics(trades),
            "groups": gm,
            "positive_groups": positive_groups,
            "pf_gt1_groups": pf_gt1_groups,
            "groups_with_trades": len(gm),
        }
    return out


def main():
    alltr = []
    group_metrics = {}

    for group, path in INPUTS.items():
        obj = json.loads(path.read_text(encoding="utf-8"))
        trades = obj.get("trades", [])
        # OOS3 is already 4H only; older groups contain 1H + 4H.
        trades = [dict(t) for t in trades if t.get("timeframe") == "4H"]
        for t in trades:
            t["_group"] = group
        alltr += trades
        group_metrics[group] = core.metrics(trades)

    w2 = defaultdict(list)
    b = defaultdict(list)
    ca = defaultdict(list)
    combo = defaultdict(list)

    for t in alltr:
        bw2 = bucket_name(t.get("wave2_retracement"), W2_BUCKETS)
        bb = bucket_name(t.get("abc_b_retracement"), B_BUCKETS)
        bc = bucket_name(t.get("abc_c_to_a"), CA_BUCKETS)
        w2[bw2].append(t)
        b[bb].append(t)
        ca[bc].append(t)
        combo[f"W2:{bw2}|B:{bb}|CA:{bc}"].append(t)

    combo_out = summarize_bucketed(combo)
    combo_out = {
        k: v for k, v in combo_out.items()
        if v["metrics"]["trades"] >= 3
    }

    out = {
        "strategy": "Elliott Wave 3 v3 4H Fibonacci diagnostic",
        "purpose": (
            "Post-hoc descriptive analysis only. This does not validate or optimize a tradable filter. "
            "Any candidate bucket found here requires a fresh unseen holdout."
        ),
        "groups": group_metrics,
        "all_4h": core.metrics(alltr),
        "wave2_retracement": summarize_bucketed(w2),
        "abc_b_retracement": summarize_bucketed(b),
        "abc_c_to_a": summarize_bucketed(ca),
        "three_way_combinations_min3": combo_out,
        "trades": alltr,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")

    print("FINAL", json.dumps({
        "groups": group_metrics,
        "all_4h": out["all_4h"],
        "wave2": {k:v["metrics"] for k,v in out["wave2_retracement"].items()},
        "b": {k:v["metrics"] for k,v in out["abc_b_retracement"].items()},
        "ca": {k:v["metrics"] for k,v in out["abc_c_to_a"].items()},
    }, indent=2), flush=True)


if __name__ == "__main__":
    main()
