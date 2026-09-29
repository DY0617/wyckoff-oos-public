import json, statistics
from collections import defaultdict
from pathlib import Path

CAP=20000.0
RISK=400.0
ROOT=Path("data/validation/stock53_e_management_shards")
OUT=Path("data/validation/stock53_e_management_sweep_20y.json")

def summarize(ts):
    ordered=sorted(ts,key=lambda t:(t["exit_t"],t["symbol"]))
    rs=[t["r_recalc"] for t in ordered]
    pos=[x for x in rs if x>0];neg=[x for x in rs if x<0]
    eq=CAP;peak=CAP;mdd=0;cur=mx=0
    for t in ordered:
        eq+=t["pnl_recalc"];peak=max(peak,eq);mdd=max(mdd,(peak-eq)/peak if peak else 0)
        if t["pnl_recalc"]<0:cur+=1;mx=max(mx,cur)
        else:cur=0
    return {
      "trades":len(ordered),
      "wins":sum(t["pnl_recalc"]>0 for t in ordered),
      "losses":sum(t["pnl_recalc"]<0 for t in ordered),
      "win_rate":sum(t["pnl_recalc"]>0 for t in ordered)/len(ordered) if ordered else None,
      "net_r":sum(rs),
      "avg_r":statistics.fmean(rs) if rs else None,
      "profit_factor":sum(pos)/abs(sum(neg)) if neg else None,
      "max_drawdown_fixed_20k":mdd,
      "max_drawdown_r":mdd*CAP/RISK,
      "max_consecutive_losses":mx
    }

def main():
    files=sorted(ROOT.glob("shard_*.json"))
    if not files:raise RuntimeError("no shards")
    modes=defaultdict(list); shard_summaries={}; years=defaultdict(lambda:defaultdict(list))
    eligible=0
    for p in files:
        o=json.loads(p.read_text())
        eligible+=o.get("eligible_trades",0)
        shard_summaries[p.name]={k:v["summary"] for k,v in o["modes"].items()}
        for mode,v in o["modes"].items():
            modes[mode]+=v.get("trades",[])
            for t in v.get("trades",[]):
                import datetime
                y=str(datetime.datetime.fromtimestamp(t["entry_t"]/1000,datetime.timezone.utc).year)
                years[mode][y].append(t)
    out={
      "period":{"start":"2006-04-01","end_exclusive":"2026-04-01"},
      "filter":"LONG + SPY bull regime + stock ret20>=SPY ret20 + breadth>=50%",
      "eligible_trades":eligible,
      "modes":{},
      "shards":shard_summaries
    }
    for mode,ts in sorted(modes.items()):
        out["modes"][mode]={
          "summary":summarize(ts),
          "years":{y:summarize(v) for y,v in sorted(years[mode].items())}
        }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=="__main__":main()
