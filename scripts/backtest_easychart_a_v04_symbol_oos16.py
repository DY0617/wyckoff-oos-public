import bisect,json
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

import backtest_easychart_synthesis_v01 as ez
import backtest_smc_liq_fvg_v01 as smc
import backtest_trend_structure_v0_1_crypto as core

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/validation/easychart_a_v04_symbol_oos16.json"
UTC=timezone.utc
CORE=("BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","LINKUSDT")
OOS=("LTCUSDT","BCHUSDT","DOTUSDT","AVAXUSDT","ETCUSDT","ATOMUSDT","FILUSDT","UNIUSDT")
ALL=CORE+OOS
GAP_MIN=0.10
SLOPE50_MIN=0.10

def attach_daily(M,t):
    D,Dclose=smc.prepare_daily(smc.aggregate_1d(M))
    di=bisect.bisect_right(Dclose,t["signal_t"])-1
    if di<6:return None
    x=D[di];A=x.get("atr")
    if not A or A<=0:return None
    sign=1 if t["direction"]=="LONG" else -1
    return {
      "gap":sign*(x["ema20"]-x["ema50"])/A,
      "slope50":sign*(x["ema50"]-D[di-5]["ema50"])/A,
    }

def metrics(ts):return ez.metrics(ts)

def suppress(ts):return ez.suppress_symbol_overlap(ts)

def summarize(ts):
    d=defaultdict(list);yd=defaultdict(list)
    for t in ts:
        d[t["symbol"]].append(t)
        yd[str(datetime.fromtimestamp(t["entry_t"]/1000,UTC).year)].append(t)
    return {
      "overall":metrics(ts),
      "symbols":{s:metrics(d.get(s,[])) for s in ALL},
      "positive_symbols":sum(metrics(v)["net_r"]>0 for v in d.values()),
      "years":{k:metrics(v) for k,v in sorted(yd.items())},
    }

def run_group(symbols):
    rows=[]
    for sym in symbols:
        M=core.load_15m(sym)
        D=smc.aggregate_1d(M);W=ez.aggregate_weekly(D);MN=ez.aggregate_monthly(D)
        a=ez.build_track_a(sym,M,W,MN)
        for t in a:
            q=dict(t);q["feat"]=attach_daily(M,q)
            if q["feat"] and q["feat"]["gap"]>=GAP_MIN and q["feat"]["slope50"]>=SLOPE50_MIN:
                rows.append(q)
        print("DONE",sym,len(a),flush=True)
    return suppress(rows)

def main():
    core_rows=run_group(CORE)
    oos_rows=run_group(OOS)
    all_rows=suppress(core_rows+oos_rows)
    out={
      "version":"0.4",
      "rule":{"gap_min_atr":GAP_MIN,"ema50_slope5_min_atr":SLOPE50_MIN,
              "base":"EasyChart A liquidity-fakeout-FVG; 2R normal / 3R weekly+monthly aligned"},
      "selection_note":"thresholds fixed from CORE universe training diagnostics; OOS symbols not used for selection",
      "core":summarize(core_rows),
      "symbol_oos":summarize(oos_rows),
      "all16":summarize(all_rows),
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2),encoding="utf-8")
    print("FINAL",json.dumps({k:v["overall"] for k,v in out.items() if isinstance(v,dict) and "overall" in v},indent=2),flush=True)

if __name__=="__main__":main()
