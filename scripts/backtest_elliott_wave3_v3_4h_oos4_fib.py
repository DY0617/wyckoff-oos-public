import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import backtest_elliott_wave3_v0_crypto as core
import backtest_elliott_wave3_v3_bbreak as v3

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc
OUT = ROOT / "data/validation/elliott_wave3_v3_4h_oos4_fib_fixed.json"

SYMBOLS = ("AVAXUSDT", "ATOMUSDT", "NEARUSDT", "FILUSDT")
TF = 240

CONFIGS = {
    "BASELINE": lambda s: True,
    "W2_0382_0500": lambda s: 0.382 <= s["wave2_retracement"] < 0.500,
    "CA_0618_1000": lambda s: 0.618 <= s["abc_c_to_a"] < 1.000,
    "BOTH": lambda s: (
        0.382 <= s["wave2_retracement"] < 0.500
        and 0.618 <= s["abc_c_to_a"] < 1.000
    ),
}


def group_metrics(trades, key):
    g = defaultdict(list)
    for t in trades:
        g[t[key]].append(t)
    return {k: core.metrics(v) for k, v in sorted(g.items())}


def run_filtered(sym, b15, predicate):
    original = v3.make_v3_signal

    def filtered(d, win):
        sig = original(d, win)
        if sig is None or not predicate(sig):
            return None
        return sig

    v3.make_v3_signal = filtered
    try:
        return v3.simulate(sym, b15, TF)
    finally:
        v3.make_v3_signal = original


def main():
    cache = {}
    for sym in SYMBOLS:
        print("LOAD", sym, flush=True)
        cache[sym] = core.load_15m(sym)

    configs_out = {}

    for name, predicate in CONFIGS.items():
        alltr = []
        cells = {}
        for sym in SYMBOLS:
            ts, st, npiv = run_filtered(sym, cache[sym], predicate)
            cells[sym] = {"metrics": core.metrics(ts), "stats": st, "pivots": npiv}
            alltr += ts
            print("RESULT", name, sym, json.dumps(cells[sym]), flush=True)

        years = defaultdict(list)
        for t in alltr:
            years[str(datetime.fromtimestamp(t["entry_t"] / 1000, UTC).year)].append(t)

        configs_out[name] = {
            "metrics": core.metrics(alltr),
            "directions": group_metrics(alltr, "direction"),
            "symbols": group_metrics(alltr, "symbol"),
            "years": {k: core.metrics(v) for k, v in sorted(years.items())},
            "cells": cells,
            "trades": alltr,
        }

    out = {
        "strategy": "Elliott Wave 3 v3 4H OOS4 fixed Fibonacci candidates",
        "purpose": (
            "Fresh unseen-symbol holdout. Candidate filters were frozen after the DEV/OOS1/OOS2/OOS3 "
            "diagnostic and before OOS4 was read. No tuning on OOS4."
        ),
        "symbols": list(SYMBOLS),
        "timeframe": "4H",
        "configs": configs_out,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")

    print("FINAL", json.dumps({
        k: v["metrics"] for k, v in configs_out.items()
    }, indent=2), flush=True)


if __name__ == "__main__":
    main()
