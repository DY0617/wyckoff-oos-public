import json, os, statistics, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import backtest_cat_core_v0_4_stop_abc_crypto as abc

base=abc.base
UTC=timezone.utc
TRAILS=(2.5,3.0,3.5)
INITIAL_ATR=2.5
OUT=Path(os.environ.get("OUT","data/validation/cat_core_v0_4_trail_sweep_crypto.json"))

def metrics(ts):
    ts=sorted(ts,key=lambda z:(z["exit_t"],z["symbol"]))
    rs=[x["r"] for x in ts]
    pos=[r for r in rs if r>0]; neg=[r for r in rs if r<0]
    eq=peak=0.0; dd=0.0; cur=mx=0
    for r in rs:
        eq+=r; peak=max(peak,eq); dd=min(dd,eq-peak)
        if r<0:
            cur+=1; mx=max(mx,cur)
        else:
            cur=0
    return {
        "trades":len(ts),"wins":len(pos),"losses":len(neg),
        "win_rate":len(pos)/len(ts) if ts else None,
        "total_r":sum(rs),"avg_r":statistics.fmean(rs) if rs else None,
        "profit_factor":sum(pos)/abs(sum(neg)) if neg else None,
        "max_drawdown_r":dd,"max_losing_streak":mx,
        "avg_hold_bars":statistics.fmean([x["hold_bars"] for x in ts]) if ts else None
    }

def sim(sym,D,bench,trail):
    trades=[]; st=defaultdict(int)
    i=200; lo=int(base.EVAL_START.timestamp()*1000); hi=int(base.EVAL_END.timestamp()*1000)
    while i<len(D)-1:
        x=D[i]
        if not (lo<=x["ct"]<hi): i+=1; continue
        if not abc.valid_signal(x,bench.get(x["t"])): i+=1; continue
        st["signals_seen"]+=1
        e=D[i+1]
        if e["t"]>=hi: break
        entry=e["o"]; atr=x["atr14"]
        if atr is None or atr<=0: st["skipped"]+=1; i+=1; continue
        stop=entry-INITIAL_ATR*atr
        if stop<=0 or stop>=entry: st["skipped"]+=1; i+=1; continue
        risk=entry-stop
        realized=-base.cost(entry)/risk
        hi_close=entry; exit_i=i+1; exit_px=None; reason="END"
        j=i+1
        while j<len(D) and D[j]["t"]<hi:
            b=D[j]; exit_i=j
            if b["o"]<=stop:
                exit_px=b["o"]; reason="GAP_STOP"
            elif b["l"]<=stop:
                exit_px=stop; reason="STOP"
            if exit_px is not None:
                realized+=(exit_px-entry)/risk-base.cost(exit_px)/risk
                break
            hi_close=max(hi_close,b["c"])
            stop=max(stop,hi_close-trail*b["atr14"])
            j+=1
        if exit_px is None:
            b=D[min(exit_i,len(D)-1)]; exit_px=b["c"]; reason="END_MARK"
            realized+=(exit_px-entry)/risk-base.cost(exit_px)/risk
        trades.append({
            "symbol":sym,"mode":f"TRAIL_{trail:.1f}","signal_t":x["ct"],"entry_t":e["t"],"exit_t":D[exit_i]["ct"],
            "entry":entry,"exit":exit_px,"initial_risk":risk,"risk_atr":risk/atr,"risk_pct":risk/entry,
            "r":realized,"reason":reason,"hold_bars":int(exit_i-(i+1)+1),
            "ret20":x["ret20"],"ret60":x["ret60"],"ret120":x["ret120"],"er20":x["er20"]
        })
        st["filled"]+=1
        i=exit_i+1
    st["fill_rate"]=st["filled"]/st["signals_seen"] if st["signals_seen"] else None
    return trades,dict(st)

def main():
    data={s:base.enrich(base.fetch1d(s)) for s in base.SYMBOLS}
    bench={x["t"]:x for x in data["BTCUSDT"]}
    out={"strategy":"CAT-Core v0.4 trailing ATR sweep","asset_class":"crypto",
         "initial_stop_atr":INITIAL_ATR,"modes":{}}
    for trail in TRAILS:
        alltr=[]; years=defaultdict(list); symbols={}; agg=defaultdict(int)
        for s,D in data.items():
            ts,st=sim(s,D,bench,trail)
            alltr+=ts
            symbols[s]={"metrics":metrics(ts),"stats":st}
            for k,v in st.items():
                if isinstance(v,int): agg[k]+=v
            for t in ts:
                years[str(datetime.fromtimestamp(t["entry_t"]/1000,UTC).year)].append(t)
        key=f"TRAIL_{trail:.1f}"
        out["modes"][key]={
            "summary":metrics(alltr),"stats":dict(agg),
            "years":{k:metrics(v) for k,v in sorted(years.items())},
            "symbols":symbols,"trades":alltr
        }
        print("MODE",key,json.dumps(out["modes"][key]["summary"]),flush=True)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2),encoding="utf-8")

if __name__=="__main__":
    main()
