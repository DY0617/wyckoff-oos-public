import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import duckdb

import backtest_easychart_stock_trend_cont_v04_plateau as v4

DATA=Path("data/cache/stock53_recent5y_15m.parquet")
OUT=Path("data/validation/easychart_stock_trend_cont_v06_direction_diagnostic.json")
NY=ZoneInfo("America/New_York")
SYMS=v4.SYMS
LOOKBACK=15
PULLBACK_DAYS=5
RECLAIM_BUFFER=.10
TP_R=2.0
VOLUME_MULT=1.10

def filt(rows,name):
    if name=="base": return rows
    if name=="long": return [t for t in rows if t["direction"]=="LONG"]
    if name=="short": return [t for t in rows if t["direction"]=="SHORT"]
    if name=="market": return [t for t in rows if t["market_align"]]
    if name=="long_market": return [t for t in rows if t["direction"]=="LONG" and t["market_align"]]
    if name=="long_rs": return [t for t in rows if t["direction"]=="LONG" and t["rs_align"]]
    if name=="long_market_rs": return [t for t in rows if t["direction"]=="LONG" and t["market_align"] and t["rs_align"]]
    if name=="short_market": return [t for t in rows if t["direction"]=="SHORT" and t["market_align"]]
    raise KeyError(name)

def score(ts):
    tr,_=v4.split(ts);m=v4.metrics(tr)
    if m["n"]<180 or m["avg_r"] is None or m["avg_r"]<=0 or (m["pf"] or 0)<1.08:
        return -1e9
    return m["net_r"]-.25*m["mdd_r"]

def side_metrics(ts):
    d=defaultdict(list)
    for t in ts:d[t["direction"]].append(t)
    return {k:v4.metrics(x) for k,x in sorted(d.items())}

def main():
    v4.DATA=DATA
    con=duckdb.connect()
    data={s:v4.load15(con,s) for s in SYMS}
    con.close()
    daily={s:v4.daily_from_15m(data[s]) for s in SYMS}
    spyD=daily["SPY"];spy_date_to_i={x["date"]:i for i,x in enumerate(spyD)}
    rows=[]
    for s in SYMS:
        rr=v4.build_symbol(s,data[s],daily[s],spyD,spy_date_to_i,LOOKBACK,PULLBACK_DAYS,RECLAIM_BUFFER,TP_R)
        rr=[t for t in rr if t.get("break_vol_ratio") is not None and t["break_vol_ratio"]>=VOLUME_MULT]
        rows+=rr
        print("SYM",s,len(rr),flush=True)
    names=("base","long","short","market","long_market","long_rs","long_market_rs","short_market")
    variants={}
    for name in names:
        ts=filt(rows,name);tr,ho=v4.split(ts)
        variants[name]={
          "score_train_only":score(ts),
          "overall":v4.summarize(ts),
          "train":v4.summarize(tr),
          "holdout":v4.summarize(ho),
          "sides":side_metrics(ts),
        }
    ranking=sorted(names,key=lambda k:variants[k]["score_train_only"],reverse=True)
    out={
      "version":"0.6",
      "note":"OOS20 failure motivated a direction diagnostic, but all selection metrics here use original 53-symbol pre-2024-04 train only. OOS20 is not reused for selection.",
      "frozen_structure":{"lookback":LOOKBACK,"pullback_days":PULLBACK_DAYS,"reclaim_buffer_atr":RECLAIM_BUFFER,"tp_r":TP_R,"volume_mult":VOLUME_MULT},
      "ranking":ranking,
      "selected_by_original_train":ranking[0],
      "variants":variants,
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2),encoding="utf-8")
    print("FINAL",json.dumps({k:{
      "score":variants[k]["score_train_only"],
      "overall":variants[k]["overall"]["overall"],
      "train":variants[k]["train"]["overall"],
      "holdout":variants[k]["holdout"]["overall"]
    } for k in ranking},indent=2),flush=True)

if __name__=="__main__":main()
