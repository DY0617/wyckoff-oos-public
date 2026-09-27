import json
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path("data/validation/stock53_regime_extension_shards")
OUT=Path("data/validation/stock53_regime_extensions_20y_comparison.json")
CAP=20000.0
NAMES=("D_long_spy_regime_rs20","E_D_plus_breadth50","F_D_plus_spy_volshock_q90",
       "G_D_plus_cross_section_rs_top50","H_D_long_plus_bearish_short")

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

def in_period(t,start_year,end_exclusive_year):
    y=datetime.fromtimestamp(t["entry_t"]/1000,timezone.utc).year
    return start_year<=y<end_exclusive_year

files=sorted(ROOT.glob("*.json"))
if len(files)!=5:raise RuntimeError(f"expected 5 shards got {len(files)}")
rows=[json.loads(p.read_text()) for p in files]
definitions=rows[0]["definitions"]

all_trades={}
for name in NAMES:
    ts=[t for r in rows for t in r["variants"][name]]
    ts.sort(key=lambda x:(x["entry_t"],x["symbol"]))
    all_trades[name]=ts

variants={}
for name,ts in all_trades.items():
    variants[name]={
      "full_20y":pack(ts),
      "early_2006_2015":pack([t for t in ts if in_period(t,2006,2016)]),
      "late_2016_2026":pack([t for t in ts if in_period(t,2016,2027)])
    }

d=variants["D_long_spy_regime_rs20"]["full_20y"]
comparison={}
for name,v0 in variants.items():
    v=v0["full_20y"]
    comparison[name]={
      "trades_kept_vs_D":v["closed"]/d["closed"] if d["closed"] else None,
      "net_r_delta_vs_D":v["net_r"]-d["net_r"],
      "pf_delta_vs_D":(v["profit_factor"] or 0)-(d["profit_factor"] or 0),
      "avg_r_delta_vs_D":(v["avg_r"] or 0)-(d["avg_r"] or 0),
      "dd_r_delta_vs_D":v["max_drawdown_r"]-d["max_drawdown_r"]
    }

report={
 "generated_at":datetime.now(timezone.utc).isoformat(),
 "purpose":"pre-specified extensions to D; no threshold search",
 "period":{"start":"2006-04-01","end_exclusive":"2026-04-01"},
 "definitions":definitions,
 "variants":variants,
 "comparison_vs_D":comparison,
 "audit":{"shard_errors":{p.name:r["errors"] for p,r in zip(files,rows) if r["errors"]},
          "months_loaded":[{"file":p.name,"months_loaded":r["months_loaded"],"warmup_start":r["warmup_start"]} for p,r in zip(files,rows)],
          "note":"Current 53-stock universe projected backward; survivorship/post-selection bias remains. Candidate definitions were chosen after observing D, so this is hypothesis testing, not pristine OOS proof."}
}
OUT.parent.mkdir(parents=True,exist_ok=True)
OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"comparison_vs_D":comparison,
                  "full":{k:v["full_20y"] for k,v in variants.items()},
                  "early":{k:v["early_2006_2015"] for k,v in variants.items()},
                  "late":{k:v["late_2016_2026"] for k,v in variants.items()}},ensure_ascii=False,indent=2))
