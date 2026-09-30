import json, glob
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from trend_structure_v0_2_engine import CONFIGS, metrics

UTC=timezone.utc
ROOT=Path(__file__).resolve().parents[1]
GLOB=str(ROOT/"data/validation/trend_structure_v0_2_stock53_20y_shards/shard_*.json")
OUT=ROOT/"data/validation/trend_structure_v0_2_stock53_20y.json"

def grouped(trades,key):
    d=defaultdict(list)
    for t in trades:d[str(t[key])].append(t)
    return {k:metrics(v) for k,v in sorted(d.items())}

def years(trades):
    d=defaultdict(list)
    for t in trades:
        d[str(datetime.fromtimestamp(t["entry_t"]/1000,UTC).year)].append(t)
    return {k:metrics(v) for k,v in sorted(d.items())}

def main():
    files=sorted(glob.glob(GLOB))
    if not files: raise RuntimeError("no shard files")
    shards=[json.loads(Path(p).read_text(encoding="utf-8")) for p in files]
    variants={}
    universe=[]
    for sh in shards: universe.extend(sh.get("symbols",[]))
    for cfg_name,cfg in CONFIGS.items():
        alltr=[]; symbols={}
        for sh in shards:
            v=sh["variants"][cfg_name]
            alltr.extend(v.get("trades",[]))
            symbols.update(v.get("symbols",{}))
        variants[cfg_name]={
            "params":cfg,
            "summary":metrics(alltr),
            "directions":grouped(alltr,"direction"),
            "years":years(alltr),
            "symbols":symbols,
            "trades":alltr,
        }
        print("MERGED",cfg_name,json.dumps({
            "summary":variants[cfg_name]["summary"],
            "directions":variants[cfg_name]["directions"]
        }),flush=True)
    out={
        "strategy":"Trend Structure v0.2 break-retest frozen",
        "asset_class":"US stock RTH cash-chart research set",
        "universe":sorted(set(universe)),
        "period":{"eval_start":"2006-04-01T00:00:00+00:00","eval_end_exclusive":"2026-04-01T00:00:00+00:00"},
        "variants":variants,
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2),encoding="utf-8")
    print("FINAL",json.dumps({
        "strategy":out["strategy"],"asset_class":out["asset_class"],"universe_count":len(out["universe"]),
        "period":out["period"],
        "variants":{k:{"params":v["params"],"summary":v["summary"],"directions":v["directions"]} for k,v in variants.items()}
    },indent=2),flush=True)

if __name__=="__main__":main()
