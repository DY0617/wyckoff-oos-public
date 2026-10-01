import bisect,json,statistics
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

import backtest_easychart_synthesis_v01 as ez
import backtest_smc_liq_fvg_v01 as smc
import backtest_trend_structure_v0_1_crypto as core

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/validation/easychart_a_v02_diagnostics.json"
UTC=timezone.utc
TRAIN_END=int(datetime(2025,1,1,tzinfo=UTC).timestamp()*1000)
SYMS=ez.SYMS

def metrics(ts):
    return ez.metrics(ts)

def split(ts):
    return [t for t in ts if t["entry_t"]<TRAIN_END],[t for t in ts if t["entry_t"]>=TRAIN_END]

def summary(ts):
    tr,ho=split(ts)
    return {"overall":metrics(ts),"train":metrics(tr),"holdout":metrics(ho)}

def attach_daily(M,t):
    D,Dclose=smc.prepare_daily(smc.aggregate_1d(M))
    di=bisect.bisect_right(Dclose,t["signal_t"])-1
    if di<6:return None
    x=D[di]; A=x.get("atr")
    if not A or A<=0:return None
    sign=1 if t["direction"]=="LONG" else -1
    slope50=sign*(x["ema50"]-D[di-5]["ema50"])/A
    slope20=sign*(x["ema20"]-D[di-5]["ema20"])/A
    gap=sign*(x["ema20"]-x["ema50"])/A
    price50=sign*(x["c"]-x["ema50"])/A
    return {"d_gap20_50_atr":gap,"d_slope50_5_atr":slope50,"d_slope20_5_atr":slope20,"d_price50_atr":price50}

def main():
    data={};alltr=[]
    for s in SYMS:
        M=core.load_15m(s);data[s]=M
        D=smc.aggregate_1d(M);W=ez.aggregate_weekly(D);MN=ez.aggregate_monthly(D)
        for t in ez.build_track_a(s,M,W,MN):
            q=dict(t);q["daily_feat"]=attach_daily(M,q);alltr.append(q)
        print("A",s,len([t for t in alltr if t["symbol"]==s]),flush=True)

    groups={}
    groups["all"]=alltr
    for k in ("htf","channel_fakeout","vol_expansion","ob_overlap"):
        groups[k+"_yes"]=[t for t in alltr if bool(t["quality"].get(k, t.get(k,False)))]
        groups[k+"_no"]=[t for t in alltr if not bool(t["quality"].get(k, t.get(k,False)))]
    for d in ("LONG","SHORT"):
        groups["dir_"+d]=[t for t in alltr if t["direction"]==d]
    for sc in (0,1,2,3):
        groups[f"score_eq_{sc}"]=[t for t in alltr if t.get("score")==sc]
    for th in (0.0,0.10,0.20,0.30,0.50,0.75):
        groups[f"gap_ge_{th:.2f}"]=[t for t in alltr if t["daily_feat"] and t["daily_feat"]["d_gap20_50_atr"]>=th]
    for th in (-0.10,0.0,0.05,0.10,0.20,0.30):
        groups[f"slope50_ge_{th:.2f}"]=[t for t in alltr if t["daily_feat"] and t["daily_feat"]["d_slope50_5_atr"]>=th]
    for th in (0.0,0.25,0.50,0.75,1.0):
        groups[f"price50_ge_{th:.2f}"]=[t for t in alltr if t["daily_feat"] and t["daily_feat"]["d_price50_atr"]>=th]

    combos={}
    combo_specs=[
      ("gap10_slope0",lambda t:t["daily_feat"] and t["daily_feat"]["d_gap20_50_atr"]>=.10 and t["daily_feat"]["d_slope50_5_atr"]>=0),
      ("gap20_slope0",lambda t:t["daily_feat"] and t["daily_feat"]["d_gap20_50_atr"]>=.20 and t["daily_feat"]["d_slope50_5_atr"]>=0),
      ("gap10_slope05",lambda t:t["daily_feat"] and t["daily_feat"]["d_gap20_50_atr"]>=.10 and t["daily_feat"]["d_slope50_5_atr"]>=.05),
      ("slope0_vol",lambda t:t["daily_feat"] and t["daily_feat"]["d_slope50_5_atr"]>=0 and t["quality"].get("vol_expansion")),
      ("gap10_vol",lambda t:t["daily_feat"] and t["daily_feat"]["d_gap20_50_atr"]>=.10 and t["quality"].get("vol_expansion")),
      ("gap10_htf",lambda t:t["daily_feat"] and t["daily_feat"]["d_gap20_50_atr"]>=.10 and t["quality"].get("htf")),
      ("slope0_htf",lambda t:t["daily_feat"] and t["daily_feat"]["d_slope50_5_atr"]>=0 and t["quality"].get("htf")),
    ]
    for name,fn in combo_specs:combos[name]=[t for t in alltr if fn(t)]

    by_year_dir={}
    for y in range(2021,2027):
        for d in ("LONG","SHORT"):
            x=[t for t in alltr if datetime.fromtimestamp(t["entry_t"]/1000,UTC).year==y and t["direction"]==d]
            by_year_dir[f"{y}_{d}"]=metrics(x)

    out={
      "version":"0.2-diagnostics",
      "groups":{k:summary(v) for k,v in groups.items()},
      "combos":{k:summary(v) for k,v in combos.items()},
      "by_year_direction":by_year_dir,
      "trades":[{k:t[k] for k in ("symbol","direction","entry_t","exit_t","r","target_r","score","quality","htf","daily_feat")} for t in alltr],
    }
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,indent=2),encoding="utf-8")
    print("FINAL",json.dumps({
      "groups":{k:v["overall"] for k,v in out["groups"].items()},
      "combos":{k:v["overall"] for k,v in out["combos"].items()},
      "by_year_direction":by_year_dir,
    },indent=2),flush=True)

if __name__=="__main__":main()
