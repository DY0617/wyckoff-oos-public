import json,statistics
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path("data/validation/stock53_baseline_er06_20y_shards")
OUT=Path("data/validation/stock53_track_b_baseline_vs_er06_20y_v1.json")
UTC=timezone.utc

def ms(s): return int(datetime.fromisoformat(s).replace(tzinfo=UTC).timestamp()*1000)
CUT=ms("2021-04-01")

def stats(ts):
    ts=sorted(ts,key=lambda x:(x["exit_t"],x["symbol"]))
    rs=[float(x["r"]) for x in ts]
    gp=sum(x for x in rs if x>0); gl=-sum(x for x in rs if x<0)
    cr=peak=mdd=0.; st=mx=0
    for r in rs:
        cr+=r; peak=max(peak,cr); mdd=max(mdd,peak-cr)
        if r<0: st+=1; mx=max(mx,st)
        else: st=0
    return {"trades":len(rs),"wins":sum(x>0 for x in rs),"losses":sum(x<0 for x in rs),
            "win_rate":sum(x>0 for x in rs)/len(rs) if rs else None,
            "net_r":sum(rs),"avg_r":statistics.fmean(rs) if rs else None,
            "profit_factor":gp/gl if gl>0 else None,"max_drawdown_r":mdd,
            "max_consecutive_losses":mx,
            "net_r_over_mdd":sum(rs)/mdd if mdd>0 else None}

def yearly(ts):
    d=defaultdict(list)
    for t in ts:
        y=str(datetime.fromtimestamp(t["entry_t"]/1000,UTC).year); d[y].append(t)
    return {y:stats(v) for y,v in sorted(d.items())}

def symbol_stats(ts):
    d=defaultdict(list)
    for t in ts:d[t["symbol"]].append(t)
    return {s:stats(v) for s,v in sorted(d.items())}

def loso(ts):
    syms=sorted(set(t["symbol"] for t in ts)); rows=[]
    for s in syms:
        q=stats([t for t in ts if t["symbol"]!=s]); q["removed_symbol"]=s; rows.append(q)
    return {
      "cases":len(rows),
      "min_net_r":min((x["net_r"] for x in rows),default=None),
      "min_pf":min((x["profit_factor"] for x in rows if x["profit_factor"] is not None),default=None),
      "max_mdd_r":max((x["max_drawdown_r"] for x in rows),default=None),
      "max_loss_streak":max((x["max_consecutive_losses"] for x in rows),default=None),
      "worst_net_case":min(rows,key=lambda x:x["net_r"]) if rows else None
    }

def main():
    files=sorted(ROOT.glob("shard_*.json"))
    if not files: raise RuntimeError("no shards")
    combined=defaultdict(list); errors={}; meta=None
    for p in files:
        o=json.loads(p.read_text())
        meta=meta or {k:o.get(k) for k in ("strategy","configs","ratio","e_definition","costs")}
        errors[p.name]=o.get("errors",{})
        for name,v in o["results"].items(): combined[name].extend(v["trades"])
    out={"generated_at":datetime.now(UTC).isoformat(),
         "period":{"start":"2006-04-01","end_exclusive":"2026-04-01",
                   "oos_cut":"2021-04-01"},
         **(meta or {}),"results":{},"errors":errors}
    for name,ts in combined.items():
        ts=sorted(ts,key=lambda x:(x["entry_t"],x["symbol"]))
        old=[t for t in ts if t["entry_t"]<CUT]; recent=[t for t in ts if t["entry_t"]>=CUT]
        out["results"][name]={
          "full20y":stats(ts),"oos15y":stats(old),"recent5y":stats(recent),
          "years":yearly(ts),"oos_years":yearly(old),"recent_years":yearly(recent),
          "symbols":symbol_stats(ts),"oos_leave_one_symbol_out":loso(old)
        }
    if "baseline" in out["results"] and "er06" in out["results"]:
        a=out["results"]["baseline"]; b=out["results"]["er06"]
        out["delta_er06_minus_baseline"]={
          scope:{k:(b[scope].get(k)-a[scope].get(k)
                    if isinstance(a[scope].get(k),(int,float)) and isinstance(b[scope].get(k),(int,float))
                    else None)
                 for k in ("trades","win_rate","net_r","avg_r","profit_factor","max_drawdown_r","max_consecutive_losses","net_r_over_mdd")}
          for scope in ("full20y","oos15y","recent5y")
        }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:{s:v[s] for s in ("full20y","oos15y","recent5y")} for k,v in out["results"].items()},ensure_ascii=False,indent=2))
    print("DELTA",json.dumps(out.get("delta_er06_minus_baseline"),ensure_ascii=False,indent=2))

if __name__=="__main__": main()
