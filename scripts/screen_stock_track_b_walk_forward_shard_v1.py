import json, os, sys, time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

sys.path.insert(0,str(Path(__file__).parent))
import backtest_wyckoff_stock_filter_engine_exact_conservative_ratchet as bt
import evaluate_stock53_filter_factorial_shard as ctxsrc
import wyckoff_status as w

UTC=timezone.utc; NY=ZoneInfo("America/New_York")
START=datetime.strptime(os.environ["EVAL_START"],"%Y-%m-%d").replace(tzinfo=UTC)
END=datetime.strptime(os.environ["EVAL_END"],"%Y-%m-%d").replace(tzinfo=UTC)
WARMUP=datetime.strptime(os.environ.get("WARMUP_START",os.environ["EVAL_START"]),"%Y-%m-%d").replace(tzinfo=UTC)
START_MS=int(START.timestamp()*1000); END_MS=int(END.timestamp()*1000)-1
HF_BASE="https://huggingface.co/datasets/mito0o852/OHLCV-1m/resolve/main/data"
TRADE_SYMS=tuple(x for x in os.environ["TRADE_SYMS"].split(",") if x)
OUT=Path(os.environ["OUT"])
FEE_BPS=4.0; SLIPPAGE_BPS=2.0
A_OFF={"climax_spread_min":999.0,"climax_volume_min":999.0}

BASE={
  "range_max_atr":12.0,"range_er_max":0.80,"penetration_min":0.25,"penetration_max":2.50,
  "test_overlap_atr":1.50,"test_spread_max":1.25,"test_volume_max":1.05,
  "entry_buffer_atr":0.05,"stop_buffer_atr":0.25,
  "rr_long_min":1.10,"rr_long_max":2.00,
  "target_distance_atr":3.50,"return30_min":-0.05,"ema_gap_atr_max":2.0,"trigger_window":9
}
GRID={
  "range_max_atr":(8.0,16.0),
  "range_er_max":(0.60,0.95),
  "penetration_min":(0.15,0.40),
  "penetration_max":(1.75,3.25),
  "test_overlap_atr":(1.00,2.00),
  "test_spread_max":(1.00,1.50),
  "test_volume_max":(0.85,1.25),
  "entry_buffer_atr":(0.00,0.10),
  "stop_buffer_atr":(0.15,0.40),
  "rr_long_min":(0.90,1.30),
  "rr_long_max":(1.75,2.50),
  "target_distance_atr":(2.50,5.00),
  "return30_min":(-0.10,0.00),
  "ema_gap_atr_max":(1.50,3.00),
  "trigger_window":(6,12),
}
STAGE1_CONFIGS=[("baseline",{})]
for p,(lo,hi) in GRID.items():
    STAGE1_CONFIGS.append((f"{p}__low",{p:lo}))
    STAGE1_CONFIGS.append((f"{p}__high",{p:hi}))

def month_iter(a,b):
    y,m=a.year,a.month
    while (y,m)<(b.year,b.month):
        yield y,m
        m+=1
        if m==13:y,m=y+1,1

def source_tickers():
    xs=set(TRADE_SYMS)
    if "META" in xs:xs.add("FB")
    if "GOOGL" in xs:xs.add("GOOG")
    return tuple(sorted(xs))

def canonical(ticker,d):
    if ticker=="FB":return "META" if d<datetime(2022,6,9).date() and "META" in TRADE_SYMS else None
    if ticker=="META":return "META" if d>=datetime(2022,6,9).date() and "META" in TRADE_SYMS else None
    if ticker=="GOOG":return "GOOGL" if d<datetime(2014,4,3).date() and "GOOGL" in TRADE_SYMS else None
    if ticker=="GOOGL":return "GOOGL" if d>=datetime(2014,4,3).date() and "GOOGL" in TRADE_SYMS else None
    return ticker if ticker in TRADE_SYMS else None

def remote_15m(con,y,m):
    srcs=source_tickers();ph=",".join(["?"]*len(srcs))
    url=f"{HF_BASE}/ohlcv_{y:04d}-{m:02d}.parquet"
    q=f"""
    WITH src AS (
      SELECT ticker,timezone('America/New_York',timestamp) et,open,high,low,"close",volume
      FROM read_parquet('{url}') WHERE ticker IN ({ph})
    ),rth AS (
      SELECT * FROM src
      WHERE cast(et as time)>=time '09:30:00' and cast(et as time)<time '16:00:00'
    ),agg AS (
      SELECT ticker,time_bucket(interval '15 minutes',et) b,
             arg_min(open,et) o,max(high) h,min(low) l,arg_max("close",et) c,sum(volume) v
      FROM rth GROUP BY ticker,b
    )
    SELECT ticker,b,o,h,l,c,v FROM agg ORDER BY ticker,b
    """
    return con.execute(q,list(srcs)).fetchall()

def collect_15m():
    cache=os.environ.get("DATA_PARQUET")
    if cache and Path(cache).exists():
        con=duckdb.connect()
        ph=",".join(["?"]*len(TRADE_SYMS))
        rows=con.execute(f"SELECT symbol,b,o,h,l,c,v FROM read_parquet(?) WHERE symbol IN ({ph}) ORDER BY symbol,b",[cache,*TRADE_SYMS]).fetchall()
        con.close()
        by={s:[] for s in TRADE_SYMS}
        for s,et,o,h,l,cl,v in rows:
            if et.tzinfo is None:et=et.replace(tzinfo=NY)
            else:et=et.astimezone(NY)
            t=int(et.astimezone(UTC).timestamp()*1000)
            by[str(s)].append({"t":t,"o":float(o),"h":float(h),"l":float(l),"c":float(cl),"v":float(v or 0)})
        print("CACHE_15M",cache,{s:len(v) for s,v in by.items()},flush=True)
        return by

    con=duckdb.connect();con.execute("INSTALL httpfs; LOAD httpfs;")
    by={s:[] for s in TRADE_SYMS};missing=[]
    for y,m in month_iter(WARMUP,END):
        rows=None
        for a in range(5):
            try:
                t0=time.time();rows=remote_15m(con,y,m)
                print("15M_MONTH",f"{y:04d}-{m:02d}",len(rows),round(time.time()-t0,2),flush=True);break
            except Exception as e:
                print("15M_RETRY",y,m,a+1,repr(e),flush=True);time.sleep(3*(a+1))
        if rows is None:
            missing.append(f"{y:04d}-{m:02d}");continue
        for ticker,et,o,h,l,cl,v in rows:
            d=et.date()
            s=canonical(str(ticker),d)
            if not s:continue
            if et.tzinfo is None:et=et.replace(tzinfo=NY)
            else:et=et.astimezone(NY)
            t=int(et.astimezone(UTC).timestamp()*1000)
            by[s].append({"t":t,"o":float(o),"h":float(h),"l":float(l),"c":float(cl),"v":float(v or 0)})
    con.close()
    if missing:raise RuntimeError("missing 15m months="+",".join(missing))
    for s in by:by[s].sort(key=lambda z:z["t"])
    return by

def day_key(z):
    return datetime.fromtimestamp(z["t"]/1000,UTC).astimezone(NY).date()

def detect_splits(bars):
    byday=defaultdict(list)
    for z in bars:byday[day_key(z)].append(z)
    days=sorted(byday);common=(2,3,4,5,7,10,15,20);ev=[]
    for i in range(1,len(days)):
        prev=byday[days[i-1]][-1]["c"];op=byday[days[i]][0]["o"]
        if prev<=0 or op<=0:continue
        ratio=prev/op;mag=ratio if ratio>=1 else 1/ratio
        if mag<1.7:continue
        f=min(common,key=lambda q:abs(mag/q))
        if abs(mag/f)<=.08:
            pm,vm=((1/f,f) if ratio>1 else (f,1/f))
            ev.append((days[i],pm,vm))
    return ev

def apply_splits(bars,ev):
    out=[]
    for z in bars:
        d=day_key(z);pm=vm=1.0
        for sd,p,v in ev:
            if d<sd:pm*=p;vm*=v
        q=z.copy()
        for k in ("o","h","l","c"):q[k]*=pm
        q["v"]*=vm;out.append(q)
    return out

def aggregate_4h(bars):
    groups=defaultdict(list)
    for z in bars:
        dt=datetime.fromtimestamp(z["t"]/1000,UTC).astimezone(NY)
        mins=(dt.hour*60+dt.minute)-570
        bucket=0 if mins<240 else 1
        groups[(dt.date(),bucket)].append(z)
    out=[]
    for _,g in sorted(groups.items()):
        g.sort(key=lambda x:x["t"])
        out.append({"t":g[0]["t"],"o":g[0]["o"],"h":max(x["h"] for x in g),
                    "l":min(x["l"] for x in g),"c":g[-1]["c"],"v":sum(x["v"] for x in g),
                    "ct":g[-1]["t"]+15*60*1000-1})
    return out

def aggregate_daily(bars):
    groups=defaultdict(list)
    for z in bars:groups[day_key(z)].append(z)
    out=[]
    for _,g in sorted(groups.items()):
        g.sort(key=lambda x:x["t"])
        out.append({"t":g[0]["t"],"o":g[0]["o"],"h":max(x["h"] for x in g),
                    "l":min(x["l"] for x in g),"c":g[-1]["c"],"v":sum(x["v"] for x in g),
                    "ct":g[-1]["t"]+15*60*1000-1})
    return out

def build_context():
    cache=os.environ.get("DATA_PARQUET")
    if cache and Path(cache).exists():
        con=duckdb.connect()
        rows=con.execute("""
          SELECT symbol,cast(b as date) d,min(b) first_b,max(b) last_b,
                 arg_min(o,b) o,max(h) h,min(l) l,arg_max(c,b) c,sum(v) v
          FROM read_parquet(?)
          GROUP BY symbol,cast(b as date)
          ORDER BY symbol,d
        """,[cache]).fetchall()
        con.close()
        by={s:[] for s in ctxsrc.SYMS}
        for s,d,first_b,last_b,o,h,l,cl,v in rows:
            s=str(s)
            if s not in by:continue
            if s=="SNDK" and d<datetime(2025,2,24).date():continue
            et=first_b.replace(tzinfo=NY) if first_b.tzinfo is None else first_b.astimezone(NY)
            z=last_b.replace(tzinfo=NY) if last_b.tzinfo is None else last_b.astimezone(NY)
            by[s].append({"t":int(et.astimezone(UTC).timestamp()*1000),
                          "o":float(o),"h":float(h),"l":float(l),"c":float(cl),"v":float(v or 0),
                          "ct":int(z.astimezone(UTC).timestamp()*1000)+15*60*1000-1})
        dailies={}
        for s,bars in by.items():
            bars=ctxsrc.apply_splits(bars,ctxsrc.detect_splits(bars))
            if bars:dailies[s]=w.enrich(bars)
        print("CTX_CACHE",len(dailies),flush=True)
        return dailies

    by,months=ctxsrc.collect()
    d={}
    for s in ctxsrc.SYMS:
        bars=ctxsrc.apply_splits(by[s],ctxsrc.detect_splits(by[s]))
        if bars:d[s]=w.enrich(bars)
    print("CTX_DAILY",len(d),"months",months,flush=True)
    return d

def overlay_state(sym,dailies,entry_t):
    D=dailies.get(sym);S=dailies.get("SPY")
    if not D or not S:return None
    i=ctxsrc.latest_idx(D,entry_t);si=ctxsrc.latest_idx(S,entry_t)
    if i<50 or si<50:return None
    rr=ctxsrc.ret20(D,i);sr=ctxsrc.ret20(S,si)
    if rr is None or sr is None:return None
    q=S[si]
    votes=int(q["c"]>q["ema50"])+int(q["ema20"]>q["ema50"])+int(sr>0)
    above=eligible=0
    for U in dailies.values():
        ui=ctxsrc.latest_idx(U,entry_t)
        if ui>=50 and U[ui].get("ema50") is not None:
            eligible+=1;above+=int(U[ui]["c"]>U[ui]["ema50"])
    br=above/eligible if eligible else None
    return votes>=2 and rr>=sr and br is not None and br>=.50

def main():
    configs=STAGE1_CONFIGS
    config_file=os.environ.get("CONFIG_FILE")
    if config_file:
        z=json.loads(Path(config_file).read_text())
        configs=[(x["name"],x["overrides"]) for x in z["stage2_configs"]]
        print("USING_CONFIG_FILE",config_file,"n",len(configs),flush=True)
    raw=collect_15m()
    dailies=build_context()
    old_dataset,old_filters=bt.dataset,bt.symbol_filters
    old_cap,old_risk=bt.CAP,bt.RISK
    bt.CAP=20000.;bt.RISK=400.
    output={name:[] for name,_ in configs};errors={}
    try:
        for sym in TRADE_SYMS:
            try:
                bars=raw.get(sym,[])
                if len(bars)<1000:
                    print("SKIP_SHORT",sym,len(bars),flush=True);continue
                bars=apply_splits(bars,detect_splits(bars))
                H=w.enrich(aggregate_4h(bars));D=w.enrich(aggregate_daily(bars));M=bars
                bt.dataset=lambda _s,D=D,H=H,M=M:(D,H,M)
                bt.symbol_filters=lambda _s:(0.01,0.,0.)
                def tf(_sym,p,trigger_open_ms):
                    return p["direction"]=="LONG" and bool(overlay_state(sym,dailies,trigger_open_ms))
                for name,ov in configs:
                    bt._CACHE.clear()
                    r=bt.simulate(sym,a_params=A_OFF,b_params=ov,start_ms=START_MS,end_ms=END_MS,
                                  fee_bps=FEE_BPS,slippage_bps=SLIPPAGE_BPS,
                                  a_mode="snapshot",b_runner_mode="pivot",b_scale_mode="10_30_60",
                                  trigger_filter=tf)
                    ts=[{"symbol":sym,**t} for t in r["trades"]
                        if t["track"]=="B" and t["direction"]=="LONG" and t["reason"]!="OPEN_MARK"]
                    output[name].extend(ts)
                    print("CFG",sym,name,len(ts),round(sum(t["r"] for t in ts),4),flush=True)
            except Exception as e:
                errors[sym]=repr(e);print("SYMBOL_ERROR",sym,repr(e),flush=True)
    finally:
        bt.dataset,bt.symbol_filters=old_dataset,old_filters
        bt.CAP,bt.RISK=old_cap,old_risk

    payload={
      "trade_symbols":list(TRADE_SYMS),
      "period":{"start":START.isoformat(),"end_exclusive":END.isoformat()},
      "baseline":BASE,"grid":GRID,
      "configs":{name:ov for name,ov in configs},
      "trades":output,"errors":errors
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(payload,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    print("DONE_WALK_FORWARD_V1",json.dumps({k:len(v) for k,v in output.items()}),flush=True)

if __name__=="__main__":main()
