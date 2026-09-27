import json
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path("data/validation/stock53_filter_factorial_shards")
OUT=Path("data/validation/stock53_filter_factorial_20y.json")
CAP=20000.0
NAMES=("A_current","B_long_only","C_spy_only","R_rs_only","M_breadth_only",
       "CR_D_spy_rs","CM_spy_breadth","RM_rs_breadth","CRM_E_spy_rs_breadth")

def stats(ts):
    n=len(ts);w=sum(t["pnl"]>0 for t in ts);l=sum(t["pnl"]<0 for t in ts)
    net=sum(t["r"] for t in ts);gp=sum(t["r"] for t in ts if t["r"]>0);gl=sum(t["r"] for t in ts if t["r"]<0)
    return {"closed":n,"wins":w,"losses":l,"win_rate":w/n if n else None,
            "net_r":net,"avg_r":net/n if n else None,"profit_factor":gp/abs(gl) if gl<0 else None}

def risk_stats(ts):
    eq=peak=CAP;cr=pr=0.0;mdd=mr=0.0;streak=best=0
    for t in sorted(ts,key=lambda x:(x["exit_t"],x["symbol"])):
        eq+=t["pnl"];peak=max(peak,eq);mdd=max(mdd,(peak-eq)/peak if peak else 0)
        cr+=t["r"];pr=max(pr,cr);mr=max(mr,pr-cr)
        if t["r"]<0:streak+=1;best=max(best,streak)
        else:streak=0
    return {"max_drawdown_fixed_20k":mdd,"max_drawdown_r":mr,"max_consecutive_losses":best}

def by_year(ts):
    d=defaultdict(list)
    for t in ts:d[str(datetime.fromtimestamp(t["entry_t"]/1000,timezone.utc).year)].append(t)
    return {k:stats(v) for k,v in sorted(d.items())}

def pack(ts):
    ys=by_year(ts)
    return {**stats(ts),**risk_stats(ts),
            "positive_years":sum(v["net_r"]>0 for v in ys.values()),
            "negative_years":sum(v["net_r"]<0 for v in ys.values()),
            "by_year":ys}

def period(ts,start,end_exclusive):
    return [t for t in ts if start<=datetime.fromtimestamp(t["entry_t"]/1000,timezone.utc).year<end_exclusive]

files=sorted(ROOT.glob("*.json"))
if len(files)!=5:raise RuntimeError(f"expected 5 shards got {len(files)}")
rows=[json.loads(p.read_text()) for p in files]
all_trades={}
for name in NAMES:
    ts=[t for r in rows for t in r["variants"][name]]
    ts.sort(key=lambda x:(x["entry_t"],x["symbol"]))
    all_trades[name]=ts

variants={}
for name,ts in all_trades.items():
    variants[name]={
      "full_20y":pack(ts),
      "late_2016_2026":pack(period(ts,2016,2027)),
      "recent_2022_2026":pack(period(ts,2022,2027)),
      "recent_2024_2026":pack(period(ts,2024,2027)),
      "recent_2025_2026":pack(period(ts,2025,2027))
    }

base=variants["B_long_only"]["full_20y"]
comparison={}
for name,v0 in variants.items():
    v=v0["full_20y"]
    comparison[name]={
      "trades_kept_vs_long":v["closed"]/base["closed"] if base["closed"] else None,
      "net_r_delta_vs_long":v["net_r"]-base["net_r"],
      "pf_delta_vs_long":(v["profit_factor"] or 0)-(base["profit_factor"] or 0),
      "avg_r_delta_vs_long":(v["avg_r"] or 0)-(base["avg_r"] or 0),
      "dd_r_delta_vs_long":v["max_drawdown_r"]-base["max_drawdown_r"]
    }

report={
 "generated_at":datetime.now(timezone.utc).isoformat(),
 "purpose":"factorial decomposition of SPY regime / relative strength / breadth filters; fixed definitions, no threshold search",
 "period":{"start":"2006-04-01","end_exclusive":"2026-04-01"},
 "definitions":rows[0]["definitions"],
 "variants":variants,
 "comparison_vs_long_only":comparison,
 "audit":{"shard_errors":{p.name:r["errors"] for p,r in zip(files,rows) if r["errors"]},
          "months_loaded":[{"file":p.name,"months_loaded":r["months_loaded"]} for p,r in zip(files,rows)],
          "note":"Current 53-symbol universe projected backward; survivorship/post-selection bias remains. Breadth threshold fixed at 50%; filters are evaluated using only completed RTH daily bars prior to entry."}
}
OUT.parent.mkdir(parents=True,exist_ok=True)
OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({
  "full":{k:v["full_20y"] for k,v in variants.items()},
  "late":{k:v["late_2016_2026"] for k,v in variants.items()},
  "recent22":{k:v["recent_2022_2026"] for k,v in variants.items()},
  "comparison":comparison
},ensure_ascii=False,indent=2))
