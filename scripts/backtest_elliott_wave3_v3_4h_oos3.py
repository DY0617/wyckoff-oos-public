import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import backtest_elliott_wave3_v0_crypto as core
import backtest_elliott_wave3_v3_bbreak as v3

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc
OUT = ROOT / "data/validation/elliott_wave3_v3_bbreak_oos3_4h.json"

SYMBOLS = ("TRXUSDT", "XLMUSDT", "UNIUSDT", "AAVEUSDT")
TF = 240


def group_metrics(trades, key):
    g = defaultdict(list)
    for t in trades:
        g[t[key]].append(t)
    return {k: core.metrics(v) for k, v in sorted(g.items())}


def main():
    alltr = []
    cells = {}

    for sym in SYMBOLS:
        print("LOAD", sym, flush=True)
        b15 = core.load_15m(sym)
        ts, st, npiv = v3.simulate(sym, b15, TF)
        cells[sym] = {"metrics": core.metrics(ts), "stats": st, "pivots": npiv}
        alltr += ts
        print("RESULT", sym, json.dumps(cells[sym]), flush=True)

    years = defaultdict(list)
    for t in alltr:
        years[str(datetime.fromtimestamp(t["entry_t"] / 1000, UTC).year)].append(t)

    out = {
        "strategy": "Elliott Wave 3 v3 B-wave breakout 4H OOS3 frozen",
        "purpose": "Fresh unseen-symbol holdout of the post-hoc observed 4H-only v3 behavior. Exact v3 rules; no tuning.",
        "symbols": list(SYMBOLS),
        "timeframe": "4H",
        "summary": core.metrics(alltr),
        "directions": group_metrics(alltr, "direction"),
        "symbols_metrics": group_metrics(alltr, "symbol"),
        "years": {k: core.metrics(v) for k, v in sorted(years.items())},
        "symbol_cells": cells,
        "trades": alltr,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("FINAL", json.dumps({k: v for k, v in out.items() if k != "trades"}, indent=2), flush=True)


if __name__ == "__main__":
    main()
