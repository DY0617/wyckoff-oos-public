import json, math, statistics
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

UTC=timezone.utc
ROOT=Path(".")
DATA_DIR=ROOT/"data/tmp_us30x2_25y"
TRADES_PATH=ROOT/"data/validation/elliott_wave3_v4_dow2000_1h_long_25y.json"
OUT=ROOT/"data/validation/elliott_wave3_v4_dow2000_regime_diagnostic.json"

DOW2000=("MMM","AA","MO","AXP","BA","CAT","C","KO","DD","EK","XOM","GE","GM","HPQ",
         "HD","HON","INTC","IBM","IP","JNJ","JPM","MCD","MRK","MSFT","PG","SBC","UTX",
         "WMT","DIS","T")
KEEP=set(DOW2000+("SPY",))

def metrics(ts):
    o=sorted(ts,key=lambda z:(z["exit_t"],z["symbol"]))
    rs=[x["r"] for x in o]; pos=[r for r in rs if r>0]; neg=[r for r in rs if r<0]
    eq=peak=0.; dd=0.; cur=mx=0
    for r in rs:
        eq+=r; peak=max(peak,eq); dd=min(dd,eq-peak)
        if r<0:cur+=1;mx=max(mx,cur)
        else:cur=0
    return {"trades":len(o),"total_r":sum(rs),"avg_r":statistics.fmean(rs) if rs else None,
            "profit_factor":sum(pos)/abs(sum(neg)) if neg else None,
            "win_rate":len(pos)/len(o) if o else None,"max_drawdown_r":dd,
            "max_losing_streak":mx}

def load_daily():
    files=sorted(DATA_DIR.glob("us30x2_15m_*.parquet"))
    if len(files)!=6:raise RuntimeError(f"need 6 chunks, got {len(files)}")
    frames=[]
    for p in files:
        x=pd.read_parquet(p,columns=["ticker","t","c"])
        frames.append(x[x.ticker.isin(KEEP)])
    df=pd.concat(frames,ignore_index=True).drop_duplicates(["ticker","t"]).sort_values(["ticker","t"])
    df["date"]=pd.to_datetime(df["t"],unit="ms",utc=True).dt.tz_convert("America/New_York").dt.date
    daily=(df.groupby(["ticker","date"],as_index=False)
             .agg(t=("t","max"),c=("c","last"))
             .sort_values(["ticker","date"]))
    return daily

def build_features(daily):
    closes={}
    for sym,g in daily.groupby("ticker"):
        g=g.sort_values("date").copy()
        g["ret"]=g["c"].pct_change()
        g["sma200"]=g["c"].rolling(200,min_periods=120).mean()
        closes[sym]=g

    spy=closes["SPY"].copy()
    spy["ema200"]=spy["c"].ewm(span=200,adjust=False).mean()
    spy["ema200_20ago"]=spy["ema200"].shift(20)
    spy["ema_slope20_pct"]=spy["ema200"]/spy["ema200_20ago"]-1
    spy["dist_ema200_pct"]=spy["c"]/spy["ema200"]-1
    spy["rv20"]=spy["ret"].rolling(20,min_periods=15).std()*math.sqrt(252)

    # breadth on each date using only names with 200d state available.
    rows=[]
    all_dates=sorted(set(spy["date"]))
    idx={sym:{r.date:(r.c,r.sma200) for r in g.itertuples()} for sym,g in closes.items() if sym!="SPY"}
    spy_map={r.date:r for r in spy.itertuples()}
    for d in all_dates:
        vals=[]
        for sym in DOW2000:
            z=idx.get(sym,{}).get(d)
            if z and pd.notna(z[1]):
                vals.append(1 if z[0]>z[1] else 0)
        s=spy_map[d]
        rows.append({
            "date":d,
            "t":int(pd.Timestamp(d,tz="America/New_York").tz_convert("UTC").timestamp()*1000)+21*60*60*1000,
            "spy_close":float(s.c),
            "dist_ema200_pct":None if pd.isna(s.dist_ema200_pct) else float(s.dist_ema200_pct),
            "ema_slope20_pct":None if pd.isna(s.ema_slope20_pct) else float(s.ema_slope20_pct),
            "rv20":None if pd.isna(s.rv20) else float(s.rv20),
            "breadth200":(sum(vals)/len(vals) if vals else None),
            "breadth_n":len(vals),
        })
    return rows

def bucket(x,cuts,labels):
    if x is None:return "NA"
    for c,l in zip(cuts,labels):
        if x<c:return l
    return labels[-1]

def main():
    obj=json.loads(TRADES_PATH.read_text())
    trades=obj["trades"]
    feats=build_features(load_daily())
    ft=[x["t"] for x in feats]

    enriched=[]
    for t in trades:
        i=bisect_right(ft,t["signal_t"])-1
        q=dict(t)
        if i>=0:
            f=feats[i]
            for k in ("dist_ema200_pct","ema_slope20_pct","rv20","breadth200","breadth_n"):
                q[k]=f[k]
        q["era"]="PRE2014" if datetime.fromtimestamp(t["signal_t"]/1000,UTC).year<2014 else "2014PLUS"
        q["trend_dist_bucket"]=bucket(q.get("dist_ema200_pct"),[-0.05,0,0.05,10],["<-5%","-5..0%","0..5%",">=5%"])
        q["vol_bucket"]=bucket(q.get("rv20"),[0.15,0.25,0.40,10],["<15%","15..25%","25..40%",">=40%"])
        q["breadth_bucket"]=bucket(q.get("breadth200"),[0.40,0.60,0.75,2],["<40%","40..60%","60..75%",">=75%"])
        q["trend_up"]=bool(q.get("dist_ema200_pct") is not None and q["dist_ema200_pct"]>0 and q.get("ema_slope20_pct") is not None and q["ema_slope20_pct"]>0)
        q["quality_regime"]=bool(q["trend_up"] and q.get("breadth200") is not None and q["breadth200"]>=0.60 and q.get("rv20") is not None and q["rv20"]<0.30)
        q["broad_regime"]=bool(q.get("breadth200") is not None and q["breadth200"]>=0.50 and q.get("rv20") is not None and q["rv20"]<0.35)
        enriched.append(q)

    def grouped(key):
        g=defaultdict(list)
        for t in enriched:g[str(t[key])].append(t)
        return {k:metrics(v) for k,v in sorted(g.items())}

    candidates={}
    for name,pred in {
        "BASELINE":lambda t:True,
        "TREND_UP":lambda t:t["trend_up"],
        "BREADTH_GE_50":lambda t:t.get("breadth200") is not None and t["breadth200"]>=0.50,
        "BREADTH_GE_60":lambda t:t.get("breadth200") is not None and t["breadth200"]>=0.60,
        "VOL_LT_30":lambda t:t.get("rv20") is not None and t["rv20"]<0.30,
        "VOL_LT_35":lambda t:t.get("rv20") is not None and t["rv20"]<0.35,
        "QUALITY_REGIME":lambda t:t["quality_regime"],
        "BROAD_REGIME":lambda t:t["broad_regime"],
    }.items():
        q=[t for t in enriched if pred(t)]
        candidates[name]={
            "all":metrics(q),
            "pre2014":metrics([t for t in q if t["era"]=="PRE2014"]),
            "post2014":metrics([t for t in q if t["era"]=="2014PLUS"]),
        }

    report={
      "strategy":"Elliott v4 DJIA2000 regime diagnostic",
      "purpose":"Post-hoc diagnosis only; not validation. Predefined coarse market-state bins and simple candidate filters.",
      "baseline":metrics(enriched),
      "era":grouped("era"),
      "trend_distance":grouped("trend_dist_bucket"),
      "realized_volatility":grouped("vol_bucket"),
      "breadth200":grouped("breadth_bucket"),
      "candidates":candidates,
      "feature_notes":{
        "dist_ema200_pct":"SPY close / EMA200 - 1 on last completed RTH day before signal",
        "ema_slope20_pct":"SPY EMA200 / EMA200 20 sessions ago - 1",
        "rv20":"SPY 20-session close-to-close realized vol annualized",
        "breadth200":"fraction of available frozen DJIA2000 names closing above their own SMA200",
        "quality_regime":"SPY>EMA200, EMA200 rising, breadth>=60%, rv20<30%",
        "broad_regime":"breadth>=50%, rv20<35%"
      },
      "trades":enriched
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k!="trades"},indent=2))

if __name__=="__main__":main()
