import copy,json
from pathlib import Path
from collections import defaultdict
import backtest_smc_liq_fvg_v01 as smc
import backtest_trend_structure_v0_1_crypto as core

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/validation/smc_liq_fvg_v013_crypto8_robustness.json"
SYMS=("BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","LINKUSDT")

VARIANTS={
 "base":{},
 "sweep16":{"sweep_lookback":16},
 "sweep24":{"sweep_lookback":24},
 "disp070":{"disp_body_atr":0.70},
 "disp090":{"disp_body_atr":0.90},
 "fvg005":{"fvg_min_atr":0.05},
 "fvg015":{"fvg_min_atr":0.15},
 "retest4":{"retest_hours":4},
 "retest12":{"retest_hours":12},
}

def agg(ts):
    if not ts:
        return {"n":0,"win_rate":None,"net_r":0.0,"avg_r":None,"pf":None,"mdd_r":0.0}
    rs=[x["r"] for x in ts]
    pos=[r for r in rs if r>0];neg=[r for r in rs if r<0]
    eq=peak=mdd=0.0
    for t in sorted(ts,key=lambda x:x["exit_t"]):
        eq+=t["r"];peak=max(peak,eq);mdd=max(mdd,peak-eq)
    return {"n":len(ts),"win_rate":len(pos)/len(ts),"net_r":sum(rs),"avg_r":sum(rs)/len(ts),
            "pf":sum(pos)/abs(sum(neg)) if neg else None,"mdd_r":mdd}

def main():
    data={}
    for s in SYMS:
        data[s]=core.load_15m(s)
        print("DATA",s,len(data[s]),flush=True)

    original=smc.core.load_15m
    results={}
    try:
        smc.core.load_15m=lambda sym:data[sym]
        for name,ov in VARIANTS.items():
            cfg=dict(smc.DEFAULTS);cfg.update(ov)
            symbols={};alltr=[]
            for s in SYMS:
                r=smc.run_symbol(s,None,cfg)
                ts=[dict(t,symbol=s) for t in r["fixed2r"]["trades"]]
                alltr+=ts
                symbols[s]={"setups":r["setup_count"],"fills":r["filled_count"],"metrics":agg(ts)}
                print("RESULT",name,s,json.dumps(symbols[s]),flush=True)
            yearly=defaultdict(list);directions=defaultdict(list)
            for t in alltr:
                import datetime
                y=str(datetime.datetime.fromtimestamp(t["entry_t"]/1000,datetime.timezone.utc).year)
                yearly[y].append(t);directions[t["direction"]].append(t)
            loo={}
            for excluded in SYMS:
                loo[excluded]=agg([t for t in alltr if t["symbol"]!=excluded])
            results[name]={
                "params":cfg,
                "summary":agg(alltr),
                "symbols":symbols,
                "years":{k:agg(v) for k,v in sorted(yearly.items())},
                "directions":{k:agg(v) for k,v in sorted(directions.items())},
                "leave_one_symbol_out":loo,
            }
    finally:
        smc.core.load_15m=original

    out={
      "version":"0.1.3",
      "strategy":"objective liquidity sweep + displacement + FVG first retest; fixed 2R",
      "universe":list(SYMS),
      "period":{"eval_start":core.EVAL_START.isoformat(),"eval_end_exclusive":core.EVAL_END.isoformat()},
      "purpose":"parameter plateau + crypto8 cross-symbol robustness",
      "variants":results,
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2),encoding="utf-8")
    print("FINAL",json.dumps({k:v["summary"] for k,v in results.items()},indent=2),flush=True)

if __name__=="__main__":
    main()
