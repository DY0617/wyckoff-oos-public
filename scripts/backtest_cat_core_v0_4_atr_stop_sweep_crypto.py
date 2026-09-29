import json, os, statistics, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import backtest_cat_core_v0_4_stop_abc_crypto as abc

base=abc.base
UTC=timezone.utc
MULTS=(1.5,2.0,2.5,3.0)
OUT=Path(os.environ.get("OUT","data/validation/cat_core_v0_4_atr_stop_sweep_crypto.json"))

def sim_mult(sym,D,bench,mult):
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
        stop=entry-mult*atr
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
            stop=max(stop,hi_close-base.TRAIL_ATR*b["atr14"])
            j+=1
        if exit_px is None:
            b=D[min(exit_i,len(D)-1)]; exit_px=b["c"]; reason="END_MARK"
            realized+=(exit_px-entry)/risk-base.cost(exit_px)/risk
        trades.append({
            "symbol":sym,"mode":f"ATR_{mult:.1f}","signal_t":x["ct"],"entry_t":e["t"],"exit_t":D[exit_i]["ct"],
            "entry":entry,"exit":exit_px,"initial_risk":risk,"risk_atr":risk/atr,"risk_pct":risk/entry,
            "r":realized,"reason":reason,"ret20":x["ret20"],"ret60":x["ret60"],"ret120":x["ret120"],"er20":x["er20"]
        })
        st["filled"]+=1
        i=exit_i+1
    st["fill_rate"]=st["filled"]/st["signals_seen"] if st["signals_seen"] else None
    st["avg_initial_stop_atr"]=mult if st["filled"] else None
    return trades,dict(st)

def main():
    data={s:base.enrich(base.fetch1d(s)) for s in base.SYMBOLS}
    bench={x["t"]:x for x in data["BTCUSDT"]}
    out={"strategy":"CAT-Core v0.4 initial ATR stop sweep","asset_class":"crypto","modes":{}}
    for mult in MULTS:
        alltr=[]; years=defaultdict(list); symbols={}; agg=defaultdict(int)
        for s,D in data.items():
            ts,st=sim_mult(s,D,bench,mult)
            alltr+=ts
            symbols[s]={"metrics":abc.metrics(ts),"stop_stats":st}
            for k,v in st.items():
                if isinstance(v,int): agg[k]+=v
            for t in ts:
                years[str(datetime.fromtimestamp(t["entry_t"]/1000,UTC).year)].append(t)
        stop_stats=dict(agg)
        stop_stats["fill_rate"]=agg["filled"]/agg["signals_seen"] if agg["signals_seen"] else None
        stop_stats["avg_initial_stop_atr"]=mult
        key=f"ATR_{mult:.1f}"
        out["modes"][key]={
            "summary":abc.metrics(alltr),"stop_stats":stop_stats,
            "years":{k:abc.metrics(v) for k,v in sorted(years.items())},
            "symbols":symbols,"trades":alltr
        }
        print("MODE",key,json.dumps(out["modes"][key]["summary"]),flush=True)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2),encoding="utf-8")

if __name__=="__main__":
    main()
