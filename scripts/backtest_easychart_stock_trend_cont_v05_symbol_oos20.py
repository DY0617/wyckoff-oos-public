import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import duckdb

import backtest_easychart_stock_trend_cont_v04_plateau as v4

DATA=Path("data/cache/stock_oos20_recent5y_15m.parquet")
OUT=Path("data/validation/easychart_stock_trend_cont_v05_symbol_oos20.json")
NY=ZoneInfo("America/New_York")
TRADE_SYMS=("XOM","BAC","MA","PG","KO","PEP","JNJ","ABBV","MRK","GE","CVX","UNH","QCOM","TXN","AMGN","SBUX","LOW","BKNG","GS","C")
ALL=TRADE_SYMS+("SPY",)
VOLUME_MULT=1.10
LOOKBACK=15
PULLBACK_DAYS=5
RECLAIM_BUFFER=.10
TP_R=2.0

def metrics(ts):
    return v4.metrics(ts)

def summarize(ts):
    by=defaultdict(list);yr=defaultdict(list);side=defaultdict(list)
    for t in ts:
        by[t["symbol"]].append(t)
        yr[str(datetime.fromtimestamp(t["entry_t"]/1000,NY).year)].append(t)
        side[t["direction"]].append(t)
    sm={s:metrics(by.get(s,[])) for s in TRADE_SYMS}
    return {
      "overall":metrics(ts),
      "positive_symbols":sum(x["net_r"]>0 for x in sm.values() if x["n"]>0),
      "active_symbols":sum(x["n"]>0 for x in sm.values()),
      "symbols":sm,
      "years":{k:metrics(v) for k,v in sorted(yr.items())},
      "sides":{k:metrics(v) for k,v in sorted(side.items())},
    }

def main():
    v4.DATA=DATA
    con=duckdb.connect()
    data={s:v4.load15(con,s) for s in ALL}
    con.close()
    daily={s:v4.daily_from_15m(data[s]) for s in ALL}
    spyD=daily["SPY"];spy_date_to_i={x["date"]:i for i,x in enumerate(spyD)}

    rows=[]
    for s in TRADE_SYMS:
        ts=v4.build_symbol(s,data[s],daily[s],spyD,spy_date_to_i,LOOKBACK,PULLBACK_DAYS,RECLAIM_BUFFER,TP_R)
        ts=[t for t in ts if t.get("break_vol_ratio") is not None and t["break_vol_ratio"]>=VOLUME_MULT]
        rows+=ts
        print("SYM",s,len(ts),flush=True)

    out={
      "version":"0.5",
      "validation":"pristine symbol-OOS20; no threshold selected or tuned on these symbols",
      "frozen_rule":{
        "lookback":LOOKBACK,
        "pullback_days":PULLBACK_DAYS,
        "reclaim_buffer_atr":RECLAIM_BUFFER,
        "tp_r":TP_R,
        "breakout_volume_mult":VOLUME_MULT,
        "entry":"next 15m open after reclaim trigger",
        "cost_bps_per_side":v4.COST_BPS_SIDE,
        "max_hold_days":v4.MAX_HOLD_DAYS,
      },
      "symbols":list(TRADE_SYMS),
      "result":summarize(rows),
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2),encoding="utf-8")
    print("FINAL",json.dumps({
      "overall":out["result"]["overall"],
      "positive_symbols":out["result"]["positive_symbols"],
      "active_symbols":out["result"]["active_symbols"],
      "years":out["result"]["years"],
      "sides":out["result"]["sides"],
    },indent=2),flush=True)

if __name__=="__main__":main()
