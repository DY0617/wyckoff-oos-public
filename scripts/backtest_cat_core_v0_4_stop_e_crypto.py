import json, os, statistics, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import backtest_cat_core_v0_4_er20_crypto_5y as base
UTC=timezone.utc
OUT=Path(os.environ.get("OUT","data/validation/cat_core_v0_4_stop_e_breakout_clamp_crypto.json"))

def valid_signal(x,bx):
    if base.signal(x)!="LONG":return False
    if bx is None or any(bx.get(f"ret{n}") is None for n in (20,60,120)):return False
    return sum(bx[f"ret{n}"]>0 for n in (20,60,120))>=2

def sim(sym,D,bench):
    trades=[];st=defaultdict(int);mults=[]
    i=200;lo=int(base.EVAL_START.timestamp()*1000);hi=int(base.EVAL_END.timestamp()*1000)
    while i<len(D)-1:
        x=D[i]
        if not (lo<=x["ct"]<hi):i+=1;continue
        if not valid_signal(x,bench.get(x["t"])):i+=1;continue
        st["signals_seen"]+=1
        e=D[i+1]
        if e["t"]>=hi:break
        entry=e["o"];support=x["prior20h"];raw_stop=support-0.5*x["atr14"]
        raw_dist=entry-raw_stop
        dist=min(max(raw_dist,2.0*x["atr14"]),3.0*x["atr14"])
        stop=entry-dist
        if stop<=0 or stop>=entry:
            st["invalid"]+=1;i+=1;continue
        initial_stop=stop;risk=entry-stop;mults.append(risk/x["atr14"])
        realized=-base.cost(entry)/risk;hi_c=entry;exit_i=i+1;exit_px=None;reason="END";j=i+1
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
        trades.append({"symbol":sym,"signal_t":x["ct"],"entry_t":e["t"],"exit_t":D[exit_i]["ct"],
                       "entry":entry,"breakout_support":support,"raw_structural_stop":raw_stop,"initial_stop":initial_stop,
                       "raw_risk_atr":raw_dist/x["atr14"],
                       "exit":exit_px,"initial_risk":risk,"risk_atr":risk/x["atr14"],
                       "risk_pct":risk/entry,"r":realized,"reason":reason,
                       "ret20":x["ret20"],"ret60":x["ret60"],"ret120":x["ret120"],"er20":x["er20"]})
        st["filled"]+=1
        st["clamp_low"]+=int(raw_dist<2.0*x["atr14"])
        st["clamp_high"]+=int(raw_dist>3.0*x["atr14"])
        i=exit_i+1
    st["fill_rate"]=st["filled"]/st["signals_seen"] if st["signals_seen"] else None
    st["avg_initial_stop_atr"]=statistics.fmean(mults) if mults else None
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
    data={s:base.enrich(base.fetch1d(s)) for s in base.SYMBOLS}
    bench={x["t"]:x for x in data["BTCUSDT"]}
    alltr=[];years=defaultdict(list);symbols={};agg=defaultdict(int);wm=[]
    for s,D in data.items():
        ts,st=sim(s,D,bench);alltr+=ts;symbols[s]={"metrics":metrics(ts),"stop_stats":st}
        for k,v in st.items():
            if isinstance(v,int):agg[k]+=v
        if st.get("filled") and st.get("avg_initial_stop_atr") is not None:wm += [st["avg_initial_stop_atr"]]*st["filled"]
        for t in ts:years[str(datetime.fromtimestamp(t["entry_t"]/1000,UTC).year)].append(t)
    ss=dict(agg);ss["fill_rate"]=agg["filled"]/agg["signals_seen"] if agg["signals_seen"] else None
    ss["avg_initial_stop_atr"]=statistics.fmean(wm) if wm else None
    out={"strategy":"CAT-Core v0.4 Stop E Breakout Clamp","asset_class":"crypto",
         "summary":metrics(alltr),"stop_stats":ss,
         "years":{k:metrics(v) for k,v in sorted(years.items())},"symbols":symbols,"trades":alltr}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,indent=2),encoding="utf-8")
    print(json.dumps({"summary":out["summary"],"stop_stats":ss},indent=2),flush=True)
if __name__=="__main__":main()
