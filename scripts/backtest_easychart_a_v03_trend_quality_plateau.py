import bisect,json
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

import backtest_easychart_synthesis_v01 as ez
import backtest_smc_liq_fvg_v01 as smc
import backtest_trend_structure_v0_1_crypto as core

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/validation/easychart_a_v03_trend_quality_plateau.json"
UTC=timezone.utc
TRAIN_END=int(datetime(2025,1,1,tzinfo=UTC).timestamp()*1000)
SYMS=ez.SYMS

GAPS=(0.00,0.05,0.10,0.15,0.20,0.30)
SLOPES=(0.00,0.025,0.05,0.075,0.10,0.15)

def attach_daily(M,t):
    D,Dclose=smc.prepare_daily(smc.aggregate_1d(M))
    di=bisect.bisect_right(Dclose,t["signal_t"])-1
    if di<6:return None
    x=D[di]; A=x.get("atr")
    if not A or A<=0:return None
    sign=1 if t["direction"]=="LONG" else -1
    return {
      "gap":sign*(x["ema20"]-x["ema50"])/A,
      "slope50":sign*(x["ema50"]-D[di-5]["ema50"])/A,
      "slope20":sign*(x["ema20"]-D[di-5]["ema20"])/A,
      "price50":sign*(x["c"]-x["ema50"])/A,
    }

def metrics(ts): return ez.metrics(ts)

def split(ts):
    return [t for t in ts if t["entry_t"]<TRAIN_END],[t for t in ts if t["entry_t"]>=TRAIN_END]

def years(ts):
    d=defaultdict(list)
    for t in ts:d[str(datetime.fromtimestamp(t["entry_t"]/1000,UTC).year)].append(t)
    return {k:metrics(v) for k,v in sorted(d.items())}

def symbols(ts):
    d=defaultdict(list)
    for t in ts:d[t["symbol"]].append(t)
    return {s:metrics(d.get(s,[])) for s in SYMS}

def loo(ts):
    return {s:metrics([t for t in ts if t["symbol"]!=s]) for s in SYMS}

def summarize(ts):
    tr,ho=split(ts);sm=symbols(ts)
    return {
      "overall":metrics(ts),"train":metrics(tr),"holdout":metrics(ho),
      "years":years(ts),"symbols":sm,
      "positive_symbols":sum(v["net_r"]>0 for v in sm.values()),
      "leave_one_symbol_out":loo(ts),
    }

def train_score(s):
    tr=s["train"]
    if tr["n"]<24 or tr["avg_r"] is None or tr["avg_r"]<=0:return -1e9
    pf=tr["pf"] or 0
    if pf<1.30:return -1e9
    return tr["net_r"] - 0.35*tr["mdd_r"] + 0.5*s["positive_symbols"]

def main():
    data={};base=[]
    for sym in SYMS:
        M=core.load_15m(sym);data[sym]=M
        D=smc.aggregate_1d(M);W=ez.aggregate_weekly(D);MN=ez.aggregate_monthly(D)
        rows=ez.build_track_a(sym,M,W,MN)
        for t in rows:
            q=dict(t);q["feat"]=attach_daily(M,q);base.append(q)
        print("BASE",sym,len(rows),flush=True)

    # Important: suppress overlap AFTER adaptive 2R/3R re-simulation.
    base=ez.suppress_symbol_overlap(base)
    variants={"base":summarize(base)}

    for g in GAPS:
        for s in SLOPES:
            ts=[t for t in base if t["feat"] and t["feat"]["gap"]>=g and t["feat"]["slope50"]>=s]
            key=f"gap{g:.3f}_slope{s:.3f}"
            variants[key]=summarize(ts)
            variants[key]["params"]={"gap_min_atr":g,"ema50_slope5_min_atr":s}
            variants[key]["train_score"]=train_score(variants[key])
            print("VAR",key,json.dumps({
                "score":variants[key]["train_score"],
                "overall":variants[key]["overall"],
                "train":variants[key]["train"],
                "holdout":variants[key]["holdout"],
                "pos":variants[key]["positive_symbols"]
            }),flush=True)

    ranked=[k for k in variants if k!="base"]
    ranked.sort(key=lambda k:variants[k]["train_score"],reverse=True)
    selected=ranked[0]
    out={
      "version":"0.3",
      "purpose":"post-resimulation overlap-safe daily trend-quality plateau",
      "base_rules":"EasyChart A track; daily price/EMA20/EMA50 regime; 1H liquidity fakeout-displacement-FVG; 2R normal, 3R weekly+monthly aligned",
      "selection":"training only before 2025-01-01; holdout reported but not used for ranking",
      "selected_by_train":selected,
      "ranking":ranked,
      "variants":variants
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2),encoding="utf-8")
    print("SELECTED",selected,json.dumps(variants[selected],indent=2),flush=True)

if __name__=="__main__":main()
