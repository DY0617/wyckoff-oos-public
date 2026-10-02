import json
from collections import defaultdict
from pathlib import Path

import backtest_elliott_wave3_v0_crypto as core

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/validation/elliott_wave3_v0_4h_long_plateau.json"

SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT")
PIVOTS = (1.25, 1.50, 1.75, 2.00)
W1_MINS = (1.50, 2.00, 2.50, 3.00)
RETRACE_WINDOWS = (
    (0.300, 0.500),
    (0.350, 0.500),
    (0.382, 0.450),
    (0.382, 0.500),
    (0.382, 0.550),
    (0.382, 0.618),
)

BASELINE = (1.50, 2.00, 0.382, 0.500)


def long_only(ts):
    return [t for t in ts if t["direction"] == "LONG"]


def key(pivot, w1, lo, hi):
    return f"p{pivot:.2f}_w{w1:.2f}_r{lo:.3f}-{hi:.3f}"


def main():
    cache = {}
    for sym in SYMBOLS:
        print("LOAD", sym, flush=True)
        cache[sym] = core.load_15m(sym)

    cells = {}
    for pivot in PIVOTS:
        core.PIVOT_REV_ATR = pivot
        for w1 in W1_MINS:
            core.W1_MIN_ATR = w1
            for lo, hi in RETRACE_WINDOWS:
                core.W2_RET_MIN, core.W2_RET_MAX = lo, hi
                alltr = []
                by_symbol = {}
                for sym in SYMBOLS:
                    ts, st, npiv = core.simulate(sym, cache[sym], 240)
                    lt = long_only(ts)
                    alltr.extend(lt)
                    by_symbol[sym] = {
                        "metrics": core.metrics(lt),
                        "raw_stats": st,
                        "pivots": npiv,
                    }
                k = key(pivot, w1, lo, hi)
                cells[k] = {
                    "params": {
                        "pivot_reversal_atr": pivot,
                        "wave1_min_atr": w1,
                        "retrace_min": lo,
                        "retrace_max": hi,
                    },
                    "metrics": core.metrics(alltr),
                    "symbols": by_symbol,
                }
                m = cells[k]["metrics"]
                print("CELL", k, "n", m["trades"], "avgR", m["avg_r"], "PF", m["profit_factor"], "DD", m["max_drawdown_r"], flush=True)

    bkey = key(*BASELINE)
    baseline = cells[bkey]

    # Neighbourhood diagnostics around the frozen baseline; not an optimizer.
    neighborhood = {}
    for k, v in cells.items():
        p = v["params"]
        if (
            p["pivot_reversal_atr"] in (1.25, 1.50, 1.75)
            and p["wave1_min_atr"] in (1.50, 2.00, 2.50)
            and (p["retrace_min"], p["retrace_max"]) in (
                (0.350, 0.500), (0.382, 0.450), (0.382, 0.500),
                (0.382, 0.550), (0.382, 0.618)
            )
        ):
            neighborhood[k] = v

    robust_positive = []
    for k, v in neighborhood.items():
        m = v["metrics"]
        if (
            m["trades"] >= 80
            and m["avg_r"] is not None and m["avg_r"] > 0
            and m["profit_factor"] is not None and m["profit_factor"] > 1
        ):
            robust_positive.append(k)

    out = {
        "strategy": "Elliott Wave 3 v0 4H LONG plateau",
        "purpose": "Robustness diagnostic around the frozen v0 baseline; not parameter optimization.",
        "symbols": list(SYMBOLS),
        "baseline_key": bkey,
        "baseline": baseline,
        "grid": {
            "pivot_reversal_atr": list(PIVOTS),
            "wave1_min_atr": list(W1_MINS),
            "retrace_windows": [list(x) for x in RETRACE_WINDOWS],
            "cells": len(cells),
        },
        "neighborhood_cells": len(neighborhood),
        "neighborhood_positive_cells": len(robust_positive),
        "neighborhood_positive_fraction": len(robust_positive) / len(neighborhood) if neighborhood else None,
        "robust_positive_keys": robust_positive,
        "cells": cells,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("FINAL", json.dumps({
        "baseline": baseline["metrics"],
        "grid_cells": len(cells),
        "neighborhood_cells": len(neighborhood),
        "positive_cells": len(robust_positive),
        "positive_fraction": out["neighborhood_positive_fraction"],
    }, indent=2), flush=True)


if __name__ == "__main__":
    main()
