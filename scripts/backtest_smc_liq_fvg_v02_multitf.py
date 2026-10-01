import json
from pathlib import Path
from datetime import datetime,timezone
import backtest_smc_liq_fvg_v01 as smc
import backtest_trend_structure_v0_1_crypto as core

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/validation/smc_liq_fvg_v02_multitf.json"
SYMS=("BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","LINKUSDT")
UTC=timezone.utc
TRAIN_END=int(datetime(2025,1,1,tzinfo=UTC).timestamp()*1000)

CONFIGS={
 "tf30":{"signal_minutes":30,"sweep_lookback":40,"disp_max_bars":6,"disp_body_atr":0.90,"tp_r":2.0},
 "tf60":{"signal_minutes":60,"sweep_lookback":20,"disp_max_bars":3,"disp_body_atr":0.90,"tp_r":2.0},
 "tf120":{"signal_minutes":120,"sweep_lookback":10,"disp_max_bars":2,"disp_body_atr":0.90,"tp_r":2.0},
}

def stats(ts):
    if not ts:return {"n":0,"win_rate":None,"net_r":0.0,"avg_r":None,"pf":None,"mdd_r":0.0}
    o=sorted(ts,key=lambda z:(z["exit_t"],z["symbol"]))
    rs=[x["r"] for x in o];pos=[r for r in rs if r>0];neg=[r for r in rs if r<0]
    eq=peak=mdd=0.0
    for r in rs:
        eq+=r;peak=max(peak,eq);mdd=max(mdd,peak-eq)
    return {"n":len(rs),"win_rate":len(pos)/len(rs),"net_r":sum(rs),"avg_r":sum(rs)/len(rs),
            "pf":sum(pos)/abs(sum(neg)) if neg else None,"mdd_r":mdd}

def suppress_same_symbol_overlap(ts):
    out=[];active={}
    for t in sorted(ts,key=lambda x:(x["entry_t"],x["symbol"],x["tf"])):
        if t["entry_t"]<=active.get(t["symbol"],-1):continue
        out.append(t);active[t["symbol"]]=t["exit_t"]
    return out

def split(ts):
    return [t for t in ts if t["entry_t"]<TRAIN_END],[t for t in ts if t["entry_t"]>=TRAIN_END]

def main():
    data={}
    for s in SYMS:
        data[s]=core.load_15m(s);print("DATA",s,len(data[s]),flush=True)
    orig=smc.core.load_15m;bytf={}
    try:
        smc.core.load_15m=lambda sym:data[sym]
        for name,ov in CONFIGS.items():
            cfg=dict(smc.DEFAULTS);cfg.update(ov)
            alltr=[];per={}
            for s in SYMS:
                r=smc.run_symbol(s,None,cfg)
                ts=[dict(t,symbol=s,tf=name) for t in r["fixed2r"]["trades"]]
                alltr+=ts;per[s]=stats(ts)
            tr,te=split(alltr)
            bytf[name]={"config":ov,"overall":stats(alltr),"train":stats(tr),"holdout":stats(te),"symbols":per,"trades":alltr}
            print("TF",name,json.dumps({"overall":bytf[name]["overall"],"train":bytf[name]["train"],"holdout":bytf[name]["holdout"]}),flush=True)
    finally:smc.core.load_15m=orig

    combos={}
    for names in (("tf30","tf60"),("tf60","tf120"),("tf30","tf60","tf120")):
        raw=[]
        for n in names:raw+=bytf[n]["trades"]
        ded=suppress_same_symbol_overlap(raw)
        tr,te=split(ded)
        combos["+".join(names)]={"overall":stats(ded),"train":stats(tr),"holdout":stats(te),"n_before_dedupe":len(raw)}
    out={"version":"0.2-multitf","configs":CONFIGS,
         "timeframes":{k:{x:y for x,y in v.items() if x!="trades"} for k,v in bytf.items()},
         "combinations":combos}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,indent=2),encoding="utf-8")
    print("FINAL",json.dumps({"timeframes":{k:v["overall"] for k,v in bytf.items()},"combinations":combos},indent=2),flush=True)

if __name__=="__main__":main()
