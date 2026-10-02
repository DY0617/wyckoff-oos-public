import json,statistics
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

UTC=timezone.utc
ROOT=Path("data/validation/elliott_v4_stock20y_shards")
OUT=Path("data/validation/elliott_wave3_v4_stock_oos25_20y.json")

def metrics(ts):
    o=sorted(ts,key=lambda z:(z["exit_t"],z["symbol"]));rs=[x["r"] for x in o]
    pos=[r for r in rs if r>0];neg=[r for r in rs if r<0]
    eq=peak=0.;dd=0.;cur=mx=0
    for r in rs:
        eq+=r;peak=max(peak,eq);dd=min(dd,eq-peak)
        if r<0:cur+=1;mx=max(mx,cur)
        else:cur=0
    return {"trades":len(o),"win_rate":len(pos)/len(o) if o else None,"total_r":sum(rs),
        "avg_r":statistics.fmean(rs) if rs else None,"profit_factor":sum(pos)/abs(sum(neg)) if neg else None,
        "max_drawdown_r":dd,"max_losing_streak":mx,
        "tp1_hit_rate":sum(t["tp1_hit"] for t in o)/len(o) if o else None,
        "tp2_hit_rate":sum(t["tp2_hit"] for t in o)/len(o) if o else None}

def grouped(ts,key):
    d=defaultdict(list)
    for t in ts:d[str(t[key])].append(t)
    return {k:metrics(v) for k,v in sorted(d.items())}

def year(t):return datetime.fromtimestamp(t["entry_t"]/1000,UTC).year

files=sorted(ROOT.glob("shard_*.json"))
if len(files)!=5:raise RuntimeError(f"expected 5 shards got {len(files)}")
shards=[json.loads(p.read_text()) for p in files]
trades=[]
for s in shards:trades.extend(s["trades"])
trades.sort(key=lambda x:(x["entry_t"],x["symbol"]))

rolling5={}
for y in range(2006,2022):
    q=[t for t in trades if y<=year(t)<y+5]
    rolling5[f"{y}-{y+4}"]=metrics(q)

wf=[]
for test_y in range(2011,2026):
    train=[t for t in trades if test_y-5<=year(t)<test_y]
    test=[t for t in trades if year(t)==test_y]
    wf.append({"train":f"{test_y-5}-{test_y-1}","test":str(test_y),
               "train_metrics":metrics(train),"test_metrics":metrics(test)})

byreg=grouped(trades,"regime")
byyear=defaultdict(list);bysym=defaultdict(list)
for t in trades:
    byyear[str(year(t))].append(t);bysym[t["symbol"]].append(t)

folds=[{"period":[s["shard"]["eval_start"],s["shard"]["eval_end_exclusive"]],"metrics":s["summary"]} for s in shards]
positive_years=sum(metrics(v)["total_r"]>0 for v in byyear.values())
negative_years=sum(metrics(v)["total_r"]<0 for v in byyear.values())

report={
 "strategy":"Elliott Wave 3 v4 frozen — US Stock OOS25 RTH 1H LONG 20Y",
 "period":{"start":"2006-04-01","end_exclusive":"2026-04-01"},
 "summary":metrics(trades),
 "non_overlapping_4y_folds":folds,
 "by_year":{k:metrics(v) for k,v in sorted(byyear.items())},
 "year_breadth":{"positive_years":positive_years,"negative_years":negative_years},
 "by_regime":byreg,
 "by_symbol":{k:metrics(v) for k,v in sorted(bysym.items())},
 "rolling_5y":rolling5,
 "walk_forward_frozen_rule":wf,
 "notes":[
  "Rules are frozen; the walk-forward table uses each prior 5y window only as a stability reference and does not re-optimize parameters.",
  "This is a historical regime stress test, not pristine temporal OOS, because the strategy was selected using recent-era results.",
  "The 25-name universe is a present-day selected universe projected backward and therefore carries survivorship bias.",
  "SPY regime is descriptive only: BULL=close>EMA200 and EMA200 rising over 20 sessions; BEAR=close<EMA200 and EMA200 falling; MIXED otherwise."
 ],
 "trades":trades
}
OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(report,indent=2),encoding="utf-8")
print(json.dumps({k:v for k,v in report.items() if k!="trades"},indent=2))
