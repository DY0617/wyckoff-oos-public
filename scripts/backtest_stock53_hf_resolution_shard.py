import json, os, sys, time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

sys.path.insert(0, str(Path(__file__).parent))
import backtest_wyckoff_exact_touch_resolution as bt
import wyckoff_status as w

SYMS=(
"AAPL","AMZN","AVGO","CRCL","DELL","MSFT","MU","SNDK","SNXX","SOXL","SPCX",
"AMD","BABA","INTC","JPM","KORU","MSTR","NFLX","SKHY","SMCI","SOXS","V",
"COST","GOOGL","LLY","META","NBIS","NVDA","QQQ","TSLA","UBER","WMT",
"AMAT","CAT","DRAM","EWY","HD","MRVL","MUU","ORCL","SPY","TSM",
"AAOI","AXTI","BE","COIN","CRM","CSCO","DIS","HOOD","IBM","LITE","TQQQ"
)
SOURCE_TICKERS=tuple(sorted(set(SYMS+("FB","GOOG"))))
HF_BASE="https://huggingface.co/datasets/mito0o852/OHLCV-1m/resolve/main/data"
NY=ZoneInfo("America/New_York")
UTC=timezone.utc
FEE_BPS=4.0
SLIPPAGE_BPS=2.0
A_OFF={"climax_spread_min":999.0,"climax_volume_min":999.0}
NOT_BEFORE={
    "DELL": datetime(2018,12,28,tzinfo=UTC),
    "SNDK": datetime(2025,2,24,tzinfo=UTC),
}

def parse_date(s):
    return datetime.strptime(s,"%Y-%m-%d").replace(tzinfo=UTC)

EVAL_START=parse_date(os.environ["EVAL_START"])
EVAL_END=parse_date(os.environ["EVAL_END"])
DATA_END=min(parse_date(os.environ.get("DATA_END","2026-04-01")),EVAL_END+timedelta(days=90))
WARMUP_START=EVAL_START-timedelta(days=190)
OUT=Path(os.environ["OUT"])

def month_iter(start,end):
    y,m=start.year,start.month
    while (y,m)<=(end.year,end.month):
        yield y,m
        m+=1
        if m==13:y,m=y+1,1

def build_local_db():
    db=Path("hf_resolution_tmp.duckdb")
    if db.exists(): db.unlink()
    con=duckdb.connect(str(db))
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("create table bars(ticker varchar, et timestamp, o double, h double, l double, c double, v double)")
    ph=",".join(["?"]*len(SOURCE_TICKERS))
    missing=[]; loaded=0
    for y,m in month_iter(WARMUP_START,DATA_END-timedelta(days=1)):
        url=f"{HF_BASE}/ohlcv_{y:04d}-{m:02d}.parquet"
        q=f"""
        insert into bars
        select ticker, timezone('America/New_York', timestamp) et,
               cast(open as double),cast(high as double),cast(low as double),
               cast("close" as double),cast(volume as double)
        from read_parquet('{url}')
        where ticker in ({ph})
          and cast(timezone('America/New_York', timestamp) as time)>=time '09:30:00'
          and cast(timezone('America/New_York', timestamp) as time)< time '16:00:00'
        """
        err=None
        for attempt in range(4):
            try:
                t=time.time(); con.execute(q,list(SOURCE_TICKERS)); loaded+=1
                print("MONTH",f"{y:04d}-{m:02d}","sec",round(time.time()-t,2),flush=True)
                err=None; break
            except Exception as e:
                err=e
                print("MONTH_RETRY",f"{y:04d}-{m:02d}",attempt+1,repr(e),flush=True)
                time.sleep(3*(attempt+1))
        if err is not None: missing.append(f"{y:04d}-{m:02d}")
    if missing:
        raise RuntimeError("missing months: "+",".join(missing))
    return con,loaded

def source_where(sym):
    if sym=="META":
        return "((ticker='FB' and cast(et as date)<date '2022-06-09') or (ticker='META' and cast(et as date)>=date '2022-06-09'))"
    if sym=="GOOGL":
        return "((ticker='GOOG' and cast(et as date)<date '2014-04-03') or (ticker='GOOGL' and cast(et as date)>=date '2014-04-03'))"
    return "ticker='"+sym.replace("'","''")+"'"

def load_symbol(con,sym):
    where=source_where(sym)
    rows=con.execute(f"""
      select et,o,h,l,c,v from bars
      where {where}
      order by et
    """).fetchall()
    nb=NOT_BEFORE.get(sym)
    out=[]
    for et,o,h,l,c,v in rows:
        if et.tzinfo is None: et=et.replace(tzinfo=NY)
        else: et=et.astimezone(NY)
        utc=et.astimezone(UTC)
        if utc<WARMUP_START or utc>=DATA_END: continue
        if nb and utc<nb: continue
        t=int(utc.timestamp()*1000)
        out.append({"t":t,"o":float(o),"h":float(h),"l":float(l),"c":float(c),"v":float(v or 0),"ct":t+60_000-1})
    return out

def day_key(z):
    return datetime.fromtimestamp(z["t"]/1000,UTC).astimezone(NY).date()

def detect_splits(bars):
    byday=defaultdict(list)
    for z in bars: byday[day_key(z)].append(z)
    days=sorted(byday); common=(2,3,4,5,7,10,15,20); events=[]
    for i in range(1,len(days)):
        prev=byday[days[i-1]][-1]["c"]; op=byday[days[i]][0]["o"]
        if prev<=0 or op<=0 or (days[i]-days[i-1]).days>14: continue
        ratio=prev/op; mag=ratio if ratio>=1 else 1/ratio
        if mag<1.7: continue
        f=min(common,key=lambda q:abs(mag/q))
        if abs(mag/f)<=0.08:
            pm,vm=((1/f,f) if ratio>1 else (f,1/f))
            events.append((days[i],pm,vm))
    return events

def apply_splits(bars,events):
    out=[]
    for z in bars:
        d=day_key(z);pm=vm=1.0
        for sd,p,v in events:
            if d<sd: pm*=p;vm*=v
        q=z.copy()
        for k in ("o","h","l","c"):q[k]*=pm
        q["v"]*=vm;out.append(q)
    return out

def aggregate_15m(bars):
    groups=defaultdict(list)
    for z in bars:
        dt=datetime.fromtimestamp(z["t"]/1000,UTC).astimezone(NY)
        minute=(dt.minute//15)*15
        key=(dt.date(),dt.hour,minute)
        groups[key].append(z)
    out=[]
    for _,g in sorted(groups.items()):
        g.sort(key=lambda x:x["t"])
        out.append({"t":g[0]["t"],"o":g[0]["o"],"h":max(x["h"] for x in g),"l":min(x["l"] for x in g),
                    "c":g[-1]["c"],"v":sum(x["v"] for x in g),"ct":g[-1]["ct"]})
    return out

def aggregate_4h(bars15):
    groups=defaultdict(list)
    for z in bars15:
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

def aggregate_daily(bars15):
    groups=defaultdict(list)
    for z in bars15: groups[day_key(z)].append(z)
    out=[]
    for _,g in sorted(groups.items()):
        g.sort(key=lambda x:x["t"])
        out.append({"t":g[0]["t"],"o":g[0]["o"],"h":max(x["h"] for x in g),"l":min(x["l"] for x in g),
                    "c":g[-1]["c"],"v":sum(x["v"] for x in g),"ct":g[-1]["ct"]})
    return out

def stats(ts):
    n=len(ts); wins=sum(t["pnl"]>0 for t in ts); losses=sum(t["pnl"]<0 for t in ts)
    net=sum(t["r"] for t in ts); gp=sum(t["r"] for t in ts if t["r"]>0);gl=sum(t["r"] for t in ts if t["r"]<0)
    return {"closed":n,"wins":wins,"losses":losses,"win_rate":wins/n if n else None,
            "net_r":net,"avg_r":net/n if n else None,"profit_factor":gp/abs(gl) if gl<0 else None}

def run_one(sym,D,H,M,res):
    old_dataset,old_filters=bt.dataset,bt.symbol_filters
    try:
        bt._CACHE.clear()
        bt.dataset=lambda _s,D=D,H=H,M=M:(D,H,M)
        bt.symbol_filters=lambda _s:(0.01,0.0,0.0)
        r=bt.simulate(sym,a_params=A_OFF,b_params=None,
            start_ms=int(EVAL_START.timestamp()*1000),end_ms=int(DATA_END.timestamp()*1000)-1,
            fee_bps=FEE_BPS,slippage_bps=SLIPPAGE_BPS,
            a_mode="snapshot",b_runner_mode="pivot",b_scale_mode="30_30_40")
        lo=int(EVAL_START.timestamp()*1000);hi=int(EVAL_END.timestamp()*1000)
        return [t for t in r["trades"] if t["track"]=="B" and t["reason"]!="OPEN_MARK" and lo<=t["entry_t"]<hi]
    finally:
        bt.dataset,bt.symbol_filters=old_dataset,old_filters

def main():
    bt.CAP=20000.0;bt.RISK=400.0
    con,months=build_local_db()
    all1=[];all15=[];per=[];errors={}
    try:
        for sym in SYMS:
            try:
                m1=load_symbol(con,sym)
                if not m1: raise RuntimeError("no bars")
                m1=apply_splits(m1,detect_splits(m1))
                m15=aggregate_15m(m1)
                H=w.enrich(aggregate_4h(m15));D=w.enrich(aggregate_daily(m15))
                if len(D)<60 or len(H)<60: raise RuntimeError(f"insufficient warmup D={len(D)} H={len(H)}")
                t1=run_one(sym,D,H,m1,"1m");t15=run_one(sym,D,H,m15,"15m")
                all1.extend([{"symbol":sym,**t} for t in t1]);all15.extend([{"symbol":sym,**t} for t in t15])
                per.append({"symbol":sym,"1m":stats(t1),"15m":stats(t15),"delta_net_r":stats(t1)["net_r"]-stats(t15)["net_r"]})
                print("RESULT",sym,"1m",stats(t1),"15m",stats(t15),flush=True)
            except Exception as e:
                errors[sym]=repr(e);print("SYMBOL_ERROR",sym,repr(e),flush=True)
    finally:
        con.close()
    all1.sort(key=lambda t:(t["entry_t"],t["symbol"]));all15.sort(key=lambda t:(t["entry_t"],t["symbol"]))
    bykey1={(t["symbol"],t["direction"],t["trigger_4h_open_ms"],round(float(t["entry"]),6)):t for t in all1}
    bykey15={(t["symbol"],t["direction"],t["trigger_4h_open_ms"],round(float(t["entry"]),6)):t for t in all15}
    common=set(bykey1)&set(bykey15)
    changed=sum(abs(bykey1[k]["r"]-bykey15[k]["r"])>1e-9 for k in common)
    report={
      "generated_at":datetime.now(UTC).isoformat(),
      "eval_start":EVAL_START.isoformat(),"eval_end_exclusive":EVAL_END.isoformat(),
      "purpose":"isolate execution-resolution effect: identical RTH Track B signals, 1m vs 15m exact-touch management",
      "months_loaded":months,"costs":{"fee_bps_per_fill":FEE_BPS,"slippage_bps_per_fill":SLIPPAGE_BPS},
      "one_minute":stats(all1),"fifteen_minute":stats(all15),
      "delta":{"closed":len(all1)-len(all15),"net_r":stats(all1)["net_r"]-stats(all15)["net_r"],
               "avg_r":(stats(all1)["avg_r"] or 0)-(stats(all15)["avg_r"] or 0),
               "common_trades":len(common),"changed_trade_r":changed},
      "per_symbol":per,"errors":errors,"trades_1m":all1,"trades_15m":all15
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("FINAL",json.dumps({k:report[k] for k in ("one_minute","fifteen_minute","delta","errors")},ensure_ascii=False),flush=True)

if __name__=="__main__": main()
