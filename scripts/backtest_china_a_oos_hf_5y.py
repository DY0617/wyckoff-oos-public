import json, math, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).parent))
import backtest_wyckoff_5y as bt
import wyckoff_status as w

ROOT=Path("data/tmp_china_a")
OUT=Path("data/validation/china_a_track_b_oos_5y.json")
CN=ZoneInfo("Asia/Shanghai")
UTC=timezone.utc

SYMS={
  "SH600519":{"exchange":"SH","code":"600519","name":"Kweichow Moutai"},
  "SH600036":{"exchange":"SH","code":"600036","name":"China Merchants Bank"},
  "SH601318":{"exchange":"SH","code":"601318","name":"Ping An Insurance"},
  "SH600030":{"exchange":"SH","code":"600030","name":"CITIC Securities"},
  "SH600276":{"exchange":"SH","code":"600276","name":"Hengrui Medicine"},
  "SH600900":{"exchange":"SH","code":"600900","name":"China Yangtze Power"},
  "SH601166":{"exchange":"SH","code":"601166","name":"Industrial Bank"},
  "SH601398":{"exchange":"SH","code":"601398","name":"ICBC"},
  "SZ000001":{"exchange":"SZ","code":"000001","name":"Ping An Bank"},
  "SZ000858":{"exchange":"SZ","code":"000858","name":"Wuliangye"},
  "SZ000333":{"exchange":"SZ","code":"000333","name":"Midea Group"},
  "SZ002415":{"exchange":"SZ","code":"002415","name":"Hikvision"},
}

WARMUP_START=datetime(2020,1,1,tzinfo=CN)
EVAL_START=datetime(2021,1,1,tzinfo=CN)
EVAL_END=datetime(2026,1,1,tzinfo=CN)
FEE_BPS=4.0
SLIPPAGE_BPS=2.0
CAP=20000.0
RISK=400.0
A_OFF={"climax_spread_min":999.0,"climax_volume_min":999.0}
H4_MS=4*60*60*1000

def local_day(ms):
    return datetime.fromtimestamp(ms/1000,UTC).astimezone(CN).date()

def load_15m(sym):
    meta=SYMS[sym]
    path=ROOT/meta["exchange"]/f"{meta['code']}.parquet"
    if not path.exists():
        raise FileNotFoundError(path)

    df=pq.read_table(path,columns=["timestamp","open","high","low","close","volume"]).to_pandas()
    ts=pd.to_datetime(df["timestamp"],errors="coerce")
    df=df.assign(timestamp=ts).dropna(subset=["timestamp","open","high","low","close"])
    df=df[(df["timestamp"]>=pd.Timestamp("2020-01-01")) & (df["timestamp"]<pd.Timestamp("2026-01-01"))].copy()
    if df.empty:
        return []

    mins=df["timestamp"].dt.hour*60+df["timestamp"].dt.minute
    valid=((mins>=570)&(mins<690)) | ((mins>=780)&(mins<900))
    df=df[valid].copy()
    mins=df["timestamp"].dt.hour*60+df["timestamp"].dt.minute
    anchor=pd.Series(780,index=df.index)
    anchor.loc[mins<720]=570
    bucket_min=anchor+((mins-anchor)//15)*15
    bucket=df["timestamp"].dt.normalize()+pd.to_timedelta(bucket_min,unit="m")
    df["bucket"]=bucket

    agg=(df.sort_values("timestamp")
           .groupby("bucket",sort=True)
           .agg(open=("open","first"),high=("high","max"),low=("low","min"),
                close=("close","last"),volume=("volume","sum"))
           .reset_index())

    local=pd.to_datetime(agg["bucket"]).dt.tz_localize(CN)
    utc=local.dt.tz_convert(UTC)
    # Robust across pandas datetime64[us]/[ns]: convert via epoch seconds to milliseconds.
    ms=utc.map(lambda x:int(x.timestamp()*1000)).astype("int64")
    out=[]
    for t,o,h,l,c,v in zip(ms,agg["open"],agg["high"],agg["low"],agg["close"],agg["volume"]):
        vals=(o,h,l,c,v)
        if not all(math.isfinite(float(x or 0)) for x in vals):
            continue
        out.append({"t":int(t),"o":float(o),"h":float(h),"l":float(l),"c":float(c),"v":float(v or 0.0)})
    return out

def detect_common_factor_events(bars):
    byday=defaultdict(list)
    for z in bars:
        byday[local_day(z["t"])].append(z)
    days=sorted(byday)
    common=(2,3,4,5,7,10,15,20)
    events=[]
    for i in range(1,len(days)):
        prev=byday[days[i-1]][-1]["c"]
        op=byday[days[i]][0]["o"]
        if prev<=0 or op<=0:
            continue
        ratio=prev/op
        mag=ratio if ratio>=1 else 1/ratio
        if mag<1.7:
            continue
        f=min(common,key=lambda q:abs(mag/q))
        if abs(mag/f)<=0.08:
            if ratio>1:
                pm,vm=1/f,f
            else:
                pm,vm=f,1/f
            events.append({"date":str(days[i]),"factor":f,"raw_prevclose_open_ratio":ratio,
                           "price_mult_before":pm,"volume_mult_before":vm})
    return events

def apply_events(bars,events):
    if not events:
        return bars
    parsed=[(datetime.fromisoformat(e["date"]).date(),e["price_mult_before"],e["volume_mult_before"]) for e in events]
    out=[]
    for z in bars:
        d=local_day(z["t"])
        pm=1.0; vm=1.0
        for ed,p,v in parsed:
            if d<ed:
                pm*=p; vm*=v
        q=z.copy()
        q["o"]*=pm; q["h"]*=pm; q["l"]*=pm; q["c"]*=pm; q["v"]*=vm
        out.append(q)
    return out

def aggregate_4h(bars):
    groups=defaultdict(list)
    for z in bars:
        k=(z["t"]//H4_MS)*H4_MS
        groups[k].append(z)
    out=[]
    for k,g in sorted(groups.items()):
        g.sort(key=lambda x:x["t"])
        out.append({"t":k,"o":g[0]["o"],"h":max(x["h"] for x in g),
                    "l":min(x["l"] for x in g),"c":g[-1]["c"],"v":sum(x["v"] for x in g)})
    return out

def aggregate_daily(bars):
    groups=defaultdict(list)
    for z in bars:
        groups[local_day(z["t"])].append(z)
    out=[]
    for _,g in sorted(groups.items()):
        g.sort(key=lambda x:x["t"])
        out.append({"t":g[0]["t"],"o":g[0]["o"],"h":max(x["h"] for x in g),
                    "l":min(x["l"] for x in g),"c":g[-1]["c"],"v":sum(x["v"] for x in g)})
    return out

def trade_summary(ts):
    ts=sorted(ts,key=lambda x:x["exit_t"])
    wins=sum(t["pnl"]>0 for t in ts)
    losses=sum(t["pnl"]<0 for t in ts)
    gw=sum(max(t["r"],0) for t in ts)
    gl=-sum(min(t["r"],0) for t in ts)
    eq=CAP; peak=CAP; mdd=0.0; streak=max_streak=0
    for t in ts:
        eq+=t["pnl"]; peak=max(peak,eq)
        mdd=max(mdd,(peak-eq)/peak if peak else 0.0)
        if t["pnl"]<0:
            streak+=1; max_streak=max(max_streak,streak)
        else:
            streak=0
    net=sum(t["r"] for t in ts)
    return {"closed":len(ts),"wins":wins,"losses":losses,"win_rate":wins/len(ts) if ts else None,
            "net_r":net,"avg_r":net/len(ts) if ts else None,
            "profit_factor_r":gw/gl if gl>0 else None,
            "max_drawdown_fixed_20k":mdd,"max_consecutive_losses":max_streak,
            "ending_equity_fixed_risk":eq}

def grouped_stats(trades,keyfn):
    out={}
    for t in trades:
        k=str(keyfn(t))
        q=out.setdefault(k,{"trades":0,"wins":0,"losses":0,"net_r":0.0})
        q["trades"]+=1
        q["wins"]+=int(t["pnl"]>0)
        q["losses"]+=int(t["pnl"]<0)
        q["net_r"]+=t["r"]
    for q in out.values():
        q["win_rate"]=q["wins"]/q["trades"] if q["trades"] else None
        q["avg_r"]=q["net_r"]/q["trades"] if q["trades"] else None
    return out

def main():
    results=[]; errors={}; all_trades=[]
    old_dataset,old_filters=bt.dataset,bt.symbol_filters
    old_cap,old_risk=bt.CAP,bt.RISK
    bt.CAP=CAP; bt.RISK=RISK
    try:
        for sym,meta in SYMS.items():
            try:
                bars=load_15m(sym)
                years={datetime.fromtimestamp(z["t"]/1000,UTC).astimezone(CN).year for z in bars}
                if len(bars)<15000 or not set(range(2020,2026)).issubset(years):
                    raise RuntimeError(f"insufficient coverage bars={len(bars)} years={sorted(years)}")
                events=detect_common_factor_events(bars)
                bars=apply_events(bars,events)
                H=w.enrich(aggregate_4h(bars))
                D=w.enrich(aggregate_daily(bars))
                M=bars
                bt._CACHE.clear()
                bt.dataset=lambda _s,D=D,H=H,M=M:(D,H,M)
                bt.symbol_filters=lambda _s:(0.01,0.0,0.0)
                r=bt.simulate(
                    sym,a_params=A_OFF,b_params=None,
                    start_ms=int(EVAL_START.astimezone(UTC).timestamp()*1000),
                    end_ms=int(EVAL_END.astimezone(UTC).timestamp()*1000)-1,
                    fee_bps=FEE_BPS,slippage_bps=SLIPPAGE_BPS,
                    a_mode="snapshot",b_runner_mode="pivot",b_scale_mode="30_30_40"
                )
                ts=[t for t in r["trades"] if t["track"]=="B" and t["reason"]!="OPEN_MARK"]
                for t in ts:
                    all_trades.append({"symbol":sym,"name":meta["name"],**t})
                sm={"symbol":sym,"name":meta["name"],"bars":{"15m":len(M),"4h":len(H),"1d":len(D)},
                    "setups":r.get("setups",{}).get("B",0),
                    "corporate_action_adjustments":events,**trade_summary(ts)}
                results.append(sm)
                print("RESULT",json.dumps(sm,ensure_ascii=False),flush=True)
            except Exception as e:
                errors[sym]=repr(e)
                print("SYMBOL_ERROR",sym,repr(e),flush=True)
    finally:
        bt.dataset,bt.symbol_filters=old_dataset,old_filters
        bt.CAP,bt.RISK=old_cap,old_risk

    all_trades.sort(key=lambda x:x["exit_t"])
    total=trade_summary(all_trades)
    by_year=grouped_stats(all_trades,lambda t:datetime.fromtimestamp(t["exit_t"]/1000,UTC).astimezone(CN).year)
    by_symbol=grouped_stats(all_trades,lambda t:t["symbol"])
    report={
      "generated_at":datetime.now(UTC).isoformat(),
      "purpose":"Five-year untouched-market OOS validation of frozen Track B on China A-share equities",
      "period":{"warmup_start":"2020-01-01","evaluation_start":"2021-01-01","evaluation_end_exclusive":"2026-01-01"},
      "source":"Hugging Face neigezhu/china-a-share-1min-ohlcv; canonical per-instrument Parquet",
      "market":"Shanghai/Shenzhen China A-share equities",
      "IMPORTANT":[
        "No China-market-specific parameter tuning was performed.",
        "Source prices are unadjusted; common-factor overnight corporate-action jumps are back-adjusted using the same cleanup style as the US-stock robustness test.",
        "4H bars use native UTC 4-hour buckets; China session contributes the morning and afternoon session portions to separate 4H buckets.",
        "This is robustness research, not an executable China-cash short-selling simulation."
      ],
      "symbols":[{"symbol":s,**m} for s,m in SYMS.items()],
      "costs":{"fee_bps_per_fill":FEE_BPS,"slippage_bps_per_fill":SLIPPAGE_BPS,"fixed_risk_usd":RISK},
      "assumptions":{"Track_A":"disabled","Track_B":"production defaults frozen; no OOS tuning",
                     "management":"TP1 30% => BE; TP2 30% => TP1; runner 40% confirmed 4H pivot",
                     "same_15m_bar":"STOP evaluated before TP","one_symbol_one_position":True},
      "totals":total,
      "by_year":by_year,
      "by_symbol":by_symbol,
      "per_symbol":results,
      "errors":errors,
      "trades":all_trades
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("FINAL_SUMMARY",json.dumps({k:v for k,v in report.items() if k not in ("trades","per_symbol")},ensure_ascii=False),flush=True)

if __name__=="__main__":
    main()
