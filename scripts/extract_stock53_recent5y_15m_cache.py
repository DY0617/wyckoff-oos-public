import json,time
from datetime import datetime,timezone,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import duckdb

UTC=timezone.utc; NY=ZoneInfo("America/New_York")
START=datetime(2020,10,1,tzinfo=UTC)
END=datetime(2026,4,1,tzinfo=UTC)
HF_BASE="https://huggingface.co/datasets/mito0o852/OHLCV-1m/resolve/main/data"
OUT=Path("data/cache/stock53_recent5y_15m.parquet")
META=Path("data/cache/stock53_recent5y_15m_meta.json")

SYMS=(
"AAPL","AMZN","AVGO","CRCL","DELL","MSFT","MU","SNDK","SNXX","SOXL","SPCX",
"AMD","BABA","INTC","JPM","KORU","MSTR","NFLX","SKHY","SMCI","SOXS","V",
"COST","GOOGL","LLY","META","NBIS","NVDA","QQQ","TSLA","UBER","WMT",
"AMAT","CAT","DRAM","EWY","HD","MRVL","MUU","ORCL","SPY","TSM",
"AAOI","AXTI","BE","COIN","CRM","CSCO","DIS","HOOD","IBM","LITE","TQQQ"
)
SOURCE=tuple(sorted(set(SYMS+("FB","GOOG"))))

def month_iter(a,b):
    y,m=a.year,a.month
    while (y,m)<(b.year,b.month):
        yield y,m
        m+=1
        if m==13:y,m=y+1,1

def month_query(y,m):
    url=f"{HF_BASE}/ohlcv_{y:04d}-{m:02d}.parquet"
    ph=",".join(["?"]*len(SOURCE))
    return f"""
    WITH src AS (
      SELECT ticker,timezone('America/New_York',timestamp) et,
             open,high,low,"close",volume
      FROM read_parquet('{url}')
      WHERE ticker IN ({ph})
    ),rth AS (
      SELECT * FROM src
      WHERE cast(et as time)>=time '09:30:00'
        AND cast(et as time)<time '16:00:00'
    ),agg AS (
      SELECT
        CASE
          WHEN ticker='FB' AND cast(et as date)<date '2022-06-09' THEN 'META'
          WHEN ticker='META' AND cast(et as date)>=date '2022-06-09' THEN 'META'
          WHEN ticker='GOOG' AND cast(et as date)<date '2014-04-03' THEN 'GOOGL'
          WHEN ticker='GOOGL' AND cast(et as date)>=date '2014-04-03' THEN 'GOOGL'
          ELSE ticker
        END symbol,
        time_bucket(interval '15 minutes',et) b,
        arg_min(open,et) o,max(high) h,min(low) l,arg_max("close",et) c,sum(volume) v
      FROM rth
      GROUP BY symbol,b
    )
    SELECT symbol,b,o,h,l,c,v
    FROM agg
    WHERE symbol IN ({ph})
    ORDER BY symbol,b
    """

def main():
    OUT.parent.mkdir(parents=True,exist_ok=True)
    tmp=OUT.parent/"stock53_recent5y_parts"
    tmp.mkdir(parents=True,exist_ok=True)
    con=duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    parts=[];errors=[]
    for y,m in month_iter(START,END):
        p=tmp/f"{y:04d}-{m:02d}.parquet"
        q=month_query(y,m)
        params=list(SOURCE)+list(SYMS)
        ok=False
        for attempt in range(10):
            try:
                t0=time.time()
                con.execute(f"COPY ({q}) TO '{p}' (FORMAT PARQUET, COMPRESSION ZSTD)",params)
                n=con.execute(f"SELECT count(*) FROM read_parquet('{p}')").fetchone()[0]
                print("MONTH_OK",f"{y:04d}-{m:02d}",n,round(time.time()-t0,2),flush=True)
                parts.append(str(p));ok=True;break
            except Exception as e:
                delay=min(60,5*(attempt+1))
                print("MONTH_RETRY",f"{y:04d}-{m:02d}",attempt+1,repr(e),"sleep",delay,flush=True)
                time.sleep(delay)
        if not ok:errors.append(f"{y:04d}-{m:02d}")
    if errors:
        raise RuntimeError("failed months="+",".join(errors))
    glob=str(tmp/"*.parquet")
    con.execute(f"COPY (SELECT * FROM read_parquet('{glob}') ORDER BY symbol,b) TO '{OUT}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    counts=dict(con.execute(f"SELECT symbol,count(*) FROM read_parquet('{OUT}') GROUP BY symbol ORDER BY symbol").fetchall())
    total=con.execute(f"SELECT count(*) FROM read_parquet('{OUT}')").fetchone()[0]
    first,last=con.execute(f"SELECT min(b),max(b) FROM read_parquet('{OUT}')").fetchone()
    con.close()
    meta={"generated_at":datetime.now(UTC).isoformat(),"rows":total,"first":str(first),"last":str(last),
          "symbols":counts,"months":len(parts)}
    META.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
    print("FINAL",json.dumps(meta,ensure_ascii=False),flush=True)

if __name__=="__main__":main()
