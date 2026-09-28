import json
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path("data/validation/stock53_e_20y_corrected_shards")
OUT=Path("data/validation/stock53_e_20y_corrected.json")
CAP=20000.0

def stats(ts):
    n=len(ts);w=sum(t["pnl"]>0 for t in ts);l=sum(t["pnl"]<0 for t in ts)
    net=sum(t["r"] for t in ts);gp=sum(t["r"] for t in ts if t["r"]>0);gl=sum(t["r"] for t in ts if t["r"]<0)
    return {"closed":n,"wins":w,"losses":l,"win_rate":w/n if n else None,
            "net_r":net,"avg_r":net/n if n else None,"profit_factor":gp/abs(gl) if gl<0 else None}

def risk(ts):
    cr=pr=mdd_r=0.0;eq=peak=CAP;mdd_pct=0.0;st=best=0
    for t in sorted(ts,key=lambda x:(x["exit_t"],x["symbol"])):
        cr+=t["r"];pr=max(pr,cr);mdd_r=max(mdd_r,pr-cr)
        eq+=t["pnl"];peak=max(peak,eq);mdd_pct=max(mdd_pct,(peak-eq)/peak if peak else 0)
        if t["r"]<0:st+=1;best=max(best,st)
        else:st=0
    return {"max_drawdown_r":mdd_r,"max_drawdown_fixed_20k":mdd_pct,"max_consecutive_losses":best}

def pack(ts):
    d=defaultdict(list)
    for t in ts:d[str(datetime.fromtimestamp(t["entry_t"]/1000,timezone.utc).year)].append(t)
    byy={y:stats(v) for y,v in sorted(d.items())}
    return {**stats(ts),**risk(ts),
            "positive_years":sum(v["net_r"]>0 for v in byy.values()),
            "negative_years":sum(v["net_r"]<0 for v in byy.values()),
            "by_year":byy}

def window(ts,start):
    return [t for t in ts if datetime.fromtimestamp(t["entry_t"]/1000,timezone.utc).year>=start]

files=sorted(ROOT.glob("*.json"))
if len(files)!=5:raise RuntimeError(f"expected 5 shards got {len(files)}")
rows=[json.loads(p.read_text()) for p in files]
base=[t for r in rows for t in r["trades"]]
e=[t for r in rows for t in r["e_trades"]]
base.sort(key=lambda x:(x["entry_t"],x["symbol"]))
e.sort(key=lambda x:(x["entry_t"],x["symbol"]))

report={
 "generated_at":datetime.now(timezone.utc).isoformat(),
 "period":{"start":"2006-04-01","end_exclusive":"2026-04-01"},
 "split_fix":"common-factor split/spinoff-like discontinuity detection uses abs(magnitude/factor - 1) <= 0.08",
 "e_definition":rows[0]["e_definition"],
 "base":{
   "full_20y":pack(base),"2016_2026":pack(window(base,2016)),
   "2022_2026":pack(window(base,2022)),"2024_2026":pack(window(base,2024))
 },
 "E":{
   "full_20y":pack(e),"2016_2026":pack(window(e,2016)),
   "2022_2026":pack(window(e,2022)),"2024_2026":pack(window(e,2024))
 },
 "old_reference":{"E_full_20y":{"closed":325,"net_r":61.1682,"profit_factor":1.43801,"max_drawdown_r":11.45}},
 "shards":[{"shard":r["shard"],"base_totals":r["totals"],"e_totals":r["e_totals"],"errors":r["errors"]} for r in rows],
 "limitations":[
   "Current 53-symbol universe is projected backward, so survivorship/post-selection bias remains.",
   "The discontinuity correction is heuristic; it repairs common split/spinoff-like jumps but is not a full corporate-action total-return database."
 ],
 "e_trades":e
}
OUT.parent.mkdir(parents=True,exist_ok=True)
OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"base":report["base"],"E":report["E"],"old_reference":report["old_reference"]},ensure_ascii=False,indent=2))
