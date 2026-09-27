import json
from pathlib import Path
from collections import defaultdict

ROOT=Path("data/validation/stock53_resolution_shards")
OUT=Path("data/validation/stock53_hf_1m_vs_15m_regime_comparison.json")

def stats(ts):
    n=len(ts);wins=sum(t["pnl"]>0 for t in ts);losses=sum(t["pnl"]<0 for t in ts)
    net=sum(t["r"] for t in ts);gp=sum(t["r"] for t in ts if t["r"]>0);gl=sum(t["r"] for t in ts if t["r"]<0)
    return {"closed":n,"wins":wins,"losses":losses,"win_rate":wins/n if n else None,
            "net_r":net,"avg_r":net/n if n else None,"profit_factor":gp/abs(gl) if gl<0 else None}

def dd_r(ts):
    eq=peak=0.0;worst=0.0
    for t in sorted(ts,key=lambda x:(x["exit_t"],x["symbol"])):
        eq+=t["r"];peak=max(peak,eq);worst=max(worst,peak-eq)
    return worst

def pack(rows):
    t1=[t for r in rows for t in r["trades_1m"]]
    t15=[t for r in rows for t in r["trades_15m"]]
    t1.sort(key=lambda x:(x["entry_t"],x["symbol"]));t15.sort(key=lambda x:(x["entry_t"],x["symbol"]))
    s1=stats(t1);s15=stats(t15)
    k=lambda t:(t["symbol"],t["direction"],t["trigger_4h_open_ms"],round(float(t["entry"]),6))
    a={k(t):t for t in t1};b={k(t):t for t in t15};common=set(a)&set(b)
    changed=[{"symbol":a[x]["symbol"],"direction":a[x]["direction"],"trigger_4h_open_ms":a[x]["trigger_4h_open_ms"],
              "r_1m":a[x]["r"],"r_15m":b[x]["r"],"delta_r":a[x]["r"]-b[x]["r"],
              "reason_1m":a[x]["reason"],"reason_15m":b[x]["reason"]}
             for x in common if abs(a[x]["r"]-b[x]["r"])>1e-9]
    changed.sort(key=lambda x:abs(x["delta_r"]),reverse=True)
    dirs={}
    for d in ("LONG","SHORT"):
        dirs[d]={"1m":stats([t for t in t1 if t["direction"]==d]),"15m":stats([t for t in t15 if t["direction"]==d])}
    return {"1m":{**s1,"max_drawdown_r":dd_r(t1)},
            "15m":{**s15,"max_drawdown_r":dd_r(t15)},
            "delta":{"net_r":s1["net_r"]-s15["net_r"],"avg_r":(s1["avg_r"] or 0)-(s15["avg_r"] or 0),
                     "closed":len(t1)-len(t15),"common_trades":len(common),"changed_trade_r":len(changed)},
            "by_direction":dirs,"largest_changed_trades":changed[:25]}

def main():
    files=sorted(ROOT.glob("*.json"))
    if len(files)!=11: raise RuntimeError(f"expected 11 shards, got {len(files)}")
    rows=[json.loads(p.read_text()) for p in files]
    if any(r.get("errors") for r in rows):
        # Pre-listing/no-history errors are expected for some symbols; retain them for audit.
        pass
    weak=[r for r in rows if 2010<=int(r["eval_start"][:4])<=2014]
    recent=[r for r in rows if 2020<=int(r["eval_start"][:4])<=2025]
    report={
      "purpose":"execution-resolution sensitivity for frozen Track B using identical RTH signals",
      "windows":{
        "2010-2015":{"start":"2010-01-01","end_exclusive":"2015-01-01",**pack(weak)},
        "2020-2026":{"start":"2020-01-01","end_exclusive":"2026-04-01",**pack(recent)}
      },
      "combined_test_windows":pack(rows),
      "shard_audit":[{"eval_start":r["eval_start"],"eval_end_exclusive":r["eval_end_exclusive"],
                      "months_loaded":r["months_loaded"],"errors":r["errors"]} for r in rows]
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report["windows"],ensure_ascii=False))

if __name__=="__main__":main()
