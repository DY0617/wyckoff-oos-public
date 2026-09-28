import json
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path("data/validation/m1_b2_rs_breadth20_20y_shards")
OUT=Path("data/validation/m1_b2_rs_breadth20_20y.json")
UTC=timezone.utc
CAP=20000.0
def stats(ts):
    n=len(ts);w=sum(t["r"]>0 for t in ts);l=sum(t["r"]<0 for t in ts)
    net=sum(t["r"] for t in ts);gp=sum(t["r"] for t in ts if t["r"]>0);gl=sum(t["r"] for t in ts if t["r"]<0)
    return {"closed":n,"wins":w,"losses":l,"win_rate":w/n if n else None,"net_r":net,
            "avg_r":net/n if n else None,"profit_factor":gp/abs(gl) if gl<0 else None}
def risk(ts):
    cr=pr=mdd=0.0;eq=peak=CAP;mdd_pct=0.0;st=best=0
    for t in sorted(ts,key=lambda x:(x["exit_t"],x["symbol"])):
        cr+=t["r"];pr=max(pr,cr);mdd=max(mdd,pr-cr)
        eq+=t["pnl"];peak=max(peak,eq);mdd_pct=max(mdd_pct,(peak-eq)/peak if peak else 0)
        if t["r"]<0:st+=1;best=max(best,st)
        else:st=0
    return {"max_drawdown_r":mdd,"max_drawdown_fixed_20k":mdd_pct,"max_consecutive_losses":best}
def by_year(ts):
    d=defaultdict(list)
    for t in ts:d[str(datetime.fromtimestamp(t["entry_t"]/1000,UTC).year)].append(t)
    return {y:stats(v) for y,v in sorted(d.items())}
def pack(ts):
    yy=by_year(ts)
    return {**stats(ts),**risk(ts),"positive_years":sum(v["net_r"]>0 for v in yy.values()),
            "negative_years":sum(v["net_r"]<0 for v in yy.values()),"by_year":yy}
def window(ts,start):
    return [t for t in ts if datetime.fromtimestamp(t["entry_t"]/1000,UTC).year>=start]
files=sorted(ROOT.glob("*.json"))
if len(files)!=5:raise RuntimeError(f"expected 5 shards got {len(files)}")
rows=[json.loads(p.read_text()) for p in files]
out={}
for name in ("rs_slope","rs_slope_breadth20_nonfalling"):
    ts=[t for r in rows for t in r["results"][name]["trades"]]
    ts.sort(key=lambda x:(x["entry_t"],x["symbol"]))
    out[name]={"full_20y":pack(ts),"2016_2026":pack(window(ts,2016)),
               "2022_2026":pack(window(ts,2022)),"2024_2026":pack(window(ts,2024))}
base=out["rs_slope"]["full_20y"];x=out["rs_slope_breadth20_nonfalling"]["full_20y"]
report={"generated_at":datetime.now(UTC).isoformat(),"results":out,
        "comparison":{"delta_trades":x["closed"]-base["closed"],"delta_net_r":x["net_r"]-base["net_r"],
                      "delta_pf":x["profit_factor"]-base["profit_factor"],
                      "delta_mdd_r":x["max_drawdown_r"]-base["max_drawdown_r"],
                      "delta_max_loss_streak":x["max_consecutive_losses"]-base["max_consecutive_losses"]},
        "note":"Exploratory filter selected after diagnosing historical loss-streak regimes; treat as in-sample hypothesis, not confirmed OOS improvement."}
OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
