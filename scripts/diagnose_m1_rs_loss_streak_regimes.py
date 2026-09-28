import json, os, time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import duckdb

UTC=timezone.utc; NY=ZoneInfo("America/New_York")
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
WINDOW=os.environ["WINDOW"]
OUT=Path(os.environ["OUT"])

EPISODES={
"w1":{"start":"2006-01-01","end":"2009-10-01","signals":[
("2007-01-03","CSCO",3),("2007-01-09","AAPL",3),("2007-01-11","DIS",3),("2007-02-13","JPM",3),("2007-01-24","MSTR",3),("2007-03-22","AXTI",3),("2007-03-21","AAPL",3),
("2007-12-06","COST",2),("2007-12-13","MSFT",2),("2007-12-21","AAPL",2),("2008-05-01","TSM",2),("2008-06-05","AAPL",2),("2009-06-01","AAPL",2),("2009-07-16","MSFT",2),("2009-08-18","AMAT",2)]},
"w2":{"start":"2011-03-01","end":"2012-08-01","signals":[
("2012-03-08","AMD",4),("2012-04-12","AMD",4),("2012-04-12","CRM",4),("2012-04-25","V",4),("2012-04-26","CRM",4),("2012-06-29","AMZN",4),("2012-06-29","LLY",4)]},
"w3":{"start":"2013-03-01","end":"2014-07-01","signals":[
("2014-03-20","AMAT",6),("2014-04-08","SOXL",6),("2014-04-08","NVDA",6),("2014-04-28","TSM",6),("2014-04-21","NVDA",6),("2014-04-30","AMD",6)]},
"w4":{"start":"2015-01-01","end":"2016-09-01","signals":[
("2015-12-15","INTC",1),("2015-12-16","MSFT",1),("2016-04-13","SMCI",1),("2016-04-20","TSLA",1),("2016-04-26","CAT",1),("2016-06-16","AMZN",1),("2016-06-21","AMAT",1),("2016-06-20","AXTI",1),("2016-06-30","WMT",1)]},
"w5":{"start":"2022-01-01","end":"2024-11-01","signals":[
("2023-01-23","CAT",5),("2023-02-01","AMAT",5),("2023-01-24","AVGO",5),("2023-03-03","UBER",5),("2023-04-03","SMCI",5),("2023-04-10","AMD",5),("2023-03-03","AVGO",5),
("2023-07-10","SOXL",7),("2023-08-23","NVDA",7),("2023-09-14","CAT",7),("2023-08-31","UBER",7),("2023-10-11","DELL",7),("2023-10-11","LLY",7),
("2024-06-25","MU",8),("2024-06-25","GOOGL",8),("2024-06-25","NVDA",8),("2024-07-16","HOOD",8),("2024-08-15","AAPL",8),("2024-09-13","TSLA",8)]}
}

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

def collect(start,end):
    con=duckdb.connect();con.execute("INSTALL httpfs; LOAD httpfs;")
    by={s:[] for s in SYMS};ph=",".join(["?"]*len(SOURCE))
    missing=[]
    for y,m in month_iter(start,end):
        url=f"{HF_BASE}/ohlcv_{y:04d}-{m:02d}.parquet"
        q=f"""
        WITH src AS (
          SELECT ticker,timezone('America/New_York',timestamp) et,open,high,low,"close",volume
          FROM read_parquet('{url}') WHERE ticker IN ({ph})
        ),rth AS (
          SELECT * FROM src WHERE cast(et as time)>=time '09:30:00' and cast(et as time)<time '16:00:00'
        )
        SELECT ticker,cast(et as date) d,arg_min(open,et) o,max(high) h,min(low) l,arg_max("close",et) c,sum(volume) v
        FROM rth GROUP BY ticker,cast(et as date) ORDER BY ticker,d
        """
        rows=None
        for a in range(7):
            try:
                t=time.time();rows=con.execute(q,list(SOURCE)).fetchall()
                print("MONTH",f"{y:04d}-{m:02d}",len(rows),round(time.time()-t,2),flush=True);break
            except Exception as e:
                print("RETRY",y,m,a+1,repr(e),flush=True);time.sleep(min(40,5*(a+1)))
        if rows is None:missing.append(f"{y:04d}-{m:02d}");continue
        for ticker,d,o,h,l,c,v in rows:
            s=canonical(str(ticker),d)
            if not s:continue
            nb=NOT_BEFORE.get(s)
            if nb and datetime(d.year,d.month,d.day,tzinfo=UTC)<nb:continue
            by[s].append({"date":str(d),"o":float(o),"h":float(h),"l":float(l),"c":float(c),"v":float(v or 0)})
    con.close()
    if missing:raise RuntimeError("missing="+",".join(missing))
    return by

def enrich(by):
    out={}
    for s,D in by.items():
        if not D:continue
        cs=[x["c"] for x in D]
        e20=ema(cs,20);e50=ema(cs,50);e200=ema(cs,200)
        for i,x in enumerate(D):
            x["ema20"]=e20[i];x["ema50"]=e50[i];x["ema200"]=e200[i]
            for n in (5,10,20,60):
                x[f"ret{n}"]=x["c"]/D[i-n]["c"]-1 if i>=n and D[i-n]["c"]>0 else None
        out[s]=D
    return out

def main():
    cfg=EPISODES[WINDOW]
    start=datetime.fromisoformat(cfg["start"]).date()
    end=datetime.fromisoformat(cfg["end"]).date()
    by=enrich(collect(start,end))
    idx={s:{x["date"]:i for i,x in enumerate(D)} for s,D in by.items()}
    dates=sorted(set(ds for m in idx.values() for ds in m))
    breadth={}
    for ds in dates:
        a=e=0
        for s,D in by.items():
            i=idx[s].get(ds)
            if i is None or i<50:continue
            e+=1;a+=int(D[i]["c"]>D[i]["ema50"])
        breadth[ds]=a/e if e else None

    rows=[]
    spy=by["SPY"];sidx=idx["SPY"]
    for ds,sym,ep in cfg["signals"]:
        si=sidx.get(ds)
        if si is None:continue
        x=spy[si]
        def bshift(n):
            if si<n:return None
            d0=spy[si-n]["date"]
            return breadth.get(d0)
        b=breadth.get(ds)
        b5=bshift(5);b20=bshift(20)
        rows.append({
          "episode":ep,"signal_date":ds,"symbol":sym,
          "spy_close":x["c"],
          "spy_above_ema20":x["c"]>x["ema20"],
          "spy_above_ema50":x["c"]>x["ema50"],
          "spy_above_ema200":x["c"]>x["ema200"],
          "spy_ema20_above_ema50":x["ema20"]>x["ema50"],
          "spy_ret5":x["ret5"],"spy_ret10":x["ret10"],"spy_ret20":x["ret20"],"spy_ret60":x["ret60"],
          "breadth":b,
          "breadth_chg5":(b-b5) if b is not None and b5 is not None else None,
          "breadth_chg20":(b-b20) if b is not None and b20 is not None else None,
          "breadth_5d_ago":b5,"breadth_20d_ago":b20
        })
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps({"window":WINDOW,"rows":rows},ensure_ascii=False,indent=2))
    print(json.dumps(rows,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
