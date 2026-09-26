import argparse, json, sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

sys.path.insert(0,str(Path(__file__).parent))
import backtest_wyckoff_5y as bt
import wyckoff_status as w

CURRENT50=("SPY","QQQ","IWM","AAPL","MSFT","NVDA","AMZN","META","GOOGL","TSLA",
           "AVGO","AMD","NFLX","ORCL","JPM","BAC","GS","V","MA","XOM","CVX","JNJ",
           "UNH","LLY","MRK","WMT","COST","HD","CAT","KO",
           "MSTR","COIN","HOOD","PLTR","BABA","TSM","MU","INTC","IBM","CRM","NOW","NET",
           "SHOP","DIS","UBER","CSCO","ANET","DDOG","AMAT","VST")
DOW2000=("MMM","AA","MO","AXP","BA","CAT","C","KO","DD","EK","XOM","GE","GM","HPQ",
         "HD","HON","INTC","IBM","IP","JNJ","JPM","MCD","MRK","MSFT","PG","SBC","UTX",
         "WMT","DIS","T")

DATA_DIR=Path("data/tmp_us50_25y")
NY=ZoneInfo("America/New_York")
UTC=timezone.utc
GLOBAL_EVAL_START=datetime(2000,1,1,tzinfo=UTC)
EVAL_END=datetime(2026,1,1,tzinfo=UTC)
LATE_LISTING_WARMUP_DAYS=180
FEE_BPS=4.0
SLIPPAGE_BPS=2.0
CAP=20000.0
RISK=400.0
A_OFF={"climax_spread_min":999.0,"climax_volume_min":999.0}

def load_all(symbols):
    files=sorted(DATA_DIR.glob("us50_15m_*.parquet"))
    if len(files)<6:
        raise RuntimeError(f"expected >=6 chunk parquets, got {len(files)}")
    frames=[]
    keep=set(symbols)
    for p in files:
        x=pd.read_parquet(p)
        frames.append(x[x["ticker"].isin(keep)])
    df=pd.concat(frames,ignore_index=True)
    df=df.drop_duplicates(["ticker","t"]).sort_values(["ticker","t"]).reset_index(drop=True)
    out={}
    for sym in symbols:
        g=df[df.ticker==sym]
        out[sym]=[
            {"t":int(r.t),"o":float(r.o),"h":float(r.h),"l":float(r.l),"c":float(r.c),"v":float(r.v)}
            for r in g.itertuples(index=False)
        ]
    return out,files

def day_key(bar):
    return datetime.fromtimestamp(bar["t"]/1000,UTC).astimezone(NY).date()

def detect_splits(bars):
    byday=defaultdict(list)
    for z in bars: byday[day_key(z)].append(z)
    days=sorted(byday); common=(2,3,4,5,7,10,15,20); events=[]
    for i in range(1,len(days)):
        prev=byday[days[i-1]][-1]["c"]; op=byday[days[i]][0]["o"]
        if prev<=0 or op<=0: continue
        ratio=prev/op; mag=ratio if ratio>=1 else 1/ratio
        if mag<1.7: continue
        f=min(common,key=lambda q:abs(mag/q))
        if abs(mag/f)<=0.08:
            pm,vm=((1/f,f) if ratio>1 else (f,1/f))
            events.append({"date":str(days[i]),"factor":f,"raw_prevclose_open_ratio":ratio,
                           "price_mult_before":pm,"volume_mult_before":vm})
    return events

def apply_splits(bars,events):
    if not events:return bars
    parsed=[(datetime.fromisoformat(e["date"]).date(),e["price_mult_before"],e["volume_mult_before"]) for e in events]
    out=[]
    for z in bars:
        d=day_key(z);pm=1.0;vm=1.0
        for split_day,p,v in parsed:
            if d<split_day:pm*=p;vm*=v
        q=z.copy()
        q["o"]*=pm;q["h"]*=pm;q["l"]*=pm;q["c"]*=pm;q["v"]*=vm
        out.append(q)
    return out

def aggregate_4h(bars):
    groups=defaultdict(list)
    for z in bars:
        dt=datetime.fromtimestamp(z["t"]/1000,UTC).astimezone(NY)
        mins=(dt.hour*60+dt.minute)-(9*60+30)
        if mins<0 or mins>=390: continue
        groups[(dt.date(),0 if mins<240 else 1)].append(z)
    out=[]
    for _,g in sorted(groups.items()):
        g.sort(key=lambda x:x["t"])
        out.append({"t":g[0]["t"],"o":g[0]["o"],"h":max(x["h"] for x in g),
                    "l":min(x["l"] for x in g),"c":g[-1]["c"],"v":sum(x["v"] for x in g)})
    return out

def aggregate_daily(bars):
    groups=defaultdict(list)
    for z in bars:groups[day_key(z)].append(z)
    out=[]
    for _,g in sorted(groups.items()):
        g.sort(key=lambda x:x["t"])
        out.append({"t":g[0]["t"],"o":g[0]["o"],"h":max(x["h"] for x in g),
                    "l":min(x["l"] for x in g),"c":g[-1]["c"],"v":sum(x["v"] for x in g)})
    return out

def trade_summary(ts):
    ts=sorted(ts,key=lambda x:x["exit_t"])
    wins=sum(t["pnl"]>0 for t in ts); losses=sum(t["pnl"]<0 for t in ts)
    gw=sum(max(t["r"],0) for t in ts); gl=-sum(min(t["r"],0) for t in ts)
    eq=CAP;peak=CAP;mdd=0.0;streak=max_streak=0
    for t in ts:
        eq+=t["pnl"];peak=max(peak,eq);mdd=max(mdd,(peak-eq)/peak if peak else 0.0)
        if t["pnl"]<0:streak+=1;max_streak=max(max_streak,streak)
        else:streak=0
    net=sum(t["r"] for t in ts)
    return {"closed":len(ts),"wins":wins,"losses":losses,
            "win_rate":wins/len(ts) if ts else None,
            "net_r":net,"avg_r":net/len(ts) if ts else None,
            "profit_factor_r":gw/gl if gl>0 else None,
            "max_drawdown_fixed_20k":mdd,
            "max_consecutive_losses":max_streak,
            "ending_equity_fixed_risk":eq}

def grouped_stats(trades,keyfn):
    out={}
    for t in trades:
        k=str(keyfn(t));q=out.setdefault(k,{"trades":0,"wins":0,"losses":0,"net_r":0.0})
        q["trades"]+=1;q["wins"]+=int(t["pnl"]>0);q["losses"]+=int(t["pnl"]<0);q["net_r"]+=t["r"]
    for q in out.values():
        q["win_rate"]=q["wins"]/q["trades"] if q["trades"] else None
        q["avg_r"]=q["net_r"]/q["trades"] if q["trades"] else None
    return out

def conservative_5r_cap(trades):
    accepted=[];skipped=[]
    for t in sorted(trades,key=lambda x:(x["entry_t"],x["exit_t"])):
        active=sum(1 for a in accepted if a["entry_t"]<=t["entry_t"]<a["exit_t"])
        if active>=5: skipped.append(t)
        else: accepted.append(t)
    return trade_summary(accepted),len(skipped)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--universe",choices=["current50","dow2000"],required=True)
    args=ap.parse_args()
    symbols=CURRENT50 if args.universe=="current50" else DOW2000
    out_path=Path(f"data/validation/us_{args.universe}_track_b_25y.json")
    bysym,files=load_all(symbols)
    results=[];errors={};all_trades=[]
    old_dataset,old_filters=bt.dataset,bt.symbol_filters
    old_cap,old_risk=bt.CAP,bt.RISK
    bt.CAP=CAP;bt.RISK=RISK
    try:
        for sym in symbols:
            try:
                bars=bysym[sym]
                if len(bars)<1000: raise RuntimeError(f"insufficient 15m bars: {len(bars)}")
                first=datetime.fromtimestamp(bars[0]["t"]/1000,UTC)
                last=datetime.fromtimestamp(bars[-1]["t"]/1000,UTC)
                if args.universe=="current50" and first>GLOBAL_EVAL_START:
                    eval_start=max(GLOBAL_EVAL_START,first+timedelta(days=LATE_LISTING_WARMUP_DAYS))
                else:
                    eval_start=GLOBAL_EVAL_START
                if eval_start>=EVAL_END:raise RuntimeError("no evaluation window")
                splits=detect_splits(bars);bars=apply_splits(bars,splits)
                H=w.enrich(aggregate_4h(bars));D=w.enrich(aggregate_daily(bars));M=bars
                bt._CACHE.clear()
                bt.dataset=lambda _s,D=D,H=H,M=M:(D,H,M)
                bt.symbol_filters=lambda _s:(0.01,0.0,0.0)
                r=bt.simulate(sym,a_params=A_OFF,b_params=None,
                    start_ms=int(eval_start.timestamp()*1000),end_ms=int(EVAL_END.timestamp()*1000)-1,
                    fee_bps=FEE_BPS,slippage_bps=SLIPPAGE_BPS,
                    a_mode="snapshot",b_runner_mode="pivot",b_scale_mode="30_30_40")
                ts=[t for t in r["trades"] if t["track"]=="B" and t["reason"]!="OPEN_MARK"]
                for t in ts:all_trades.append({"symbol":sym,**t})
                sm={"symbol":sym,
                    "coverage":{"first":first.isoformat(),"last":last.isoformat(),"evaluation_start":eval_start.isoformat()},
                    "bars":{"15m":len(M),"4h":len(H),"1d":len(D)},
                    "setups":r.get("setups",{}).get("B",0),"split_adjustments":splits,
                    **trade_summary(ts)}
                results.append(sm);print("RESULT",json.dumps(sm),flush=True)
            except Exception as e:
                errors[sym]=repr(e);print("SYMBOL_ERROR",sym,repr(e),flush=True)
    finally:
        bt.dataset,bt.symbol_filters=old_dataset,old_filters;bt.CAP,bt.RISK=old_cap,old_risk

    all_trades.sort(key=lambda x:x["exit_t"])
    total=trade_summary(all_trades)
    cap5,skipped5=conservative_5r_cap(all_trades)
    by_year=grouped_stats(all_trades,lambda t:datetime.fromtimestamp(t["exit_t"]/1000,UTC).astimezone(NY).year)
    by_symbol=grouped_stats(all_trades,lambda t:t["symbol"])
    report={
      "generated_at":datetime.now(UTC).isoformat(),
      "purpose":("Long-horizon stress test on the expanded 50-symbol US universe"
                 if args.universe=="current50"
                 else "Survivorship-bias-reduced stress test on the DJIA constituent universe frozen at 2000-01"),
      "universe":args.universe,"symbols":list(symbols),
      "period":{"global_evaluation_start":GLOBAL_EVAL_START.isoformat(),"evaluation_end_exclusive":EVAL_END.isoformat(),
                "late_listing_rule":("first available bar + 180 calendar days" if args.universe=="current50" else None)},
      "data":{"provider":"Hugging Face mito0o852/OHLCV-1m",
              "source":"monthly 1-minute US OHLCV parquet",
              "session":"09:30-16:00 America/New_York only",
              "aggregation":"1m -> 15m; 15m -> 09:30-13:30 4h + 13:30-16:00 stub; RTH daily",
              "chunk_files":[p.name for p in files],
              "split_cleanup":"common-factor overnight split detection; pre-split OHLCV back-adjusted"},
      "strategy":{"Track_A":"disabled","Track_B":"production defaults frozen; no long-horizon tuning",
                  "management":"TP1 30% => BE; TP2 30% => TP1; runner 40% confirmed 4H pivot",
                  "same_15m_bar":"STOP first","one_symbol_one_position":True},
      "costs":{"fee_bps_per_fill":FEE_BPS,"slippage_bps_per_fill":SLIPPAGE_BPS,"fixed_risk_usd":RISK},
      "totals_raw_aggregate":total,
      "conservative_5r_cap":{"summary":cap5,"skipped_trades":skipped5,
                             "method":"At most five simultaneous 1R positions; does not credit intratrade risk reduction."},
      "breadth":{"symbols_requested":len(symbols),"symbols_with_data":len(results),"symbols_with_errors":len(errors),
                 "positive_symbols":sum(1 for v in by_symbol.values() if v["net_r"]>0),
                 "negative_symbols":sum(1 for v in by_symbol.values() if v["net_r"]<0)},
      "by_year":by_year,"by_symbol":by_symbol,"per_symbol":results,"errors":errors,"trades":all_trades,
      "limitations":([
        "Current50-universe test is survivorship-biased by construction and is a regime stress test, not pristine OOS."
      ] if args.universe=="current50" else [
        "Universe membership is frozen to the DJIA roster in effect at 2000-01; no later constituent replacements are added.",
        "Corporate mergers, reorganizations, delistings and ticker reuse can complicate long-run security continuity in raw ticker data.",
        "This reduces survivorship bias versus today's winners, but does not eliminate historical-data/corporate-action bias."
      ])
    }
    out_path.parent.mkdir(parents=True,exist_ok=True)
    out_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("FINAL_SUMMARY",json.dumps({k:v for k,v in report.items() if k not in ("trades","per_symbol")},ensure_ascii=False),flush=True)

if __name__=="__main__":
    main()
