import json
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path("data/validation/stock30_vs_50_e_20y_shards")
OUT=Path("data/validation/stock30_vs_stock50_e_20y.json")
CAP=20000.0

def stats(ts):
    n=len(ts);w=sum(t["pnl"]>0 for t in ts);l=sum(t["pnl"]<0 for t in ts)
    net=sum(t["r"] for t in ts);gp=sum(t["r"] for t in ts if t["r"]>0);gl=sum(t["r"] for t in ts if t["r"]<0)
    return {"closed":n,"wins":w,"losses":l,"win_rate":w/n if n else None,
            "net_r":net,"avg_r":net/n if n else None,"profit_factor":gp/abs(gl) if gl<0 else None}

def risk(ts):
    eq=peak=CAP;cr=pr=0.0;mdd_pct=mdd_r=0.0;st=best=0
    for t in sorted(ts,key=lambda x:(x["exit_t"],x["symbol"])):
        eq+=t["pnl"];peak=max(peak,eq);mdd_pct=max(mdd_pct,(peak-eq)/peak if peak else 0.0)
        cr+=t["r"];pr=max(pr,cr);mdd_r=max(mdd_r,pr-cr)
        if t["r"]<0:st+=1;best=max(best,st)
        else:st=0
    return {"max_drawdown_fixed_20k":mdd_pct,"max_drawdown_r":mdd_r,"max_consecutive_losses":best}

def by_year(ts):
    d=defaultdict(list)
    for t in ts:d[str(datetime.fromtimestamp(t["entry_t"]/1000,timezone.utc).year)].append(t)
    return {y:stats(v) for y,v in sorted(d.items())}

def pack(ts):
    ys=by_year(ts)
    return {**stats(ts),**risk(ts),
            "positive_years":sum(v["net_r"]>0 for v in ys.values()),
            "negative_years":sum(v["net_r"]<0 for v in ys.values()),
            "by_year":ys}

files=sorted(ROOT.glob("*.json"))
if len(files)!=5:raise RuntimeError(f"expected 5 shards got {len(files)}")
rows=[json.loads(p.read_text()) for p in files]

out={}
for name in ("stock30","stock50","stock53_control"):
    base=[];e=[]
    for r in rows:
        base.extend(r["variants"][name]["base_trades"])
        e.extend(r["variants"][name]["e_trades"])
    base.sort(key=lambda x:(x["entry_t"],x["symbol"]))
    e.sort(key=lambda x:(x["entry_t"],x["symbol"]))
    out[name]={"base":pack(base),"E":pack(e)}

# Recent windows to judge whether full-period behavior persists.
def window(ts,start_year):
    return [t for t in ts if datetime.fromtimestamp(t["entry_t"]/1000,timezone.utc).year>=start_year]

recent={}
for name in ("stock30","stock50","stock53_control"):
    e=[t for r in rows for t in r["variants"][name]["e_trades"]]
    recent[name]={
      "2016_2026":pack(window(e,2016)),
      "2022_2026":pack(window(e,2022)),
      "2024_2026":pack(window(e,2024))
    }

# 30-only ten-symbol contribution under E.
missing10=set(rows[0]["universes"]["stock30_only_missing10"])
e30=[t for r in rows for t in r["variants"]["stock30"]["e_trades"]]
e30_only=[t for t in e30 if t["symbol"] in missing10]
e30_common=[t for t in e30 if t["symbol"] not in missing10]
by_symbol={}
for s in sorted(missing10):
    xs=[t for t in e30_only if t["symbol"]==s]
    if xs:by_symbol[s]=pack(xs)

report={
 "generated_at":datetime.now(timezone.utc).isoformat(),
 "period":{"start":"2006-04-01","end_exclusive":"2026-04-01"},
 "definition_E":rows[0]["definition_E"],
 "universes":rows[0]["universes"],
 "results":out,
 "recent_windows":recent,
 "stock30_e_decomposition":{
   "shared20":pack(e30_common),
   "stock30_only10":pack(e30_only),
   "stock30_only10_by_symbol":by_symbol
 },
 "validation":{
   "stock53_control_expected_reference":{"closed":325,"net_r":61.17,"profit_factor":1.438,"max_drawdown_r":11.45},
   "note":"stock53_control is included to verify that this pipeline reproduces the previously validated 53-symbol E result."
 },
 "limitations":[
   "The current 30/50/53 universes are projected backward, so survivorship/post-selection bias remains.",
   "Breadth denominator uses symbols with sufficient completed daily history at each entry; later listings enter only when enough history exists.",
   "The 30-symbol and 50-symbol universes differ in composition as well as size, so this is a universe comparison, not a pure count-only experiment."
 ]
}
OUT.parent.mkdir(parents=True,exist_ok=True)
OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"results":out,"recent_windows":recent,"stock30_e_decomposition":report["stock30_e_decomposition"],"validation":report["validation"]},ensure_ascii=False,indent=2))
