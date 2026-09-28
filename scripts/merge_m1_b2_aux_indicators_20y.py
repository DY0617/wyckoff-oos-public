import json
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path("data/validation/m1_b2_aux_indicators_20y_shards")
OUT=Path("data/validation/m1_b2_aux_indicators_20y.json")
UTC=timezone.utc
CAP=20000.0

def stats(ts):
    n=len(ts);w=sum(t["r"]>0 for t in ts);l=sum(t["r"]<0 for t in ts)
    net=sum(t["r"] for t in ts);gp=sum(t["r"] for t in ts if t["r"]>0);gl=sum(t["r"] for t in ts if t["r"]<0)
    return {"closed":n,"wins":w,"losses":l,"win_rate":w/n if n else None,
            "net_r":net,"avg_r":net/n if n else None,"profit_factor":gp/abs(gl) if gl<0 else None}

def risk(ts):
    ordered=sorted(ts,key=lambda x:(x["exit_t"],x["symbol"]))
    cr=pr=mdd=0.0;eq=peak=CAP;mdd_pct=0.0;st=best=0
    for t in ordered:
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
if len(files)!=5:raise RuntimeError(f"expected 5 shards got {len(files)}")
rows=[json.loads(p.read_text()) for p in files]
names=sorted(rows[0]["results"])

out={}
for name in names:
    ts=[t for r in rows for t in r["results"][name]["trades"]]
    ts.sort(key=lambda x:(x["entry_t"],x["symbol"]))
    keys=[(t["symbol"],t["entry_t"],t["signal_t"]) for t in ts]
    if len(keys)!=len(set(keys)):raise RuntimeError(f"duplicate trade keys {name}")
    out[name]={
      "full_20y":pack(ts),
      "2016_2026":pack(window(ts,2016)),
      "2022_2026":pack(window(ts,2022)),
      "2024_2026":pack(window(ts,2024)),
      "signals_seen_in_shards":sum(r["results"][name]["signals"] for r in rows),
      "cap_block_events_in_shards":sum(r["results"][name]["cap_block_events"] for r in rows)
    }

base=out["baseline"]["full_20y"]
comparison={}
for name,v in out.items():
    x=v["full_20y"]
    comparison[name]={
      "delta_trades":x["closed"]-base["closed"],
      "delta_net_r":x["net_r"]-base["net_r"],
      "delta_avg_r":x["avg_r"]-base["avg_r"],
      "delta_pf":(x["profit_factor"]-base["profit_factor"]) if x["profit_factor"] is not None and base["profit_factor"] is not None else None,
      "delta_mdd_r":x["max_drawdown_r"]-base["max_drawdown_r"],
      "delta_max_loss_streak":x["max_consecutive_losses"]-base["max_consecutive_losses"]
    }

# A strict predeclared success screen; descriptive only, not used to tune thresholds.
success=[]
for name,v in out.items():
    if name=="baseline":continue
    x=v["full_20y"]
    if x["closed"]>=200 and x["net_r"]>=130 and x["profit_factor"] is not None and x["profit_factor"]>=2.30 and x["avg_r"]>=0.55 and x["max_consecutive_losses"]<=8:
        success.append(name)

report={
 "generated_at":datetime.now(UTC).isoformat(),
 "strategy":"M1_B2_aux_indicators",
 "period":{"start":"2006-04-01","end_exclusive":"2026-04-01"},
 "fixed_filters":rows[0]["fixed_filters"],
 "results":out,
 "comparison_vs_baseline":comparison,
 "predeclared_success_screen":{
   "criteria":"closed>=200, net_r>=130, PF>=2.30, avg_r>=0.55, max_consecutive_losses<=8",
   "passing":success
 },
 "validation":{
   "expected_baseline":{"closed":302,"net_r":156.4555769715374,"profit_factor":2.149909847763946,
                        "max_drawdown_r":12.522868732618235,"max_consecutive_losses":11},
   "note":"Baseline should reproduce the previously validated M1-B2 full state-machine result."
 },
 "limitations":[
   "Current 53-symbol universe is projected backward, so survivorship/post-selection bias remains.",
   "All indicator thresholds were fixed before this run; no parameter sweep is performed.",
   "All filters use only the completed signal-day data and earlier information.",
   "RSI and MACD are included as overlap/control indicators, not because they were expected to be independent alpha sources."
 ]
}
OUT.parent.mkdir(parents=True,exist_ok=True)
OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"results":{k:v["full_20y"] for k,v in out.items()},
                  "comparison_vs_baseline":comparison,
                  "predeclared_success_screen":report["predeclared_success_screen"],
                  "validation":report["validation"]},ensure_ascii=False,indent=2))
