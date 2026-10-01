import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime,timezone
import backtest_smc_liq_fvg_v01 as smc
import backtest_trend_structure_v0_1_crypto as core

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/validation/smc_liq_fvg_v02_stage1.json"
SYMS=("BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","LINKUSDT")
UTC=timezone.utc
TRAIN_END=int(datetime(2025,1,1,tzinfo=UTC).timestamp()*1000)
TEST_START=TRAIN_END

VARIANTS={"base":{}}
for x in (1.5,1.75,2.25,2.5,3.0): VARIANTS[f"tp_{x:g}r"]={"tp_r":x}
for x in (.25,.35,.65,.75): VARIANTS[f"depth_{x:.2f}"]={"fvg_entry_depth":x}
for x in ("ema200_only","ema50_200","price_ema50"): VARIANTS[f"trend_{x}"]={"trend_mode":x}
for x in (.05,.10,.25,.35): VARIANTS[f"stop_{x:.2f}"]={"stop_buffer_atr":x}
for x in (12,16,24,32): VARIANTS[f"sweep_{x}"]={"sweep_lookback":x}
for x in (.60,.70,.90,1.00): VARIANTS[f"disp_{x:.2f}"]={"disp_body_atr":x}
for x in (.05,.15,.20): VARIANTS[f"fvg_{x:.2f}"]={"fvg_min_atr":x}
for x in (4,12,24): VARIANTS[f"retest_{x}h"]={"retest_hours":x}

def stats(ts):
    if not ts:return {"n":0,"wins":0,"win_rate":None,"net_r":0.0,"avg_r":None,"pf":None,"mdd_r":0.0,"max_ls":0}
    o=sorted(ts,key=lambda z:(z["exit_t"],z["symbol"]))
    rs=[x["r"] for x in o]; pos=[r for r in rs if r>0]; neg=[r for r in rs if r<0]
    eq=peak=mdd=0.0;cur=mx=0
    for r in rs:
        eq+=r;peak=max(peak,eq);mdd=max(mdd,peak-eq)
        if r<0:cur+=1;mx=max(mx,cur)
        else:cur=0
    return {"n":len(rs),"wins":len(pos),"win_rate":len(pos)/len(rs),"net_r":sum(rs),"avg_r":sum(rs)/len(rs),
            "pf":sum(pos)/abs(sum(neg)) if neg else None,"mdd_r":mdd,"max_ls":mx}

def split(ts):
    return [t for t in ts if t["entry_t"]<TRAIN_END],[t for t in ts if t["entry_t"]>=TEST_START]

def pos_symbols(ts):
    d=defaultdict(list)
    for t in ts:d[t["symbol"]].append(t)
    sm={s:stats(d.get(s,[])) for s in SYMS}
    return sum(v["net_r"]>0 for v in sm.values()),sm

def score(train_st,pos_count):
    if train_st["n"]<25:return -1e9
    pf=train_st["pf"] or 0.0
    if pf<1.20 or train_st["avg_r"] is None or train_st["avg_r"]<=0 or pos_count<4:return -1e9
    return train_st["net_r"]-0.35*train_st["mdd_r"]+0.35*pos_count

def main():
    data={}
    for s in SYMS:
        data[s]=core.load_15m(s);print("DATA",s,len(data[s]),flush=True)
    orig=smc.core.load_15m
    outvars={}
    try:
        smc.core.load_15m=lambda sym:data[sym]
        for name,ov in VARIANTS.items():
            cfg=dict(smc.DEFAULTS);cfg.update(ov)
            alltr=[];per={}
            for s in SYMS:
                r=smc.run_symbol(s,None,cfg)
                ts=[dict(t,symbol=s) for t in r["fixed2r"]["trades"]]
                alltr+=ts;per[s]=stats(ts)
            tr,te=split(alltr);ptr,train_sym=pos_symbols(tr);pte,test_sym=pos_symbols(te)
            train_st=stats(tr);test_st=stats(te);all_st=stats(alltr)
            sc=score(train_st,ptr)
            outvars[name]={"overrides":ov,"score_train_only":sc,"overall":all_st,"train":train_st,"holdout":test_st,
                           "positive_symbols_train":ptr,"positive_symbols_holdout":pte,
                           "symbols_overall":per,"symbols_train":train_sym,"symbols_holdout":test_sym}
            print("VAR",name,json.dumps({"ov":ov,"score":sc,"train":train_st,"holdout":test_st,"pos_train":ptr,"pos_test":pte}),flush=True)
    finally:
        smc.core.load_15m=orig

    ranked=sorted(outvars,key=lambda k:outvars[k]["score_train_only"],reverse=True)
    selected=ranked[0]
    result={"version":"0.2-stage1","strategy":"SMC liquidity-FVG fixed target factor search",
            "universe":list(SYMS),"train_end_exclusive":"2025-01-01T00:00:00Z",
            "holdout_start":"2025-01-01T00:00:00Z",
            "selection_note":"ranking uses training period only; holdout is reported after selection",
            "selected_by_train":selected,"ranking":ranked,"variants":outvars}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print("SELECTED",selected,json.dumps(outvars[selected]),flush=True)

if __name__=="__main__":main()
