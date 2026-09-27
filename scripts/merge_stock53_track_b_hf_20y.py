import json, math, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path("data/validation/stock53_20y_shards")
OUT=Path("data/validation/stock53_track_b_hf_20y_exact_touch.json")
CAP=20000.0
RISK=400.0

def stats(ts):
    n=len(ts); wins=sum(t["pnl"]>0 for t in ts); losses=sum(t["pnl"]<0 for t in ts)
    net=sum(t["r"] for t in ts); gp=sum(t["r"] for t in ts if t["r"]>0); gl=sum(t["r"] for t in ts if t["r"]<0)
    return {"closed":n,"wins":wins,"losses":losses,"win_rate":wins/n if n else None,
            "net_r":net,"avg_r":net/n if n else None,"profit_factor":gp/abs(gl) if gl<0 else None}

def grouped(ts,keyfn):
    d=defaultdict(list)
    for t in ts: d[str(keyfn(t))].append(t)
    return {k:stats(v) for k,v in sorted(d.items())}

def max_loss_streak(ts):
    c=b=0
    for t in sorted(ts,key=lambda x:(x["exit_t"],x["symbol"])):
        if t["r"]<0: c+=1; b=max(b,c)
        else: c=0
    return b

def dd(ts):
    eq=CAP; peak=CAP; mdd=0.0; mdd_r=0.0; cr=pr=0.0
    for t in sorted(ts,key=lambda x:(x["exit_t"],x["symbol"])):
        eq+=t["pnl"]; peak=max(peak,eq); mdd=max(mdd,(peak-eq)/peak if peak else 0.0)
        cr+=t["r"]; pr=max(pr,cr); mdd_r=max(mdd_r,pr-cr)
    return mdd,mdd_r

files=sorted(ROOT.glob("*.json"))
if len(files)!=5:
    raise SystemExit(f"expected 5 shard files, got {len(files)}: {files}")
shards=[json.loads(p.read_text()) for p in files]
trades=[]
errors={}
per_symbol=defaultdict(lambda:{"closed":0,"wins":0,"losses":0,"net_r":0.0})
missing_months=[]
for s in shards:
    trades.extend(s.get("trades",[]))
    missing_months.extend(s.get("data",{}).get("missing_months",[]))
    for sym,e in s.get("errors",{}).items():
        errors.setdefault(sym,[]).append({"shard":s["shard"],"error":e})
trades.sort(key=lambda x:(x["entry_t"],x["symbol"]))
for t in trades:
    q=per_symbol[t["symbol"]]; q["closed"]+=1; q["wins"]+=int(t["pnl"]>0); q["losses"]+=int(t["pnl"]<0); q["net_r"]+=t["r"]
for q in per_symbol.values():
    q["win_rate"]=q["wins"]/q["closed"] if q["closed"] else None
    q["avg_r"]=q["net_r"]/q["closed"] if q["closed"] else None

mdd,mdd_r=dd(trades)
by_year=grouped(trades,lambda t:datetime.fromtimestamp(t["entry_t"]/1000,timezone.utc).year)
by_direction=grouped(trades,lambda t:t["direction"])
ranked=sorted(({"symbol":k,**v} for k,v in per_symbol.items()),key=lambda x:x["net_r"],reverse=True)

report={
  "generated_at":datetime.now(timezone.utc).isoformat(),
  "purpose":"20-year exact-touch validation of current 53-stock universe using historical US RTH minute data",
  "period":{"evaluation_start":"2006-04-01T00:00:00+00:00","evaluation_end_exclusive":"2026-04-01T00:00:00+00:00"},
  "strategy":"Frozen Track B exact-touch; 30/30/40; TP1=>BE; TP2=>TP1; confirmed RTH 4H pivot runner",
  "symbols":shards[0]["symbols"],
  "data":{"provider":"Hugging Face mito0o852/OHLCV-1m (Finnhub-origin)",
          "available_through":"2026-03","session":"US RTH 09:30-16:00 ET",
          "source_resolution":"1m","execution_resolution":"15m",
          "split_cleanup":"common-factor overnight split detection inside each shard",
          "aliases":{"META":"FB before 2022-06-09","GOOGL":"GOOG before 2014-04-03"},
          "not_before":{"DELL":"2018-12-28","SNDK":"2025-02-24"},
          "missing_months":sorted(set(missing_months)),
          "survivorship_note":"Current 53-stock universe projected backward; constituents were not selected contemporaneously."},
  "costs":shards[0]["costs"],
  "totals":{**stats(trades),"max_drawdown_fixed_20k":mdd,"max_drawdown_r":mdd_r,
            "max_consecutive_losses":max_loss_streak(trades)},
  "by_year":by_year,
  "by_direction":by_direction,
  "breadth":{"symbols_with_trades":len(per_symbol),
             "positive_symbols":sum(v["net_r"]>0 for v in per_symbol.values()),
             "negative_symbols":sum(v["net_r"]<0 for v in per_symbol.values()),
             "flat_symbols":sum(v["net_r"]==0 for v in per_symbol.values())},
  "top_symbols":ranked[:15],
  "bottom_symbols":list(reversed(ranked[-15:])),
  "per_symbol":dict(sorted(per_symbol.items())),
  "shards":[{"shard":s["shard"],"totals":s["totals"],"errors":s["errors"]} for s in shards],
  "errors":errors,
  "trades":trades
}
OUT.parent.mkdir(parents=True,exist_ok=True)
OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({k:v for k,v in report.items() if k not in ("trades","per_symbol","errors")},ensure_ascii=False,indent=2))
