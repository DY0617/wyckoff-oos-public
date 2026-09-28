import json
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path("data/validation/m1_momentum_pullback_20y_shards")
OUT=Path("data/validation/m1_momentum_pullback_20y.json")
EFILE=Path("data/validation/stock53_filter_factorial_20y.json")
CAP=20000.0

def stats(ts):
    n=len(ts);w=sum(t["r"]>0 for t in ts);l=sum(t["r"]<0 for t in ts)
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

def window(ts,start_year):
    return [t for t in ts if datetime.fromtimestamp(t["entry_t"]/1000,timezone.utc).year>=start_year]

files=sorted(ROOT.glob("*.json"))
if len(files)!=5:raise RuntimeError(f"expected 5 shards got {len(files)}")
rows=[json.loads(p.read_text()) for p in files]
trades=[t for r in rows for t in r["trades"]]
trades.sort(key=lambda x:(x["entry_t"],x["symbol"]))

by_symbol={}
for s in sorted(set(t["symbol"] for t in trades)):
    by_symbol[s]=pack([t for t in trades if t["symbol"]==s])
ranked=sorted(({"symbol":s,**v} for s,v in by_symbol.items()),key=lambda x:x["net_r"],reverse=True)
top10_sum=sum(x["net_r"] for x in ranked[:10])
total=sum(t["r"] for t in trades)

e_ref=None
if EFILE.exists():
    e=json.loads(EFILE.read_text())
    v=e["variants"]["CRM_E_spy_rs_breadth"]
    e_ref={
      "full_20y":v["full_20y"],
      "2016_2026":v["late_2016_2026"],
      "2022_2026":v["recent_2022_2026"],
      "2024_2026":v["recent_2024_2026"]
    }

report={
 "generated_at":datetime.now(timezone.utc).isoformat(),
 "strategy":"M1_v1_cross_section_momentum_pullback",
 "locked_rules":rows[0]["locked_rules"],
 "period":{"start":"2006-04-01","end_exclusive":"2026-04-01"},
 "results":{
   "full_20y":pack(trades),
   "2016_2026":pack(window(trades,2016)),
   "2022_2026":pack(window(trades,2022)),
   "2024_2026":pack(window(trades,2024))
 },
 "comparison_E53":e_ref,
 "concentration":{
   "symbols_with_trades":len(by_symbol),
   "top10_net_r":top10_sum,
   "top10_share_of_total_r":top10_sum/total if total else None,
   "top_symbols":ranked[:15],
   "bottom_symbols":list(reversed(ranked[-15:]))
 },
 "by_symbol":by_symbol,
 "shards":[{"shard":r["shard"],"signals":r["signals"],"totals":r["totals"]} for r in rows],
 "limitations":[
   "Current 53-symbol universe is projected backward, so survivorship/post-selection bias remains.",
   "M1 rules were locked before this run and were not tuned on the resulting 20-year performance.",
   "No portfolio-wide concurrency cap is applied here; figures measure raw strategy edge in R units.",
   "Cross-sectional eligibility naturally changes as later-listed symbols acquire sufficient history."
 ],
 "trades":trades
}
OUT.parent.mkdir(parents=True,exist_ok=True)
OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"results":report["results"],"comparison_E53":e_ref,"concentration":report["concentration"]},ensure_ascii=False,indent=2))
