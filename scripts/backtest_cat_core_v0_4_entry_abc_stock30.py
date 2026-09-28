import json, os, statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import backtest_cat_core_v0_4_er20_stock30_5y as base

UTC=timezone.utc
MODES=("A_NEXT_OPEN","B_RETEST","C_HYBRID")
VALID_BARS=3
GAP_ATR_MAX=0.50
OUT=Path(os.environ.get("OUT","data/validation/cat_core_v0_4_entry_abc_stock30.json"))

def valid_signal(x,bx):
    if base.signal(x)!="LONG":return False
    if bx is None or any(bx.get(f"ret{n}") is None for n in (20,60,120)):return False
    return sum(bx[f"ret{n}"]>0 for n in (20,60,120))>=2

def entry_candidate(mode,D,i):
    x=D[i];level=x["prior20h"];atr=x["atr14"]
    if mode=="A_NEXT_OPEN":
        if i+1>=len(D):return None,"EXPIRED"
        return (i+1,D[i+1]["o"],"NEXT_OPEN"),None
    last=min(len(D)-1,i+VALID_BARS)
    if mode=="B_RETEST":
        for k in range(i+1,last+1):
            b=D[k]
            if b["l"]<=level<=b["h"]:return (k,level,"RETEST_TOUCH"),None
        return None,"EXPIRED"
    if mode=="C_HYBRID":
        cap=level+GAP_ATR_MAX*atr
        for k in range(i+1,last+1):
            b=D[k]
            if b["o"]>cap:return None,"GAP_CANCEL"
            if b["o"]>=level:return (k,b["o"],"NORMAL_OPEN"),None
            if b["h"]>=level:return (k,level,"STOP_RECLAIM"),None
        return None,"EXPIRED"
    raise ValueError(mode)

def run_trade(sym,D,i,mode):
    cand,miss=entry_candidate(mode,D,i)
    if cand is None:return None,miss,None
    ei,entry,etype=cand
    hi=int(base.EVAL_END.timestamp()*1000)
    if D[ei]["t"]>=hi:return None,"EXPIRED",None
    risk=base.STOP_ATR*D[i]["atr14"]
    if risk<=0 or entry-risk<=0:return None,"INVALID_RISK",None
    stop=entry-risk;realized=-base.cost(entry)/risk;hi_c=entry;exit_i=ei;exit_px=None;reason="END"
    j=ei
    while j<len(D) and D[j]["t"]<hi:
        b=D[j];exit_i=j
        if b["o"]<=stop:exit_px=b["o"];reason="GAP_STOP"
        elif b["l"]<=stop:exit_px=stop;reason="STOP"
        if exit_px is not None:
            realized+=(exit_px-entry)/risk-base.cost(exit_px)/risk;break
        hi_c=max(hi_c,b["c"]);stop=max(stop,hi_c-base.TRAIL_ATR*b["atr14"]);j+=1
    if exit_px is None:
        b=D[min(exit_i,len(D)-1)];exit_px=b["c"];reason="END_MARK"
        realized+=(exit_px-entry)/risk-base.cost(exit_px)/risk
    return {"symbol":sym,"direction":"LONG","mode":mode,"signal_t":D[i]["ct"],
            "entry_t":D[ei]["t"],"entry_bar_index":ei,"exit_t":D[exit_i]["ct"],
            "entry":entry,"entry_type":etype,"breakout_level":D[i]["prior20h"],
            "exit":exit_px,"initial_risk":risk,"risk_pct":risk/entry,"r":realized,"reason":reason,
            "er20":D[i]["er20"]},None,exit_i

def simulate_mode(sym,D,bench,mode):
    trades=[];stats={"signals_seen":0,"filled":0,"expired":0,"gap_cancelled":0,"invalid_risk":0}
    i=200;lo=int(base.EVAL_START.timestamp()*1000);hi=int(base.EVAL_END.timestamp()*1000)
    while i<len(D)-1:
        x=D[i]
        if not (lo<=x["t"]<hi):i+=1;continue
        if not valid_signal(x,bench.get(x["date"])):i+=1;continue
        stats["signals_seen"]+=1
        t,miss,exit_i=run_trade(sym,D,i,mode)
        if t is None:
            if miss=="GAP_CANCEL":stats["gap_cancelled"]+=1
            elif miss=="INVALID_RISK":stats["invalid_risk"]+=1
            else:stats["expired"]+=1
            i=min(len(D),i+VALID_BARS+1);continue
        trades.append(t);stats["filled"]+=1;i=exit_i+1
    stats["fill_rate"]=stats["filled"]/stats["signals_seen"] if stats["signals_seen"] else None
    return trades,stats

def metrics(ts):
    ts=sorted(ts,key=lambda z:(z["exit_t"],z["symbol"]));rs=[x["r"] for x in ts]
    pos=[r for r in rs if r>0];neg=[r for r in rs if r<0]
    eq=peak=0.;dd=0.;cur=mx=0
    for r in rs:
        eq+=r;peak=max(peak,eq);dd=min(dd,eq-peak)
        if r<0:cur+=1;mx=max(mx,cur)
        else:cur=0
    return {"trades":len(ts),"wins":len(pos),"losses":len(neg),
            "win_rate":len(pos)/len(ts) if ts else None,"total_r":sum(rs),
            "avg_r":statistics.fmean(rs) if rs else None,
            "profit_factor":sum(pos)/abs(sum(neg)) if neg else None,
            "max_drawdown_r":dd,"max_losing_streak":mx}

def main():
    raw=base.collect();data={}
    for s,D in raw.items():
        D=base.enrich(base.adjust(D))
        if len(D)>=201:data[s]=D
    bench={x["date"]:x for x in data["SPY"]}
    out={"strategy":"CAT-Core v0.4 entry A/B/C","asset_class":"us_stock_underlying_proxy_for_futures",
         "parameters":{"retest_valid_bars":VALID_BARS,"hybrid_max_gap_atr":GAP_ATR_MAX,
         "same_bar_ambiguity":"conservative stop if entry bar also touches stop"},"modes":{}}
    for mode in MODES:
        alltr=[];agg=defaultdict(int);years=defaultdict(list);symbols={}
        for s,D in data.items():
            ts,st=simulate_mode(s,D,bench,mode);alltr+=ts
            symbols[s]={"metrics":metrics(ts),"entry_stats":st}
            for k,v in st.items():
                if k!="fill_rate":agg[k]+=v
            for t in ts:years[str(datetime.fromtimestamp(t["entry_t"]/1000,UTC).year)].append(t)
        entry_stats=dict(agg);entry_stats["fill_rate"]=agg["filled"]/agg["signals_seen"] if agg["signals_seen"] else None
        out["modes"][mode]={"summary":metrics(alltr),"entry_stats":entry_stats,
                           "years":{k:metrics(v) for k,v in sorted(years.items())},
                           "symbols":symbols,"trades":alltr}
        print("MODE",mode,json.dumps(out["modes"][mode]["summary"]),json.dumps(entry_stats),flush=True)
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,indent=2),encoding="utf-8")

if __name__=="__main__":main()
