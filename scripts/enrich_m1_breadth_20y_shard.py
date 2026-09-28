import json, math, os, time
from datetime import datetime,timezone,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import duckdb

M1=Path("data/validation/m1_momentum_pullback_20y.json")
UTC=timezone.utc;NY=ZoneInfo("America/New_York")
HF_BASE="https://huggingface.co/datasets/mito0o852/OHLCV-1m/resolve/main/data"
SYMS=(
"AAPL","AMZN","AVGO","CRCL","DELL","MSFT","MU","SNDK","SNXX","SOXL","SPCX",
"AMD","BABA","INTC","JPM","KORU","MSTR","NFLX","SKHY","SMCI","SOXS","V",
"COST","GOOGL","LLY","META","NBIS","NVDA","QQQ","TSLA","UBER","WMT",
"AMAT","CAT","DRAM","EWY","HD","MRVL","MUU","ORCL","SPY","TSM",
"AAOI","AXTI","BE","COIN","CRM","CSCO","DIS","HOOD","IBM","LITE","TQQQ"
)
SOURCE=tuple(sorted(set(SYMS+("FB","GOOG"))))
NOT_BEFORE={"DELL":datetime(2018,12,28,tzinfo=UTC),"SNDK":datetime(2025,2,24,tzinfo=UTC)}
def pd(s):return datetime.strptime(s,"%Y-%m-%d").replace(tzinfo=UTC)
START=pd(os.environ["EVAL_START"]);END=pd(os.environ["EVAL_END"]);WARMUP=START-timedelta(days=390)
OUT=Path(os.environ["OUT"])

def month_iter(start,end):
    y,m=start.year,start.month
    while (y,m)<=(end.year,end.month):
        yield y,m
        m+=1
        if m==13:y,m=y+1,1

def canonical(ticker,d):
    if ticker=="FB":return "META" if d<datetime(2022,6,9).date() else None
    if ticker=="META":return "META" if d>=datetime(2022,6,9).date() else None
    if ticker=="GOOG":return "GOOGL" if d<datetime(2014,4,3).date() else None
    if ticker=="GOOGL":return "GOOGL" if d>=datetime(2014,4,3).date() else None
    return ticker if ticker in SYMS else None

def ema(vals,n):
    k=2/(n+1);out=[];e=None
    for x in vals:
        e=x if e is None else e+k*(x-e);out.append(e)
    return out

def detect_splits(bars):
    common=(2,3,4,5,7,10,15,20);ev=[]
    for i in range(1,len(bars)):
        prev=bars[i-1]["c"];op=bars[i]["o"]
        d0=datetime.fromtimestamp(bars[i-1]["t"]/1000,UTC).date()
        d1=datetime.fromtimestamp(bars[i]["t"]/1000,UTC).date()
        if prev<=0 or op<=0 or (d1-d0).days>14:continue
        ratio=prev/op;mag=ratio if ratio>=1 else 1/ratio
        if mag<1.7:continue
        f=min(common,key=lambda q:abs(mag/q))
        if abs(mag/f)<=.08:
            pm,vm=((1/f,f) if ratio>1 else (f,1/f));ev.append((bars[i]["t"],pm,vm))
    return ev

def apply_splits(bars,ev):
    out=[]
    for z in bars:
        pm=vm=1.0
        for ts,p,v in ev:
            if z["t"]<ts:pm*=p;vm*=v
        q=z.copy()
        for k in ("o","h","l","c"):q[k]*=pm
        q["v"]*=vm;out.append(q)
    return out

def collect_daily():
    con=duckdb.connect();con.execute("INSTALL httpfs; LOAD httpfs;")
    by={s:[] for s in SYMS};missing=[];ph=",".join(["?"]*len(SOURCE))
    for y,m in month_iter(WARMUP,END-timedelta(days=1)):
        url=f"{HF_BASE}/ohlcv_{y:04d}-{m:02d}.parquet"
        q=f"""
        WITH src AS (
          SELECT ticker,timezone('America/New_York',timestamp) et,open,high,low,"close",volume
          FROM read_parquet('{url}') WHERE ticker IN ({ph})
        ),rth AS (
          SELECT * FROM src WHERE cast(et as time)>=time '09:30:00' and cast(et as time)<time '16:00:00'
        )
        SELECT ticker,cast(et as date) d,min(et) first_et,max(et) last_et,
               arg_min(open,et) o,max(high) h,min(low) l,arg_max("close",et) c,sum(volume) v
        FROM rth GROUP BY ticker,cast(et as date) ORDER BY ticker,d
        """
        rows=None
        for a in range(5):
            try:
                t0=time.time();rows=con.execute(q,list(SOURCE)).fetchall()
                print("MONTH",f"{y:04d}-{m:02d}",len(rows),round(time.time()-t0,2),flush=True);break
            except Exception as e:
                print("RETRY",y,m,a+1,repr(e),flush=True);time.sleep(3*(a+1))
        if rows is None:missing.append(f"{y:04d}-{m:02d}");continue
        for ticker,d,first_et,last_et,o,h,l,c,v in rows:
            s=canonical(str(ticker),d)
            if not s:continue
            f=first_et.replace(tzinfo=NY) if first_et.tzinfo is None else first_et.astimezone(NY)
            z=last_et.replace(tzinfo=NY) if last_et.tzinfo is None else last_et.astimezone(NY)
            utc=f.astimezone(UTC)
            nb=NOT_BEFORE.get(s)
            if nb and utc<nb:continue
            if utc<WARMUP or utc>=END:continue
            tms=int(utc.timestamp()*1000);ct=int(z.astimezone(UTC).timestamp()*1000)+60_000-1
            by[s].append({"t":tms,"o":float(o),"h":float(h),"l":float(l),"c":float(c),"v":float(v or 0),"ct":ct,"date":str(d)})
    con.close()
    if missing:raise RuntimeError("missing="+",".join(missing))
    out={}
    for s,b in by.items():
        if not b:continue
        b=apply_splits(b,detect_splits(b));e50=ema([x["c"] for x in b],50)
        for i,x in enumerate(b):x["ema50"]=e50[i]
        out[s]=b
    return out

def breadth_map(dailies):
    idx={s:{x["date"]:i for i,x in enumerate(D)} for s,D in dailies.items()}
    dates=sorted(set(ds for m in idx.values() for ds in m))
    out={}
    for ds in dates:
        a=e=0
        for s,D in dailies.items():
            i=idx[s].get(ds)
            if i is None or i<50:continue
            e+=1;a+=int(D[i]["c"]>D[i]["ema50"])
        out[ds]=(a/e if e else None,a,e)
    return out

def et_date(ms):return datetime.fromtimestamp(ms/1000,UTC).astimezone(NY).date().isoformat()

def main():
    m=json.loads(M1.read_text())
    lo=int(START.timestamp()*1000);hi=int(END.timestamp()*1000)
    trades=[t for t in m["trades"] if lo<=t["signal_t"]<hi]
    ds=collect_daily();bm=breadth_map(ds)
    out=[]
    for t in trades:
        q=t.copy();d=et_date(t["signal_t"]);b,a,e=bm.get(d,(None,0,0))
        q["breadth"]=b;q["breadth_above"]=a;q["breadth_eligible"]=e
        out.append(q)
    report={"eval_start":START.isoformat(),"eval_end_exclusive":END.isoformat(),"trades":out}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print("FINAL",len(out),sum(x["r"] for x in out),flush=True)
if __name__=="__main__":main()
