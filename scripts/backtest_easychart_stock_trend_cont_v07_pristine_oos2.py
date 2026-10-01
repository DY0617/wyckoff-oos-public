import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import duckdb

import backtest_easychart_stock_trend_cont_v04_plateau as v4

ORIG_DATA=Path("data/cache/stock53_recent5y_15m.parquet")
OOS_DATA=Path("data/cache/stock_oos2_20_recent5y_15m.parquet")
OUT=Path("data/validation/easychart_stock_trend_cont_v07_pristine_oos2.json")
NY=ZoneInfo("America/New_York")

ORIG_SYMS=v4.SYMS
OOS_SYMS=("MCD","NKE","TMO","DHR","MDT","UPS","RTX","LMT","DE","NEE","DUK","SO","PLD","AMT","CB","AXP","USB","PNC","BLK","CME")
LOOKBACK=15
PULLBACK_DAYS=5
RECLAIM_BUFFER=.10
TP_R=2.0
VOLUME_MULT=1.10

def select_filter(rows,name):
    if name=="base": return rows
    if name=="long": return [t for t in rows if t["direction"]=="LONG"]
    if name=="short": return [t for t in rows if t["direction"]=="SHORT"]
    if name=="market": return [t for t in rows if t["market_align"]]
    if name=="long_market": return [t for t in rows if t["direction"]=="LONG" and t["market_align"]]
    if name=="long_rs": return [t for t in rows if t["direction"]=="LONG" and t["rs_align"]]
    if name=="long_market_rs": return [t for t in rows if t["direction"]=="LONG" and t["market_align"] and t["rs_align"]]
    if name=="short_market": return [t for t in rows if t["direction"]=="SHORT" and t["market_align"]]
    raise KeyError(name)

def score_train(ts):
    tr,_=v4.split(ts);m=v4.metrics(tr)
    if m["n"]<180 or m["avg_r"] is None or m["avg_r"]<=0 or (m["pf"] or 0)<1.08:
        return -1e9
    return m["net_r"]-.25*m["mdd_r"]

def build_rows(data_path,syms):
    old=v4.DATA
    v4.DATA=data_path
    con=duckdb.connect()
    all_syms=tuple(dict.fromkeys(tuple(syms)+("SPY",)))
    data={s:v4.load15(con,s) for s in all_syms}
    con.close()
    daily={s:v4.daily_from_15m(data[s]) for s in all_syms}
    spyD=daily["SPY"];spy_date_to_i={x["date"]:i for i,x in enumerate(spyD)}
    rows=[]
    for s in syms:
        rr=v4.build_symbol(s,data[s],daily[s],spyD,spy_date_to_i,LOOKBACK,PULLBACK_DAYS,RECLAIM_BUFFER,TP_R)
        rr=[t for t in rr if t.get("break_vol_ratio") is not None and t["break_vol_ratio"]>=VOLUME_MULT]
        rows+=rr
        print("ROWS",data_path.name,s,len(rr),flush=True)
    v4.DATA=old
    return rows

def summarize(ts,syms):
    by=defaultdict(list);yr=defaultdict(list);side=defaultdict(list)
    for t in ts:
        by[t["symbol"]].append(t)
        yr[str(datetime.fromtimestamp(t["entry_t"]/1000,NY).year)].append(t)
        side[t["direction"]].append(t)
    sm={s:v4.metrics(by.get(s,[])) for s in syms}
    return {
      "overall":v4.metrics(ts),
      "positive_symbols":sum(x["net_r"]>0 for x in sm.values() if x["n"]>0),
      "active_symbols":sum(x["n"]>0 for x in sm.values()),
      "symbols":sm,
      "years":{k:v4.metrics(x) for k,x in sorted(yr.items())},
      "sides":{k:v4.metrics(x) for k,x in sorted(side.items())},
    }

def main():
    original=build_rows(ORIG_DATA,ORIG_SYMS)
    names=("base","long","short","market","long_market","long_rs","long_market_rs","short_market")
    selection={}
    for name in names:
        ts=select_filter(original,name)
        tr,ho=v4.split(ts)
        selection[name]={
          "score_train_only":score_train(ts),
          "train":v4.metrics(tr),
          "holdout":v4.metrics(ho),
          "overall":v4.metrics(ts),
        }
    ranking=sorted(names,key=lambda k:selection[k]["score_train_only"],reverse=True)
    selected=ranking[0]

    # Pristine OOS2 is touched only after selection is fixed.
    oos=build_rows(OOS_DATA,OOS_SYMS)
    oos_selected=select_filter(oos,selected)

    out={
      "version":"0.7",
      "protocol":"direction/filter selected only from original 53-symbol pre-2024-04 train. OOS20-v1 not reused. OOS2 symbols unseen until after selection.",
      "frozen_structure":{
        "lookback":LOOKBACK,"pullback_days":PULLBACK_DAYS,"reclaim_buffer_atr":RECLAIM_BUFFER,
        "tp_r":TP_R,"breakout_volume_mult":VOLUME_MULT,
        "entry":"next 15m open after reclaim trigger",
        "cost_bps_per_side":v4.COST_BPS_SIDE,
        "max_hold_days":v4.MAX_HOLD_DAYS,
      },
      "selection_ranking":ranking,
      "selected_by_original_train":selected,
      "selection_metrics":selection,
      "oos2_symbols":list(OOS_SYMS),
      "oos2_result":summarize(oos_selected,OOS_SYMS),
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2),encoding="utf-8")
    print("FINAL",json.dumps({
      "selected":selected,
      "selection":selection[selected],
      "oos2":out["oos2_result"]["overall"],
      "positive_symbols":out["oos2_result"]["positive_symbols"],
      "active_symbols":out["oos2_result"]["active_symbols"],
      "years":out["oos2_result"]["years"],
      "sides":out["oos2_result"]["sides"],
    },indent=2),flush=True)

if __name__=="__main__":main()
