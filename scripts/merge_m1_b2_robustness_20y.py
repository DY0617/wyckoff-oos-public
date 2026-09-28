import json
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path("data/validation/m1_b2_robustness_20y_shards")
OUT=Path("data/validation/m1_b2_robustness_20y.json")
UTC=timezone.utc
CAP=20000.0

def stats(ts):
    n=len(ts);w=sum(t["r"]>0 for t in ts);l=sum(t["r"]<0 for t in ts)
    net=sum(t["r"] for t in ts);gp=sum(t["r"] for t in ts if t["r"]>0);gl=sum(t["r"] for t in ts if t["r"]<0)
    return {"closed":n,"wins":w,"losses":l,"win_rate":w/n if n else None,
            "net_r":net,"avg_r":net/n if n else None,
            "profit_factor":gp/abs(gl) if gl<0 else None}

def risk(ts):
    cr=pr=mdd=0.0;eq=peak=CAP;mdd_pct=0.0;st=best=0
    for t in sorted(ts,key=lambda x:(x["exit_t"],x["symbol"])):
        cr+=t["r"];pr=max(pr,cr);mdd=max(mdd,pr-cr)
        eq+=t["pnl"];peak=max(peak,eq);mdd_pct=max(mdd_pct,(peak-eq)/peak if peak else 0)
        if t["r"]<0:st+=1;best=max(best,st)
        else:st=0
    return {"max_drawdown_r":mdd,"max_drawdown_fixed_20k":mdd_pct,
            "max_consecutive_losses":best}

def by_year(ts):
    d=defaultdict(list)
    for t in ts:d[str(datetime.fromtimestamp(t["entry_t"]/1000,UTC).year)].append(t)
    return {y:stats(v) for y,v in sorted(d.items())}

def pack(ts):
    yy=by_year(ts)
    return {**stats(ts),**risk(ts),
            "positive_years":sum(v["net_r"]>0 for v in yy.values()),
            "negative_years":sum(v["net_r"]<0 for v in yy.values()),
            "by_year":yy}

def window(ts,start):
    return [t for t in ts if datetime.fromtimestamp(t["entry_t"]/1000,UTC).year>=start]

files=sorted(ROOT.glob("*.json"))
if len(files)!=5:raise RuntimeError(f"expected 5 shards, got {len(files)}")
rows=[json.loads(p.read_text()) for p in files]
names=sorted(rows[0]["results"].keys())

merged={}
for name in names:
    ts=[t for r in rows for t in r["results"][name]["trades"]]
    ts.sort(key=lambda x:(x["entry_t"],x["symbol"]))
    keys=[(t["symbol"],t["entry_t"],t["signal_t"]) for t in ts]
    if len(keys)!=len(set(keys)):raise RuntimeError(f"duplicate keys in {name}")
    merged[name]={
      "allowed_symbols":rows[0]["results"][name]["allowed_symbols"],
      "excluded_symbols":rows[0]["results"][name]["excluded_symbols"],
      "full_20y":pack(ts),
      "2016_2026":pack(window(ts,2016)),
      "2022_2026":pack(window(ts,2022)),
      "2024_2026":pack(window(ts,2024)),
      "signals_seen_in_shards":sum(r["results"][name]["signals"] for r in rows),
      "cap_block_events_in_shards":sum(r["results"][name]["cap_block_events"] for r in rows)
    }

base_trades=[t for r in rows for t in r["results"]["baseline"]["trades"]]
base_trades.sort(key=lambda x:(x["entry_t"],x["symbol"]))

# Secondary diagnostic only: post-hoc LOSO on accepted baseline trades.
# It does NOT recalculate ranks/breadth/cap and is clearly labeled as such.
loso=[]
for s in sorted(set(t["symbol"] for t in base_trades)):
    xs=[t for t in base_trades if t["symbol"]!=s]
    p=pack(xs)
    loso.append({"removed_symbol":s,**p})
loso.sort(key=lambda x:x["net_r"])

# Contribution concentration of the accepted baseline state-machine portfolio.
symstats=[]
for s in sorted(set(t["symbol"] for t in base_trades)):
    p=pack([t for t in base_trades if t["symbol"]==s])
    symstats.append({"symbol":s,**p})
symstats.sort(key=lambda x:x["net_r"],reverse=True)
base_net=merged["baseline"]["full_20y"]["net_r"]

report={
 "generated_at":datetime.now(UTC).isoformat(),
 "strategy":"M1_B2_full_counterfactual_robustness",
 "period":{"start":"2006-04-01","end_exclusive":"2026-04-01"},
 "rules":rows[0]["rules"],
 "scenario_results":merged,
 "baseline_concentration":{
   "top10_net_r":sum(x["net_r"] for x in symstats[:10]),
   "top10_share_of_total_r":sum(x["net_r"] for x in symstats[:10])/base_net if base_net else None,
   "top_symbols":symstats[:15],
   "bottom_symbols":list(reversed(symstats[-15:]))
 },
 "posthoc_loso_diagnostic":{
   "note":"Accepted-trade subtraction only; does not recompute cross-sectional ranks, breadth, pending orders, or cap interactions.",
   "worst_10_after_removal":loso[:10],
   "best_10_after_removal":list(reversed(loso[-10:])),
   "all":loso
 },
 "random80_summary":{
   "scenarios":[k for k in names if k.startswith("random80_")],
   "net_r":[merged[k]["full_20y"]["net_r"] for k in names if k.startswith("random80_")],
   "profit_factor":[merged[k]["full_20y"]["profit_factor"] for k in names if k.startswith("random80_")],
   "max_drawdown_r":[merged[k]["full_20y"]["max_drawdown_r"] for k in names if k.startswith("random80_")]
 },
 "limitations":[
   "Current 53-symbol universe is projected backward, so survivorship/post-selection bias remains.",
   "Top1/3/5/10 removals are stress tests based on the already-observed baseline contributors; they are not independent OOS selections.",
   "Random-80 scenarios use fixed seeds chosen before results and always retain SPY as the market benchmark.",
   "Each scenario fully recomputes breadth, cross-sectional 60d momentum rank, pending fills, and the two-position state machine."
 ]
}
OUT.parent.mkdir(parents=True,exist_ok=True)
OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({
  "scenario_results":{k:v["full_20y"] for k,v in merged.items()},
  "random80_summary":report["random80_summary"],
  "baseline_concentration":report["baseline_concentration"],
  "posthoc_loso_worst10":loso[:10]
},ensure_ascii=False,indent=2))
