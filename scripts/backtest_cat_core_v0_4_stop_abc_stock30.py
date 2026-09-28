import json, os, statistics, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import backtest_cat_core_v0_4_er20_stock30_5y as base

UTC=timezone.utc
MODES=("A_2ATR","B_LOW10","C_SWING")
OUT=Path(os.environ.get("OUT","data/validation/cat_core_v0_4_stop_abc_stock30.json"))

def valid_signal(x,bx):
    if base.signal(x)!="LONG":return False
    if bx is None or any(bx.get(f"ret{n}") is None for n in (20,60,120)):return False
    return sum(bx[f"ret{n}"]>0 for n in (20,60,120))>=2

def recent_pivot_low(D,i):
    lo=max(2,i-19)
    for j in range(i-2,lo-1,-1):
        if j+2>i:continue
        v=D[j]["l"]
        if v<D[j-2]["l"] and v<D[j-1]["l"] and v<D[j+1]["l"] and v<D[j+2]["l"]:
            return j,v
    return None,None

def initial_stop(mode,D,i,entry):
    atr=D[i]["atr14"]
    if atr<=0:return None,{"invalid":1}
    if mode=="A_2ATR":return entry-2.0*atr,{"atr_multiple":2.0}
    if mode=="B_LOW10":
        support=min(z["l"] for z in D[max(0,i-9):i+1]);stop=support-0.5*atr
        return stop,{"support":support,"raw_stop":stop,"atr_multiple":(entry-stop)/atr}
    if mode=="C_SWING":
        pj,pv=recent_pivot_low(D,i)
        if pj is None:return None,{"no_pivot":1}
        raw=pv-0.5*atr;raw_dist=entry-raw;dist=min(max(raw_dist,1.2*atr),2.5*atr);stop=entry-dist
        return stop,{"pivot_index":pj,"pivot_low":pv,"raw_stop":raw,"raw_atr_multiple":raw_dist/atr,
                     "atr_multiple":dist/atr,"clamp_low":int(raw_dist<1.2*atr),"clamp_high":int(raw_dist>2.5*atr)}
    raise ValueError(mode)

def sim_mode(sym,D,bench,mode):
    trades=[];st=defaultdict(int);atr_mult=[]
    i=200;lo=int(base.EVAL_START.timestamp()*1000);hi=int(base.EVAL_END.timestamp()*1000)
    while i<len(D)-1:
        x=D[i]
        if not (lo<=x["t"]<hi):i+=1;continue
        if not valid_signal(x,bench.get(x["date"])):i+=1;continue
        st["signals_seen"]+=1;e=D[i+1]
        if e["t"]>=hi:break
        entry=e["o"];stop,meta=initial_stop(mode,D,i,entry)
        for k,v in meta.items():
            if k in ("no_pivot","invalid","clamp_low","clamp_high"):st[k]+=int(v)
        if stop is None or stop<=0 or stop>=entry:
            st["skipped"]+=1;i+=1;continue
        risk=entry-stop;atr_mult.append(risk/x["atr14"]);realized=-base.cost(entry)/risk
        hi_c=entry;exit_i=i+1;exit_px=None;reason="END";j=i+1
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
        trades.append({"symbol":sym,"mode":mode,"signal_t":x["ct"],"entry_t":e["t"],"exit_t":D[exit_i]["ct"],
                       "entry":entry,"exit":exit_px,"initial_risk":risk,"risk_atr":risk/x["atr14"],
                       "risk_pct":risk/entry,"r":realized,"reason":reason,"er20":x["er20"],"stop_meta":meta})
        st["filled"]+=1;i=exit_i+1
    st["fill_rate"]=st["filled"]/st["signals_seen"] if st["signals_seen"] else None
    st["avg_initial_stop_atr"]=statistics.fmean(atr_mult) if atr_mult else None
    return trades,dict(st)

def metrics(ts):
    ts=sorted(ts,key=lambda z:(z["exit_t"],z["symbol"]));rs=[x["r"] for x in ts]
    pos=[r for r in rs if r>0];neg=[r for r in rs if r<0]
    eq=peak=0.;dd=0.;cur=mx=0
    for r in rs:
        eq+=r;peak=max(peak,eq);dd=min(dd,eq-peak)
        if r<0:cur+=1;mx=max(mx,cur)
        else:cur=0
    return {"trades":len(ts),"wins":len(pos),"losses":len(neg),"win_rate":len(pos)/len(ts) if ts else None,
            "total_r":sum(rs),"avg_r":statistics.fmean(rs) if rs else None,
            "profit_factor":sum(pos)/abs(sum(neg)) if neg else None,
            "max_drawdown_r":dd,"max_losing_streak":mx}

def main():
    raw=base.collect();data={}
    for s,D in raw.items():
        D=base.enrich(base.adjust(D))
        if len(D)>=201:data[s]=D
    bench={x["date"]:x for x in data["SPY"]}
    out={"strategy":"CAT-Core v0.4 stop A/B/C","asset_class":"us_stock_underlying_proxy_for_futures","modes":{}}
    for mode in MODES:
        alltr=[];years=defaultdict(list);symbols={};agg=defaultdict(int);weighted=[]
        for s,D in data.items():
            ts,st=sim_mode(s,D,bench,mode);alltr+=ts;symbols[s]={"metrics":metrics(ts),"stop_stats":st}
            for k,v in st.items():
                if isinstance(v,int):agg[k]+=v
            if st.get("filled") and st.get("avg_initial_stop_atr") is not None:
                weighted += [st["avg_initial_stop_atr"]]*st["filled"]
            for t in ts:years[str(datetime.fromtimestamp(t["entry_t"]/1000,UTC).year)].append(t)
        stop_stats=dict(agg);stop_stats["fill_rate"]=agg["filled"]/agg["signals_seen"] if agg["signals_seen"] else None
        stop_stats["avg_initial_stop_atr"]=statistics.fmean(weighted) if weighted else None
        out["modes"][mode]={"summary":metrics(alltr),"stop_stats":stop_stats,
                           "years":{k:metrics(v) for k,v in sorted(years.items())},
                           "symbols":symbols,"trades":alltr}
        print("MODE",mode,json.dumps(out["modes"][mode]["summary"]),json.dumps(stop_stats),flush=True)
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,indent=2),encoding="utf-8")

if __name__=="__main__":main()
