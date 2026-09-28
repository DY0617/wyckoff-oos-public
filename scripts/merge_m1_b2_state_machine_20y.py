import json
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path("data/validation/m1_b2_state_machine_20y_shards")
OUT=Path("data/validation/m1_b2_state_machine_20y.json")
EFILE=Path("data/validation/stock53_filter_factorial_20y.json")
M1FILE=Path("data/validation/m1_momentum_pullback_20y.json")
UTC=timezone.utc
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

def window(ts,start_year):
    return [t for t in ts if datetime.fromtimestamp(t["entry_t"]/1000,UTC).year>=start_year]

files=sorted(ROOT.glob("*.json"))
if len(files)!=5:raise RuntimeError(f"expected 5 shards got {len(files)}")
rows=[json.loads(p.read_text()) for p in files]
trades=[t for r in rows for t in r["trades"]]
trades.sort(key=lambda x:(x["entry_t"],x["symbol"]))

# Boundary integrity: entry windows are disjoint, so exact duplicate keys should never occur.
keys=[(t["symbol"],t["entry_t"],t["signal_t"]) for t in trades]
if len(keys)!=len(set(keys)):raise RuntimeError("duplicate trade keys across shards")

by_symbol={}
for s in sorted(set(t["symbol"] for t in trades)):
    by_symbol[s]=pack([t for t in trades if t["symbol"]==s])
ranked=sorted(({"symbol":s,**v} for s,v in by_symbol.items()),key=lambda x:x["net_r"],reverse=True)

e_ref=None
if EFILE.exists():
    e=json.loads(EFILE.read_text())["variants"]["CRM_E_spy_rs_breadth"]
    e_ref={"full_20y":e["full_20y"],"2016_2026":e["late_2016_2026"],
           "2022_2026":e["recent_2022_2026"],"2024_2026":e["recent_2024_2026"]}

m1_ref=None
if M1FILE.exists():
    m=json.loads(M1FILE.read_text())
    m1_ref={"full_20y":m["results"]["full_20y"],
            "2016_2026":m["results"]["2016_2026"],
            "2022_2026":m["results"]["2022_2026"],
            "2024_2026":m["results"]["2024_2026"]}

report={
 "generated_at":datetime.now(UTC).isoformat(),
 "strategy":"M1_B2_full_portfolio_state_machine",
 "period":{"start":"2006-04-01","end_exclusive":"2026-04-01"},
 "rules":rows[0]["rules"],
 "results":{
   "full_20y":pack(trades),
   "2016_2026":pack(window(trades,2016)),
   "2022_2026":pack(window(trades,2022)),
   "2024_2026":pack(window(trades,2024))
 },
 "comparison":{"E53":e_ref,"M1_unconstrained":m1_ref},
 "execution_audit":{
   "signals_seen_in_shards":sum(r["signals"] for r in rows),
   "cap_block_events_in_shards":sum(r["cap_block_events"] for r in rows),
   "shards":[{"shard":r["shard"],"signals":r["signals"],"cap_block_events":r["cap_block_events"],"totals":r["totals"]} for r in rows]
 },
 "concentration":{
   "symbols_with_trades":len(by_symbol),
   "top10_net_r":sum(x["net_r"] for x in ranked[:10]),
   "top_symbols":ranked[:15],
   "bottom_symbols":list(reversed(ranked[-15:]))
 },
 "by_symbol":by_symbol,
 "limitations":[
   "Current 53-symbol universe is projected backward, so survivorship/post-selection bias remains.",
   "Each 4-year shard is seeded with 140 calendar days of portfolio-state pre-roll (except the first global shard) and 420 days of indicator warmup.",
   "Same-15m simultaneous admissions are prioritized by signal-day 60d return; intrabar ordering inside a 15m candle is otherwise unavailable.",
   "Risk is expressed in fixed 1R-per-position units; dynamic equity compounding is not modeled."
 ],
 "trades":trades
}
OUT.parent.mkdir(parents=True,exist_ok=True)
OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"results":report["results"],"comparison":report["comparison"],"execution_audit":report["execution_audit"],"concentration":report["concentration"]},ensure_ascii=False,indent=2))
