import json, statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path("data/validation/stock53_balanced_runner_20y_shards")
OUT=Path("data/validation/stock53_balanced_runner_20y_oos_v1.json")
UTC=timezone.utc

def ms(s):
    return int(datetime.fromisoformat(s).replace(tzinfo=UTC).timestamp()*1000)

OOS_START=ms("2006-04-01")
OOS_END=ms("2021-04-01")
SEL_START=ms("2021-04-01")
SEL_END=ms("2026-04-01")

def summarize(ts):
    ordered=sorted(ts,key=lambda t:(t["exit_t"],t["symbol"]))
    rs=[float(t["r"]) for t in ordered]
    gp=sum(x for x in rs if x>0); gl=-sum(x for x in rs if x<0)
    cr=peak=mdd=0.0; st=mx=0
    for r in rs:
        cr+=r; peak=max(peak,cr); mdd=max(mdd,peak-cr)
        if r<0: st+=1; mx=max(mx,st)
        else: st=0
    return {
      "trades":len(rs),"wins":sum(x>0 for x in rs),"losses":sum(x<0 for x in rs),
      "win_rate":sum(x>0 for x in rs)/len(rs) if rs else None,
      "net_r":sum(rs),"avg_r":statistics.fmean(rs) if rs else None,
      "profit_factor":gp/gl if gl>0 else None,
      "max_drawdown_r":mdd,"max_consecutive_losses":mx,
      "net_r_over_mdd":sum(rs)/mdd if mdd>0 else None
    }

def period(ts,a,b):
    return summarize([t for t in ts if a<=int(t["entry_t"])<b])

def yearly(ts):
    d=defaultdict(list)
    for t in ts:
        y=str(datetime.fromtimestamp(t["entry_t"]/1000,UTC).year)
        d[y].append(t)
    return {y:summarize(v) for y,v in sorted(d.items())}

def concentration(ts):
    d=defaultdict(float)
    for t in ts:d[t["symbol"]]+=float(t["r"])
    vals=sorted(d.items(),key=lambda z:z[1],reverse=True)
    total=sum(d.values())
    return {
      "trading_symbols":len(d),
      "profitable_symbols":sum(v>0 for v in d.values()),
      "losing_symbols":sum(v<0 for v in d.values()),
      "top1_share":vals[0][1]/total if vals and total else None,
      "top5_share":sum(v for _,v in vals[:5])/total if total else None,
      "top5":vals[:5],"bottom5":vals[-5:]
    }

def loso(ts):
    syms=sorted(set(t["symbol"] for t in ts))
    rows=[]
    for s in syms:
        q=summarize([t for t in ts if t["symbol"]!=s])
        q["removed_symbol"]=s
        rows.append(q)
    return {
      "cases":len(rows),
      "min_net_r":min((x["net_r"] for x in rows),default=None),
      "min_pf":min((x["profit_factor"] for x in rows if x["profit_factor"] is not None),default=None),
      "max_mdd_r":max((x["max_drawdown_r"] for x in rows),default=None),
      "max_loss_streak":max((x["max_consecutive_losses"] for x in rows),default=None),
    }

def main():
    files=sorted(ROOT.glob("shard_*.json"))
    if not files:raise RuntimeError("no shards")
    modes=defaultdict(list); shard_summaries={}; meta=None
    for p in files:
        o=json.loads(p.read_text())
        meta=meta or {k:o.get(k) for k in ("strategy","b_params","ratios","e_definition","costs")}
        shard_summaries[p.name]={k:v["summary"] for k,v in o["modes"].items()}
        for mode,v in o["modes"].items():
            modes[mode]+=v.get("trades",[])
    out={
      "period":{"start":"2006-04-01","end_exclusive":"2026-04-01"},
      "oos_definition":"Backward untouched OOS = 2006-04-01 through 2021-04-01; recent 2021-04-01 through 2026-04-01 was used for parameter/ratio selection.",
      **(meta or {}),"modes":{},"shards":shard_summaries
    }
    for mode,ts in sorted(modes.items()):
        ts=sorted(ts,key=lambda t:(t["entry_t"],t["symbol"]))
        oos=[t for t in ts if OOS_START<=int(t["entry_t"])<OOS_END]
        recent=[t for t in ts if SEL_START<=int(t["entry_t"])<SEL_END]
        out["modes"][mode]={
          "full20y":summarize(ts),
          "oos15y":summarize(oos),
          "recent5y":summarize(recent),
          "oos_2006_2013":period(ts,ms("2006-04-01"),ms("2013-04-01")),
          "oos_2013_2021":period(ts,ms("2013-04-01"),ms("2021-04-01")),
          "years":yearly(ts),
          "oos_symbol_concentration":concentration(oos),
          "oos_leave_one_symbol_out":loso(oos)
        }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({m:{k:v[k] for k in ("full20y","oos15y","recent5y","oos_2006_2013","oos_2013_2021")} for m,v in out["modes"].items()},ensure_ascii=False,indent=2))

if __name__=="__main__":main()
