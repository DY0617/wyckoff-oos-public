import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime,timezone
import backtest_smc_liq_fvg_v01 as smc
import backtest_trend_structure_v0_1_crypto as core

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/validation/smc_liq_fvg_v02_universe16.json"
UTC=timezone.utc
SYMS=("BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","LINKUSDT",
      "LTCUSDT","BCHUSDT","DOTUSDT","AVAXUSDT","ETCUSDT","ATOMUSDT","FILUSDT","UNIUSDT")
TRAIN_END=int(datetime(2025,1,1,tzinfo=UTC).timestamp()*1000)
EXPECTED_MIN=120000

def stats(ts):
    if not ts:return {"n":0,"win_rate":None,"net_r":0.0,"avg_r":None,"pf":None,"mdd_r":0.0}
    o=sorted(ts,key=lambda z:(z["exit_t"],z["symbol"]))
    rs=[t["r"] for t in o];pos=[r for r in rs if r>0];neg=[r for r in rs if r<0]
    eq=peak=mdd=0.0
    for r in rs:
        eq+=r;peak=max(peak,eq);mdd=max(mdd,peak-eq)
    return {"n":len(rs),"win_rate":len(pos)/len(rs),"net_r":sum(rs),"avg_r":sum(rs)/len(rs),
            "pf":sum(pos)/abs(sum(neg)) if neg else None,"mdd_r":mdd}

def main():
    data={};coverage={}
    for s in SYMS:
        b=core.load_15m(s);coverage[s]=len(b)
        if len(b)>=EXPECTED_MIN:data[s]=b
        print("DATA",s,len(b),"USE",s in data,flush=True)
    orig=smc.core.load_15m;rows=[]
    try:
        smc.core.load_15m=lambda sym:data[sym]
        for cfg_name,ov in {
            "base":{"tp_r":2.0},
            "disp090":{"disp_body_atr":0.90,"tp_r":2.0},
        }.items():
            alltr=[];per={}
            cfg=dict(smc.DEFAULTS);cfg.update(ov)
            for s in data:
                r=smc.run_symbol(s,None,cfg)
                ts=[dict(t,symbol=s) for t in r["fixed2r"]["trades"]]
                alltr+=ts;per[s]=stats(ts)
            train=[t for t in alltr if t["entry_t"]<TRAIN_END]
            hold=[t for t in alltr if t["entry_t"]>=TRAIN_END]
            rows.append({"name":cfg_name,"overrides":ov,"overall":stats(alltr),"train":stats(train),"holdout":stats(hold),
                         "positive_symbols_overall":sum(v["net_r"]>0 for v in per.values()),"symbols":per})
    finally:smc.core.load_15m=orig
    out={"version":"0.2-universe16","coverage_rows":coverage,"used_symbols":list(data),"variants":rows}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,indent=2),encoding="utf-8")
    print("FINAL",json.dumps(rows,indent=2),flush=True)

if __name__=="__main__":main()
