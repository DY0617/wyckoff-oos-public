import json,time
from datetime import datetime,timezone
from pathlib import Path
import duckdb

UTC=timezone.utc
START=datetime(2020,10,1,tzinfo=UTC)
END=datetime(2026,4,1,tzinfo=UTC)
HF_BASE="https://huggingface.co/datasets/mito0o852/OHLCV-1m/resolve/main/data"
OUT=Path("data/cache/stock_oos20_recent5y_15m.parquet")
META=Path("data/cache/stock_oos20_recent5y_15m_meta.json")
SYMS=("XOM","BAC","MA","PG","KO","PEP","JNJ","ABBV","MRK","GE","CVX","UNH","QCOM","TXN","AMGN","SBUX","LOW","BKNG","GS","C","SPY")

def month_iter(a,b):
    y,m=a.year,a.month
    while (y,m)<(b.year,b.month):
        yield y,m
        m+=1
        if m==13:y,m=y+1,1

def query(y,m):
    url=f"{HF_BASE}/ohlcv_{y:04d}-{m:02d}.parquet"
    ph=",".join(["?"]*len(SYMS))
    return f"""
    WITH src AS (
      SELECT ticker,timezone('America/New_York',timestamp) et,open,high,low,"close",volume
      FROM read_parquet('{url}')
      WHERE ticker IN ({ph})
    ),rth AS (
      SELECT * FROM src
      WHERE cast(et as time)>=time '09:30:00' AND cast(et as time)<time '16:00:00'
    ),agg AS (
      SELECT ticker symbol,time_bucket(interval '15 minutes',et) b,
             arg_min(open,et) o,max(high) h,min(low) l,arg_max("close",et) c,sum(volume) v
      FROM rth GROUP BY ticker,b
    )
    SELECT symbol,b,o,h,l,c,v FROM agg ORDER BY symbol,b
    """

def main():
    OUT.parent.mkdir(parents=True,exist_ok=True)
    tmp=OUT.parent/"stock_oos20_parts";tmp.mkdir(parents=True,exist_ok=True)
    con=duckdb.connect();con.execute("INSTALL httpfs; LOAD httpfs;")
    parts=[];errors=[]
    for y,m in month_iter(START,END):
        p=tmp/f"{y:04d}-{m:02d}.parquet"
        ok=False
        for a in range(8):
            try:
                con.execute(f"COPY ({query(y,m)}) TO '{p}' (FORMAT PARQUET, COMPRESSION ZSTD)",list(SYMS))
                parts.append(str(p));ok=True;print("OK",y,m,flush=True);break
            except Exception as e:
                print("RETRY",y,m,a+1,repr(e),flush=True);time.sleep(min(30,3*(a+1)))
        if not ok:errors.append(f"{y:04d}-{m:02d}")
    if errors:raise RuntimeError(",".join(errors))
    glob=str(tmp/"*.parquet")
    con.execute(f"COPY (SELECT * FROM read_parquet('{glob}') ORDER BY symbol,b) TO '{OUT}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    counts=dict(con.execute(f"SELECT symbol,count(*) FROM read_parquet('{OUT}') GROUP BY symbol ORDER BY symbol").fetchall())
    first,last=con.execute(f"SELECT min(b),max(b) FROM read_parquet('{OUT}')").fetchone()
    con.close()
    META.write_text(json.dumps({"first":str(first),"last":str(last),"symbols":counts},indent=2),encoding="utf-8")
    print("FINAL",json.dumps(counts),flush=True)

if __name__=="__main__":main()
