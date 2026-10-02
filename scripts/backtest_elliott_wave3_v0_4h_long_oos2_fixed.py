import json
from pathlib import Path

import backtest_elliott_wave3_v0_crypto as core

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/validation/elliott_wave3_v0_4h_long_oos2_fixed.json"

SYMBOLS = ("LTCUSDT", "BCHUSDT", "ETCUSDT", "DOTUSDT")
CONFIGS = {
    "A_ORIGINAL_BASELINE": {
        "pivot": 1.50, "w1": 2.00, "rlo": 0.382, "rhi": 0.500
    },
    "B_CROSSSET_ROBUST_REGION": {
        "pivot": 2.00, "w1": 2.00, "rlo": 0.382, "rhi": 0.450
    },
}


def main():
    cache = {}
    for sym in SYMBOLS:
        print("LOAD", sym, flush=True)
        cache[sym] = core.load_15m(sym)

    out_configs = {}
    for name, p in CONFIGS.items():
        core.PIVOT_REV_ATR = p["pivot"]
        core.W1_MIN_ATR = p["w1"]
        core.W2_RET_MIN = p["rlo"]
        core.W2_RET_MAX = p["rhi"]
        alltr = []
        syms = {}
        for sym in SYMBOLS:
            ts, st, npiv = core.simulate(sym, cache[sym], 240, direction_filter="LONG")
            syms[sym] = {"metrics": core.metrics(ts), "stats": st, "pivots": npiv}
            alltr += ts
        out_configs[name] = {
            "params": p,
            "metrics": core.metrics(alltr),
            "symbols": syms,
        }
        print("CONFIG", name, json.dumps(out_configs[name]["metrics"]), flush=True)

    out = {
        "strategy": "Elliott Wave 3 v0 4H LONG OOS2 fixed configs",
        "purpose": (
            "Second unseen-symbol holdout. Config A is the original baseline. "
            "Config B was selected only after development + OOS1 diagnostics and is tested here without further tuning."
        ),
        "symbols": list(SYMBOLS),
        "configs": out_configs,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("FINAL", json.dumps({k: v["metrics"] for k, v in out_configs.items()}, indent=2), flush=True)


if __name__ == "__main__":
    main()
