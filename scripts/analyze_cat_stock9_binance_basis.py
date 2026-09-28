import json, math, statistics, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import backtest_stock9_spot_vs_binance_same_window as src

UTC=timezone.utc
OUT=ROOT/"data/validation/cat_stock9_binance_basis_calibration.json"

def q(vals,p):
    if not vals:return None
    a=sorted(vals);i=(len(a)-1)*p;lo=math.floor(i);hi=math.ceil(i)
    if lo==hi:return a[lo]
    return a[lo]*(hi-i)+a[hi]*(i-lo)

def stats(vals):
    vals=[float(x) for x in vals if math.isfinite(float(x))]
    if not vals:return {"n":0}
    return {"n":len(vals),"mean":statistics.fmean(vals),"median":statistics.median(vals),
            "p05":q(vals,.05),"p25":q(vals,.25),"p75":q(vals,.75),"p95":q(vals,.95),
            "mean_abs":statistics.fmean(abs(x) for x in vals),"median_abs":statistics.median(abs(x) for x in vals),
            "p95_abs":q([abs(x) for x in vals],.95)}

def pearson(a,b):
    if len(a)<3:return None
    ma=statistics.fmean(a);mb=statistics.fmean(b)
    va=sum((x-ma)**2 for x in a);vb=sum((y-mb)**2 for y in b)
    if va<=0 or vb<=0:return None
    return sum((x-ma)*(y-mb) for x,y in zip(a,b))/math.sqrt(va*vb)

def daily_first_last(bars):
    mp=defaultdict(list)
    for z in src.rth_only(bars):
        d=src.day_key(z).isoformat();mp[d].append(z)
    out={}
    for d,g in mp.items():
        g=sorted(g,key=lambda x:x["t"])
        out[d]={"o":g[0]["o"],"c":g[-1]["c"]}
    return out

def main():
    hf=src.fetch_hf_warmup()
    per={};pooled_basis=[];pooled_change=[]
    for sym in src.SYMS:
        print("CALIBRATE",sym,flush=True)
        cash=src.merge_spot(hf[sym],src.fetch_getdata(sym))
        fut=src.fetch_binance_15m(sym,src.BINANCE_FIRST[sym])
        cd=daily_first_last(cash);fd=daily_first_last(fut)
        common=sorted(set(cd)&set(fd))
        rows=[];prev_basis=None;cr=[];fr=[]
        prev_c=prev_f=None
        for d in common:
            basis=(fd[d]["o"]/cd[d]["o"]-1)*10000
            chg=None if prev_basis is None else basis-prev_basis
            rows.append({"date":d,"basis_bps":basis,"basis_change_bps":chg})
            pooled_basis.append(basis)
            if chg is not None:pooled_change.append(chg)
            if prev_c is not None and prev_f is not None:
                cr.append(cd[d]["c"]/prev_c-1);fr.append(fd[d]["c"]/prev_f-1)
            prev_basis=basis;prev_c=cd[d]["c"];prev_f=fd[d]["c"]
        per[sym]={
            "common_sessions":len(common),
            "basis_bps":stats([x["basis_bps"] for x in rows]),
            "basis_change_bps":stats([x["basis_change_bps"] for x in rows if x["basis_change_bps"] is not None]),
            "daily_return_corr":pearson(cr,fr),
            "first":common[0] if common else None,"last":common[-1] if common else None
        }
    report={
      "purpose":"CAT cash-signal to Binance TradFi perpetual execution calibration",
      "definition":"basis_bps = 10000*(Binance first RTH 15m open / cash first RTH 15m open - 1); basis_change is day-over-day basis change",
      "symbols":list(src.SYMS),
      "overall":{"basis_bps":stats(pooled_basis),"basis_change_bps":stats(pooled_change)},
      "per_symbol":per,
      "interpretation_note":"Absolute basis is not treated as slippage because the perpetual can trade at a persistent fair-value premium/discount. Day-to-day basis change and return correlation are the more relevant execution-domain stability measures."
    }
    OUT.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print("FINAL",json.dumps(report,indent=2),flush=True)

if __name__=="__main__":main()
