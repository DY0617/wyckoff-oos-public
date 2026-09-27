import json
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path("data/validation/stock53_regime_shards")
OUT=Path("data/validation/stock53_regime_filter_20y_comparison.json")
CAP=20000.0

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

files=sorted(ROOT.glob("*.json"))
if len(files)!=5:raise RuntimeError(f"expected 5 shards got {len(files)}")
rows=[json.loads(p.read_text()) for p in files]
names=("A_current","B_long_only","C_long_spy_regime","D_long_spy_regime_rs20")
variants={}
for name in names:
    ts=[t for r in rows for t in r["variants"][name]]
    # Entry windows are disjoint, so no duplicates should exist.
    ts.sort(key=lambda x:(x["entry_t"],x["symbol"]))
    variants[name]=pack(ts)

a=variants["A_current"]
comparison={}
for name,v in variants.items():
    comparison[name]={
      "trades_kept_pct":v["closed"]/a["closed"] if a["closed"] else None,
      "net_r_delta_vs_A":v["net_r"]-a["net_r"],
      "pf_delta_vs_A":(v["profit_factor"] or 0)-(a["profit_factor"] or 0),
      "dd_r_delta_vs_A":v["max_drawdown_r"]-a["max_drawdown_r"],
      "avg_r_delta_vs_A":(v["avg_r"] or 0)-(a["avg_r"] or 0)
    }

report={
 "generated_at":datetime.now(timezone.utc).isoformat(),
 "purpose":"pre-specified structural regime-filter comparison; no threshold optimization",
 "period":{"start":"2006-04-01","end_exclusive":"2026-04-01"},
 "definitions":rows[0]["definitions"],
 "variants":variants,
 "comparison_vs_A":comparison,
 "audit":{"missing_months":[],"shard_errors":{p.name:r["errors"] for p,r in zip(files,rows) if r["errors"]},
          "note":"Current 53-stock universe is projected backward, so survivorship/post-selection bias remains."}
}
OUT.parent.mkdir(parents=True,exist_ok=True)
OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(report,ensure_ascii=False,indent=2))
