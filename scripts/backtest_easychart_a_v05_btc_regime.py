import bisect,json,math
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

import backtest_easychart_synthesis_v01 as ez
import backtest_smc_liq_fvg_v01 as smc
import backtest_trend_structure_v0_1_crypto as core

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/validation/easychart_a_v05_btc_regime.json"
UTC=timezone.utc
TRAIN_END=int(datetime(2025,1,1,tzinfo=UTC).timestamp()*1000)

CORE=("BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","LINKUSDT")
OOS1=("LTCUSDT","BCHUSDT","DOTUSDT","AVAXUSDT","ETCUSDT","ATOMUSDT","FILUSDT","UNIUSDT")
OOS2=("TRXUSDT","XLMUSDT","AAVEUSDT","NEARUSDT","ALGOUSDT","XTZUSDT","EOSUSDT","RUNEUSDT")

GAP_MIN=0.10
SLOPE50_MIN=0.10

def metrics(ts): return ez.metrics(ts)

def summarize(ts,symbols):
    by=defaultdict(list);yr=defaultdict(list)
    for t in ts:
        by[t["symbol"]].append(t)
        yr[str(datetime.fromtimestamp(t["entry_t"]/1000,UTC).year)].append(t)
    sm={s:metrics(by.get(s,[])) for s in symbols}
    return {
      "overall":metrics(ts),
      "symbols":sm,
      "positive_symbols":sum(v["net_r"]>0 for v in sm.values() if v["n"]>0),
      "active_symbols":sum(v["n"]>0 for v in sm.values()),
      "years":{k:metrics(v) for k,v in sorted(yr.items())},
    }

def attach_symbol_daily(M,t):
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

def prepare_btc(B):
    D,Dclose=smc.prepare_daily(smc.aggregate_1d(B))
    W=ez.aggregate_weekly(D)
    M=ez.aggregate_monthly(D)
    return D,Dclose,W,M

def efficiency(D,di,n=10):
    if di<n:return None
    net=abs(D[di]["c"]-D[di-n]["c"])
    path=sum(abs(D[k]["c"]-D[k-1]["c"]) for k in range(di-n+1,di+1))
    return net/path if path>0 else 0.0

def btc_ctx(prep,t,direction):
    D,Dclose,W,M=prep
    di=bisect.bisect_right(Dclose,t)-1
    if di<20:return None
    x=D[di];A=x.get("atr")
    if not A or A<=0:return None
    sign=1 if direction=="LONG" else -1
    daily_align=sign*(x["c"]-x["ema50"])>0 and sign*(x["ema20"]-x["ema50"])>0
    gap=sign*(x["ema20"]-x["ema50"])/A
    slope=sign*(x["ema50"]-D[di-5]["ema50"])/A
    price50=sign*(x["c"]-x["ema50"])/A
    er10=efficiency(D,di,10)
    h=ez.htf_context(W,M,t,direction)
    return {
      "daily_align":daily_align,
      "gap":gap,
      "slope50":slope,
      "price50":price50,
      "er10":er10,
      "weekly_align":h["w20"],
      "monthly4_align":h["m4"],
      "htf_both":h["w20"] and h["m4"],
    }

def build_rows(symbols,data,btcprep):
    rows=[]
    for sym in symbols:
        M=data[sym]
        D=smc.aggregate_1d(M);W=ez.aggregate_weekly(D);MN=ez.aggregate_monthly(D)
        for t in ez.build_track_a(sym,M,W,MN):
            q=dict(t)
            sf=attach_symbol_daily(M,q)
            if not sf or sf["gap"]<GAP_MIN or sf["slope50"]<SLOPE50_MIN:
                continue
            q["sym_feat"]=sf
            q["btc"]=btc_ctx(btcprep,q["signal_t"],q["direction"])
            if q["btc"] is not None: rows.append(q)
        print("ROWS",sym,len([x for x in rows if x["symbol"]==sym]),flush=True)
    return ez.suppress_symbol_overlap(rows)

def variants(rows):
    specs={
      "none":lambda t:True,
      "btc_daily_align":lambda t:t["btc"]["daily_align"],
      "btc_gap0":lambda t:t["btc"]["gap"]>=0,
      "btc_gap010":lambda t:t["btc"]["gap"]>=0.10,
      "btc_slope0":lambda t:t["btc"]["slope50"]>=0,
      "btc_slope010":lambda t:t["btc"]["slope50"]>=0.10,
      "btc_daily_strength":lambda t:t["btc"]["daily_align"] and t["btc"]["gap"]>=0.10 and t["btc"]["slope50"]>=0.10,
      "btc_weekly":lambda t:t["btc"]["weekly_align"],
      "btc_monthly4":lambda t:t["btc"]["monthly4_align"],
      "btc_htf_both":lambda t:t["btc"]["htf_both"],
      "btc_daily_weekly":lambda t:t["btc"]["daily_align"] and t["btc"]["weekly_align"],
      "btc_daily_monthly":lambda t:t["btc"]["daily_align"] and t["btc"]["monthly4_align"],
      "btc_all_tf":lambda t:t["btc"]["daily_align"] and t["btc"]["htf_both"],
      "btc_er10_020":lambda t:t["btc"]["er10"] is not None and t["btc"]["er10"]>=0.20,
      "btc_er10_030":lambda t:t["btc"]["er10"] is not None and t["btc"]["er10"]>=0.30,
      "btc_er10_040":lambda t:t["btc"]["er10"] is not None and t["btc"]["er10"]>=0.40,
      "btc_daily_er020":lambda t:t["btc"]["daily_align"] and t["btc"]["er10"] is not None and t["btc"]["er10"]>=0.20,
      "btc_daily_er030":lambda t:t["btc"]["daily_align"] and t["btc"]["er10"] is not None and t["btc"]["er10"]>=0.30,
    }
    return {k:[t for t in rows if fn(t)] for k,fn in specs.items()}

def train_score(ts):
    tr=[t for t in ts if t["entry_t"]<TRAIN_END]
    st=metrics(tr)
    if st["n"]<18 or st["avg_r"] is None or st["avg_r"]<=0 or (st["pf"] or 0)<1.25:return -1e9
    by=defaultdict(list)
    for t in tr:by[t["symbol"]].append(t)
    pos=sum(metrics(v)["net_r"]>0 for v in by.values())
    return st["net_r"]-0.35*st["mdd_r"]+0.35*pos

def main():
    syms=tuple(dict.fromkeys(("BTCUSDT",)+CORE+OOS1+OOS2))
    data={}
    unavailable=[]
    for s in syms:
        try:
            data[s]=core.load_15m(s)
            print("DATA",s,len(data[s]),flush=True)
        except Exception as e:
            unavailable.append({"symbol":s,"error":str(e)})
            print("DATA_FAIL",s,str(e),flush=True)

    btcprep=prepare_btc(data["BTCUSDT"])
    core_rows=build_rows([s for s in CORE if s in data],data,btcprep)
    v=variants(core_rows)

    ranking=sorted(v,key=lambda k:train_score(v[k]),reverse=True)
    selected=ranking[0]
    selection={}
    for k in ranking:
        tr=[t for t in v[k] if t["entry_t"]<TRAIN_END]
        ho=[t for t in v[k] if t["entry_t"]>=TRAIN_END]
        selection[k]={
          "score_train_only":train_score(v[k]),
          "train":metrics(tr),
          "holdout":metrics(ho),
          "overall":metrics(v[k]),
          "n_2022":metrics([t for t in v[k] if datetime.fromtimestamp(t["entry_t"]/1000,UTC).year==2022]),
        }

    # apply selected rule without changing it
    spec_rows=variants(core_rows)[selected]
    oos1_syms=[s for s in OOS1 if s in data]
    oos2_syms=[s for s in OOS2 if s in data]
    oos1_all=build_rows(oos1_syms,data,btcprep)
    oos2_all=build_rows(oos2_syms,data,btcprep)
    oos1_sel=variants(oos1_all)[selected]
    oos2_sel=variants(oos2_all)[selected]

    out={
      "version":"0.5",
      "base_rule":{"symbol_gap_min_atr":GAP_MIN,"symbol_ema50_slope5_min_atr":SLOPE50_MIN},
      "selection_note":"BTC regime variant selected only on CORE trades before 2025-01-01. OOS1 and OOS2 are not used in ranking.",
      "selected_by_core_train":selected,
      "ranking":ranking,
      "selection":selection,
      "selected_results":{
        "core":summarize(spec_rows,CORE),
        "core_train":summarize([t for t in spec_rows if t["entry_t"]<TRAIN_END],CORE),
        "core_time_holdout":summarize([t for t in spec_rows if t["entry_t"]>=TRAIN_END],CORE),
        "oos1":summarize(oos1_sel,oos1_syms),
        "oos2_pristine":summarize(oos2_sel,oos2_syms),
      },
      "coverage":{"available":list(data),"unavailable":unavailable},
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2),encoding="utf-8")
    print("SELECTED",selected,flush=True)
    print("RESULT",json.dumps({k:v["overall"] for k,v in out["selected_results"].items()},indent=2),flush=True)

if __name__=="__main__":main()
