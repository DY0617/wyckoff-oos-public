import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import backtest_trend_structure_v0_1_crypto as core
from trend_structure_v0_2_engine import CONFIGS, metrics, run_symbol

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/validation/trend_structure_v0_2_crypto8_5y.json"
UTC = timezone.utc

SYMBOLS = (
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT",
    "XRPUSDT", "ADAUSDT", "DOGEUSDT", "LINKUSDT",
)


def grouped_metrics(trades, key):
    d = defaultdict(list)
    for t in trades:
        d[str(t[key])].append(t)
    return {k: metrics(v) for k, v in sorted(d.items())}


def year_metrics(trades):
    d = defaultdict(list)
    for t in trades:
        y = str(datetime.fromtimestamp(t["entry_t"] / 1000, UTC).year)
        d[y].append(t)
    return {k: metrics(v) for k, v in sorted(d.items())}


def main():
    data = {}
    for sym in SYMBOLS:
        b15 = core.load_15m(sym)
        data[sym] = b15
        print("DATA_READY", sym, len(b15), flush=True)

    variants = {}
    for cfg_name, cfg in CONFIGS.items():
        alltr = []
        symbols = {}
        for sym in SYMBOLS:
            ts, st = run_symbol(sym, data[sym], cfg_name)
            symbols[sym] = {"metrics": metrics(ts), "stats": st}
            alltr += ts
            print("RESULT", cfg_name, sym, json.dumps(symbols[sym]), flush=True)

        variants[cfg_name] = {
            "params": cfg,
            "summary": metrics(alltr),
            "directions": grouped_metrics(alltr, "direction"),
            "years": year_metrics(alltr),
            "symbols": symbols,
            "trades": alltr,
        }
        print("VARIANT", cfg_name, json.dumps({
            "params": cfg,
            "summary": variants[cfg_name]["summary"],
            "directions": variants[cfg_name]["directions"],
            "years": variants[cfg_name]["years"],
        }), flush=True)

    out = {
        "strategy": "Trend Structure v0.2 break-retest frozen",
        "asset_class": "Binance USDT-M perpetual",
        "universe": list(SYMBOLS),
        "period": {
            "fetch_start": core.FETCH_START.isoformat(),
            "eval_start": core.EVAL_START.isoformat(),
            "eval_end_exclusive": core.EVAL_END.isoformat(),
        },
        "costs": {"fee_bps": core.FEE_BPS, "slippage_bps": core.SLIP_BPS},
        "variants": variants,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("FINAL", json.dumps({
        "strategy": out["strategy"],
        "asset_class": out["asset_class"],
        "universe": out["universe"],
        "period": out["period"],
        "variants": {
            k: {
                "params": v["params"],
                "summary": v["summary"],
                "directions": v["directions"],
                "years": v["years"],
            }
            for k, v in variants.items()
        },
    }, indent=2), flush=True)


if __name__ == "__main__":
    main()
