import bisect, json, math, os, sys, time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

sys.path.insert(0, str(Path(__file__).parent))
import backtest_wyckoff_stock_filter_engine_exact_conservative_ratchet as bt
import wyckoff_status as w

ALL_SYMS=(
"AAPL","AMZN","AVGO","CRCL","DELL","MSFT","MU","SNDK","SNXX","SOXL","SPCX",
"AMD","BABA","INTC","JPM","KORU","MSTR","NFLX","SKHY","SMCI","SOXS","V",
"COST","GOOGL","LLY","META","NBIS","NVDA","QQQ","TSLA","UBER","WMT",
"AMAT","CAT","DRAM","EWY","HD","MRVL","MUU","ORCL","SPY","TSM",
"AAOI","AXTI","BE","COIN","CRM","CSCO","DIS","HOOD","IBM","LITE","TQQQ"
)
SYMS=tuple(x for x in os.environ.get("TRADE_SYMS",",".join(ALL_SYMS)).split(",") if x)
# Historical aliases for the same security/economic issuer. GOOG is used only before
# the 2014 share-class split; FB is used only before the META ticker change.
SOURCE_TICKERS=tuple(sorted(set(ALL_SYMS+("FB","GOOG"))))
HF_BASE="https://huggingface.co/datasets/mito0o852/OHLCV-1m/resolve/main/data"
NY=ZoneInfo("America/New_York")
UTC=timezone.utc
FEE_BPS=4.0
SLIPPAGE_BPS=2.0
A_OFF={"climax_spread_min":999.0,"climax_volume_min":999.0}

# Avoid accidentally stitching extinct/reused ticker incarnations to today's security.
NOT_BEFORE={
    "DELL": datetime(2018,12,28,tzinfo=UTC),
    "SNDK": datetime(2025,2,24,tzinfo=UTC),
}

def parse_date(s):
    return datetime.strptime(s,"%Y-%m-%d").replace(tzinfo=UTC)

EVAL_START=parse_date(os.environ["EVAL_START"])
EVAL_END=parse_date(os.environ["EVAL_END"])  # exclusive entry boundary
DATA_END=min(parse_date(os.environ.get("DATA_END","2026-04-01")), EVAL_END+timedelta(days=90))
WARMUP_START=EVAL_START-timedelta(days=190)
OUT=Path(os.environ.get("OUT",f"data/validation/stock53_track_b_hf20y_{EVAL_START.date()}_{EVAL_END.date()}.json"))

def month_iter(start,end):
    y,m=start.year,start.month
    stop=(end.year,end.month)
    while (y,m)<=stop:
        yield y,m
        m+=1
        if m==13: y,m=y+1,1

def canonical_ticker(ticker,et):
    d=et.date()
    if ticker=="FB":
        return "META" if d < datetime(2022,6,9).date() else None
    if ticker=="META":
        return "META" if d >= datetime(2022,6,9).date() else None
    if ticker=="GOOG":
        return "GOOGL" if d < datetime(2014,4,3).date() else None
    if ticker=="GOOGL":
        return "GOOGL" if d >= datetime(2014,4,3).date() else None
    return ticker if ticker in ALL_SYMS else None

def remote_15m(con,y,m):
    url=f"{HF_BASE}/ohlcv_{y:04d}-{m:02d}.parquet"
    placeholders=",".join(["?"]*len(SOURCE_TICKERS))
    q=f"""
    WITH src AS (
      SELECT ticker, timezone('America/New_York', timestamp) AS et,
             open,high,low,close,volume
      FROM read_parquet('{url}')
      WHERE ticker IN ({placeholders})
    ), rth AS (
      SELECT * FROM src
      WHERE CAST(et AS TIME) >= TIME '09:30:00'
        AND CAST(et AS TIME) <  TIME '16:00:00'
    ), agg AS (
      SELECT ticker,time_bucket(INTERVAL '15 minutes',et) et_bucket,
             arg_min(open,et) open,max(high) high,min(low) low,
             arg_max(close,et) close_px,sum(volume) volume,
             max(et) last_et
      FROM rth GROUP BY ticker,et_bucket
    )
    SELECT ticker,et_bucket,open,high,low,close_px,volume
    FROM agg ORDER BY ticker,et_bucket
    """
    t0=time.time()
    rows=con.execute(q,list(SOURCE_TICKERS)).fetchall()
    print("MONTH",f"{y:04d}-{m:02d}","rows15",len(rows),"sec",round(time.time()-t0,1),flush=True)
    return rows

def collect():
    con=duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    bysym={s:[] for s in ALL_SYMS}
    missing=[]
    months=0
    for y,m in month_iter(WARMUP_START,DATA_END-timedelta(days=1)):
        try:
            last_err=None
            rows=None
            for attempt in range(6):
                try:
                    rows=remote_15m(con,y,m)
                    break
                except Exception as e:
                    last_err=e
                    print("MONTH_RETRY",y,m,"attempt",attempt+1,repr(e),flush=True)
                    time.sleep(min(45,5*(attempt+1)))
            if rows is None:
                raise last_err
            months+=1
            for ticker,et,o,h,l,c,v in rows:
                if et.tzinfo is None: et=et.replace(tzinfo=NY)
                else: et=et.astimezone(NY)
                canon=canonical_ticker(str(ticker),et)
                if not canon: continue
                utc=et.astimezone(UTC)
                nb=NOT_BEFORE.get(canon)
                if nb and utc < nb: continue
                # Trim exact data window (month files straddle boundaries).
                if utc < WARMUP_START or utc >= DATA_END: continue
                bysym[canon].append({
                    "t":int(utc.timestamp()*1000),
                    "o":float(o),"h":float(h),"l":float(l),"c":float(c),
                    "v":float(v or 0.0),"ct":int(utc.timestamp()*1000)+15*60*1000-1
                })
        except Exception as e:
            print("MONTH_ERROR",y,m,repr(e),flush=True)
            missing.append(f"{y:04d}-{m:02d}")
    con.close()
    for s in bysym: bysym[s].sort(key=lambda z:z["t"])
    return bysym,months,missing

def day_key(z):
    return datetime.fromtimestamp(z["t"]/1000,UTC).astimezone(NY).date()

def detect_splits(bars):
    byday=defaultdict(list)
    for z in bars: byday[day_key(z)].append(z)
    days=sorted(byday)
    common=(1.5,2,3,4,5,7,10,15,20)
    events=[]
    for i in range(1,len(days)):
        prev=byday[days[i-1]][-1]["c"]; op=byday[days[i]][0]["o"]
        if prev<=0 or op<=0: continue
        # Do not treat long listing/data gaps as a stock split.
        if (days[i]-days[i-1]).days>14: continue
        ratio=prev/op; mag=ratio if ratio>=1 else 1/ratio
        if mag<1.35: continue
        f=min(common,key=lambda q:abs(mag/q-1.0))
        if abs(mag/f-1.0)<=0.05:
            pm,vm=((1/f,f) if ratio>1 else (f,1/f))
            events.append({"date":str(days[i]),"factor":f,"price_mult_before":pm,"volume_mult_before":vm,
                           "raw_prevclose_open_ratio":ratio})
    return events

def apply_splits(bars,events):
    if not events: return bars
    parsed=[(datetime.fromisoformat(e["date"]).date(),e["price_mult_before"],e["volume_mult_before"]) for e in events]
    out=[]
    for z in bars:
        d=day_key(z); pm=vm=1.0
        for sd,p,v in parsed:
            if d<sd: pm*=p; vm*=v
        q=z.copy()
        for k in ("o","h","l","c"): q[k]*=pm
        q["v"]*=vm; out.append(q)
    return out

def aggregate_4h(bars):
    groups=defaultdict(list)
    for z in bars:
        dt=datetime.fromtimestamp(z["t"]/1000,UTC).astimezone(NY)
        mins=(dt.hour*60+dt.minute)-(9*60+30)
        bucket=0 if mins<240 else 1
        groups[(dt.date(),bucket)].append(z)
    out=[]
    for _,g in sorted(groups.items()):
        g.sort(key=lambda x:x["t"])
        out.append({"t":g[0]["t"],"o":g[0]["o"],"h":max(x["h"] for x in g),"l":min(x["l"] for x in g),
                    "c":g[-1]["c"],"v":sum(x["v"] for x in g),"ct":g[-1]["ct"]})
    return out

def aggregate_daily(bars):
    groups=defaultdict(list)
    for z in bars: groups[day_key(z)].append(z)
    out=[]
    for _,g in sorted(groups.items()):
        g.sort(key=lambda x:x["t"])
        out.append({"t":g[0]["t"],"o":g[0]["o"],"h":max(x["h"] for x in g),"l":min(x["l"] for x in g),
                    "c":g[-1]["c"],"v":sum(x["v"] for x in g),"ct":g[-1]["ct"]})
    return out

def stats(ts):
    n=len(ts); wins=sum(t["pnl"]>0 for t in ts); losses=sum(t["pnl"]<0 for t in ts)
    net=sum(t["r"] for t in ts); gp=sum(t["r"] for t in ts if t["r"]>0); gl=sum(t["r"] for t in ts if t["r"]<0)
    return {"closed":n,"wins":wins,"losses":losses,"win_rate":wins/n if n else None,
            "net_r":net,"avg_r":net/n if n else None,"profit_factor":gp/abs(gl) if gl<0 else None}

def latest_idx(D,entry_t):
    cts=[x.get("ct",x["t"]+24*60*60*1000-1) for x in D]
    return bisect.bisect_left(cts,entry_t)-1

def ret20(D,i):
    if i<20 or D[i-20]["c"]<=0:return None
    return D[i]["c"]/D[i-20]["c"]-1

def e_state(sym,dailies,entry_t):
    D=dailies.get(sym);spyD=dailies.get("SPY")
    if not D or not spyD:return None
    i=latest_idx(D,entry_t);si=latest_idx(spyD,entry_t)
    if i<50 or si<50:return None
    rr=ret20(D,i);sr=ret20(spyD,si)
    if rr is None or sr is None:return None
    s=spyD[si]
    bull_votes=int(s["c"]>s["ema50"])+int(s["ema20"]>s["ema50"])+int(sr>0)
    eligible=above=0
    for _,UD in dailies.items():
        ui=latest_idx(UD,entry_t)
        if ui>=50 and UD[ui].get("ema50") is not None:
            eligible+=1
            above+=int(UD[ui]["c"]>UD[ui]["ema50"])
    breadth=(above/eligible) if eligible else None
    return {
      "bull_regime":bull_votes>=2,
      "stock_ret20":rr,"spy_ret20":sr,
      "rs_ok":rr>=sr,
      "breadth":breadth,
      "breadth_ok":breadth is not None and breadth>=.50,
      "eligible_breadth":eligible
    }


CONFIGS={
 "baseline":{},
 "er06":{"range_er_max":0.6},
}
TP1_FRAC=0.15
TP2_FRAC=0.15

def recalc_ratio_trade(t,f1,f2):
    # All three tested modes keep a non-zero runner, so the stop/trailing path
    # and position holding time are identical; only realized fractions change.
    sign=1 if t["direction"]=="LONG" else -1
    entry=float(t["entry"]); size=float(t["size"]); risk=abs(entry-float(t["stop"]))
    cost=(FEE_BPS+SLIPPAGE_BPS)/10000.0
    realized=-size*entry*cost
    remain=1.0
    for e in t.get("events",[]):
        typ=e.get("type")
        if typ=="TP1":
            frac=min(f1,remain); px=float(e["price"])
            realized += frac*sign*(px-entry)*size - frac*size*px*cost
            remain-=frac
        elif typ=="TP2":
            frac=min(f2,remain); px=float(e["price"])
            realized += frac*sign*(px-entry)*size - frac*size*px*cost
            remain-=frac
        elif typ in ("STOP","BE","OPEN_MARK","FIB1618_FULL","FIB1618_PARTIAL"):
            if remain<=1e-12: break
            px=float(e["price"]); frac=remain
            realized += frac*sign*(px-entry)*size - frac*size*px*cost
            remain=0.0
            break
    if remain>1e-9:
        raise RuntimeError(f"ratio replay left open fraction={remain} symbol={t.get('symbol')}")
    q=dict(t); q["pnl"]=realized; q["r"]=realized/400.0
    q["ratio"]=[f1,f2,1.0-f1-f2]
    return q

def main():
    bysym,months,missing=collect()
    if months == 0:
        raise RuntimeError("HF parquet load failed: zero months loaded")
    if missing:
        raise RuntimeError("HF parquet load incomplete: missing months=" + ",".join(missing))

    # First build every symbol's enriched daily/4H/15m series. The E filter
    # needs prior completed daily bars for SPY and the full breadth universe at
    # the actual first 15m entry touch, so this must be a two-pass evaluation.
    prepared={}; dailies={}; errors={}
    for sym in ALL_SYMS:
        try:
            bars=apply_splits(bysym[sym],detect_splits(bysym[sym]))
            if not bars: raise RuntimeError("no bars")
            H=w.enrich(aggregate_4h(bars)); D=w.enrich(aggregate_daily(bars)); M=bars
            if len(D)<60 or len(H)<60:
                raise RuntimeError(f"insufficient warmup D={len(D)} H={len(H)} M={len(M)}")
            prepared[sym]=(D,H,M); dailies[sym]=D
        except Exception as e:
            errors[sym]=repr(e)
            print("PREP_ERROR",sym,repr(e),flush=True)

    eval_start_ms=int(EVAL_START.timestamp()*1000)
    eval_end_ms=int(EVAL_END.timestamp()*1000)
    engine_end_ms=int(DATA_END.timestamp()*1000)-1
    config_trades={name:[] for name in CONFIGS}
    old_dataset,old_filters=bt.dataset,bt.symbol_filters
    old_cap,old_risk=bt.CAP,bt.RISK
    bt.CAP=20000.0; bt.RISK=400.0

    def entry_gate(sym,p,entry_t):
        st=e_state(sym,dailies,entry_t)
        return bool(st and p.get("direction")=="LONG" and st["bull_regime"] and st["rs_ok"] and st["breadth_ok"])

    try:
        for cfg_name,b_params in CONFIGS.items():
            for sym in SYMS:
                if sym not in prepared: continue
                D,H,M=prepared[sym]
                try:
                    bt._CACHE.clear()
                    bt.dataset=lambda _s,D=D,H=H,M=M:(D,H,M)
                    bt.symbol_filters=lambda _s:(0.01,0.0,0.0)
                    r=bt.simulate(
                        sym,a_params=A_OFF,b_params=b_params,
                        start_ms=eval_start_ms,end_ms=engine_end_ms,
                        fee_bps=FEE_BPS,slippage_bps=SLIPPAGE_BPS,
                        a_mode="snapshot",b_runner_mode="pivot",b_scale_mode="10_30_60",
                        trigger_filter=entry_gate
                    )
                    raw=[{"symbol":sym,**t} for t in r["trades"]
                         if t["track"]=="B" and t["reason"]!="OPEN_MARK"
                         and eval_start_ms<=t["entry_t"]<eval_end_ms]
                    ts=[recalc_ratio_trade(t,TP1_FRAC,TP2_FRAC) for t in raw]
                    config_trades[cfg_name].extend(ts)
                    print("RESULT",cfg_name,sym,stats(ts),flush=True)
                except Exception as e:
                    errors[f"{cfg_name}:{sym}"]=repr(e); print("SYMBOL_ERROR",cfg_name,sym,repr(e),flush=True)
    finally:
        bt.dataset,bt.symbol_filters=old_dataset,old_filters
        bt.CAP,bt.RISK=old_cap,old_risk

    for name in config_trades:
        config_trades[name].sort(key=lambda t:(t["entry_t"],t["symbol"]))

    report={
      "generated_at":datetime.now(UTC).isoformat(),
      "strategy":"Track-B baseline vs ER0.6; exact 15m touch; actual-entry E filter; conservative same-bar TP1=>BE / TP2=>TP1 ratchet; confirmed RTH 4H pivot runner",
      "configs":CONFIGS,
      "ratio":[TP1_FRAC,TP2_FRAC,1.0-TP1_FRAC-TP2_FRAC],
      "shard":{"eval_start":EVAL_START.isoformat(),"eval_end_exclusive":EVAL_END.isoformat(),
               "warmup_start":WARMUP_START.isoformat(),"data_end":DATA_END.isoformat()},
      "e_definition":"LONG + prior completed SPY bull regime >=2/3 + stock 20d return >= SPY 20d return + >=50% universe above EMA50, evaluated at actual first exact-touch 15m entry bar",
      "data":{"provider":"Hugging Face mito0o852/OHLCV-1m (Finnhub-origin)",
              "session":"09:30-16:00 America/New_York","source_resolution":"1m","execution_resolution":"15m",
              "aggregation":"RTH 1m -> 15m -> actual-close 4H/stub + daily",
              "months_loaded":months,"missing_months":missing},
      "costs":{"fee_bps_per_fill":FEE_BPS,"slippage_bps_per_fill":SLIPPAGE_BPS},
      "trade_syms":list(SYMS),
      "results":{name:{"summary":stats(ts),"trades":ts} for name,ts in config_trades.items()},
      "errors":errors
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("FINAL",json.dumps({k:stats(v) for k,v in config_trades.items()},ensure_ascii=False),flush=True)

if __name__=="__main__":
    main()
