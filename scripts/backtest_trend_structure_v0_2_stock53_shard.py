import json, os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import duckdb

import backtest_trend_structure_v0_1_stock53 as stockbase
from trend_structure_v0_2_engine import CONFIGS, metrics, run_symbol

UTC=timezone.utc
DATA=Path(os.environ["DATA_PARQUET"])
OUT=Path(os.environ["OUT"])
EVAL_START=datetime.strptime(os.environ["EVAL_START"],"%Y-%m-%d").replace(tzinfo=UTC)
EVAL_END=datetime.strptime(os.environ["EVAL_END"],"%Y-%m-%d").replace(tzinfo=UTC)
SYMS=tuple(x.strip() for x in os.environ["TRADE_SYMS"].split(",") if x.strip())

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
    stockbase.DATA=DATA
    con=duckdb.connect()
    cache={}
    for sym in SYMS:
        b15=stockbase.load_symbol(con,sym)
        h1=stockbase.aggregate_rth_1h(b15)
        d1=stockbase.aggregate_rth_daily(b15)
        cache[sym]=(b15,h1,d1)
        print("DATA_READY",sym,len(b15),len(h1),len(d1),flush=True)
    con.close()

    variants={}
    for cfg_name,cfg in CONFIGS.items():
        alltr=[]; symbols={}
        for sym,(b15,h1,d1) in cache.items():
            if len(b15)<500:
                symbols[sym]={"metrics":metrics([]),"stats":{"skipped":"insufficient_data","bars15":len(b15)}}
                continue
            ts,st=run_symbol(sym,b15,cfg_name,h1_override=h1,h4_override=d1,eval_start=EVAL_START,eval_end=EVAL_END)
            st["bars15"]=len(b15);st["bars1h_rth"]=len(h1);st["daily_rth"]=len(d1)
            symbols[sym]={"metrics":metrics(ts),"stats":st}
            alltr+=ts
            print("RESULT",cfg_name,sym,json.dumps(symbols[sym]),flush=True)
        variants[cfg_name]={
            "params":cfg,
            "summary":metrics(alltr),
            "directions":grouped(alltr,"direction"),
            "years":years(alltr),
            "symbols":symbols,
            "trades":alltr,
        }
        print("VARIANT",cfg_name,json.dumps({
            "summary":variants[cfg_name]["summary"],
            "directions":variants[cfg_name]["directions"]
        }),flush=True)

    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps({
        "strategy":"Trend Structure v0.2 break-retest frozen",
        "asset_class":"US stock RTH cash-chart research set",
        "period":{"eval_start":EVAL_START.isoformat(),"eval_end_exclusive":EVAL_END.isoformat()},
        "symbols":list(SYMS),
        "variants":variants,
    },indent=2),encoding="utf-8")

if __name__=="__main__":main()
