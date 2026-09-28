import json
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path("data/validation/m1_risk_control_shards")
OUT=Path("data/validation/m1_risk_controls_20y_v2.json")
UTC=timezone.utc

def stats(ts):
    ts=sorted(ts,key=lambda x:(x["exit_t"],x["symbol"]))
    n=len(ts);w=sum(x["r"]>0 for x in ts);l=sum(x["r"]<0 for x in ts)
    net=sum(x["r"] for x in ts);gp=sum(x["r"] for x in ts if x["r"]>0);gl=sum(x["r"] for x in ts if x["r"]<0)
    cr=pr=mdd=0.0;st=best=0
    for x in ts:
        cr+=x["r"];pr=max(pr,cr);mdd=max(mdd,pr-cr)
        if x["r"]<0:st+=1;best=max(best,st)
        else:st=0
    return {"closed":n,"wins":w,"losses":l,"win_rate":w/n if n else None,
            "net_r":net,"avg_r":net/n if n else None,"profit_factor":gp/abs(gl) if gl<0 else None,
            "max_drawdown_r":mdd,"max_consecutive_losses":best}
def by_year(ts):
    d=defaultdict(list)
    for t in ts:d[str(datetime.fromtimestamp(t["entry_t"]/1000,UTC).year)].append(t)
    return {y:stats(v) for y,v in sorted(d.items())}
def pack(ts):
    yy=by_year(ts)
    return {**stats(ts),"positive_years":sum(v["net_r"]>0 for v in yy.values()),
            "negative_years":sum(v["net_r"]<0 for v in yy.values()),"by_year":yy}
def cap(ts,n):
    acc=[]
    for t in sorted(ts,key=lambda x:(x["entry_t"],-x.get("signal_ret60",0),x["symbol"])):
        active=sum(1 for a in acc if a["entry_t"]<=t["entry_t"]<a["exit_t"])
        if active<n:acc.append(t)
    return acc
def samefill(ts,n):
    g=defaultdict(list)
    for t in ts:g[t["entry_t"]].append(t)
    out=[]
    for _,xs in sorted(g.items()):
        out.extend(sorted(xs,key=lambda x:(-x.get("signal_ret60",0),x["symbol"]))[:n])
    return sorted(out,key=lambda x:(x["entry_t"],x["symbol"]))

files=sorted(ROOT.glob("*.json"))
if len(files)!=5:raise RuntimeError(f"expected 5 shards got {len(files)}")
trades=[t for p in files for t in json.loads(p.read_text())["trades"]]
trades.sort(key=lambda x:(x["entry_t"],x["symbol"]))
b=[t for t in trades if t.get("breadth") is not None and t["breadth"]>=.50]
variants={
 "M1_base":trades,
 "M1_breadth50":b,
 "M1_cap3":cap(trades,3),
 "M1_breadth50_cap3":cap(b,3),
 "M1_breadth50_same_fill_top1":samefill(b,1),
 "M1_breadth50_same_fill_top2":samefill(b,2),
 "M1_breadth50_same_fill_top3":samefill(b,3)
}
report={
 "generated_at":datetime.now(UTC).isoformat(),
 "results":{k:pack(v) for k,v in variants.items()},
 "recent":{k:{
   "2016_2026":pack([t for t in v if datetime.fromtimestamp(t["entry_t"]/1000,UTC).year>=2016]),
   "2022_2026":pack([t for t in v if datetime.fromtimestamp(t["entry_t"]/1000,UTC).year>=2022])
 } for k,v in variants.items()},
 "definitions":{
  "breadth50":"signal-day completed RTH breadth >=50% above EMA50 in current 53-symbol universe",
  "cap3":"conservative post-filter max 3 concurrent accepted positions; simultaneous fills prioritize signal_ret60",
  "same_fill_topN":"only exact same 15m fill timestamp ranked by signal_ret60; avoids ex-post future fill knowledge"
 },
 "notes":[
   "Post-filter tests are conservative: skipped trades do not generate replacement later same-symbol signals.",
   "Breadth threshold 50% and concurrency cap 3 were fixed before results."
 ]
}
OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({"results":report["results"],"recent":report["recent"]},ensure_ascii=False,indent=2))
