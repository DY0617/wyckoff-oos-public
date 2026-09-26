import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

CURRENT50=("SPY","QQQ","IWM","AAPL","MSFT","NVDA","AMZN","META","GOOGL","TSLA",
           "AVGO","AMD","NFLX","ORCL","JPM","BAC","GS","V","MA","XOM","CVX","JNJ",
           "UNH","LLY","MRK","WMT","COST","HD","CAT","KO",
           "MSTR","COIN","HOOD","PLTR","BABA","TSM","MU","INTC","IBM","CRM","NOW","NET",
           "SHOP","DIS","UBER","CSCO","ANET","DDOG","AMAT","VST")
ALIASES=("QQQQ","FB","GOOG")
SOURCE_TICKERS=tuple(sorted(set(CURRENT50+ALIASES)))
HF_BASE="https://huggingface.co/datasets/mito0o852/OHLCV-1m/resolve/main/data"

def ym(s):
    return datetime.strptime(s,"%Y-%m")

def month_iter(start,end):
    y,m=start.year,start.month
    while (y,m)<(end.year,end.month):
        yield y,m
        m+=1
        if m==13:
            y,m=y+1,1

def remote_15m(con,y,m):
    url=f"{HF_BASE}/ohlcv_{y:04d}-{m:02d}.parquet"
    tickers=",".join("'" + s.replace("'","''") + "'" for s in SOURCE_TICKERS)
    q=f"""
    WITH src AS (
      SELECT
        ticker,
        timezone('America/New_York', timestamp) AS et,
        open, high, low, close, volume
      FROM read_parquet('{url}')
      WHERE ticker IN ({tickers})
    ),
    rth AS (
      SELECT *
      FROM src
      WHERE CAST(et AS TIME) >= TIME '09:30:00'
        AND CAST(et AS TIME) <  TIME '16:00:00'
    ),
    agg AS (
      SELECT
        ticker,
        time_bucket(INTERVAL '15 minutes', et) AS et_bucket,
        arg_min(open, et) AS open,
        max(high) AS high,
        min(low) AS low,
        arg_max(close, et) AS close,
        sum(volume) AS volume
      FROM rth
      GROUP BY ticker, et_bucket
    )
    SELECT ticker, et_bucket, open, high, low, close, volume
    FROM agg
    ORDER BY ticker, et_bucket
    """
    last=None
    for attempt in range(1,4):
        try:
            t0=time.time()
            rows=con.execute(q).fetchall()
            print(f"MONTH {y:04d}-{m:02d} rows15={len(rows)} sec={time.time()-t0:.1f}",flush=True)
            return rows
        except Exception as e:
            last=e
            print(f"MONTH_RETRY {y:04d}-{m:02d} attempt={attempt} error={e!r}",flush=True)
            time.sleep(3*attempt)
    raise RuntimeError(f"failed month {y:04d}-{m:02d}: {last!r}")

def normalize_ticker(ticker,et):
    d=pd.Timestamp(et).date()
    if ticker=="QQQQ":
        return "QQQ"
    if ticker=="FB":
        return "META"
    # Before Google's 2014 share-class change, GOOG is used as the history source
    # for the current GOOGL company proxy. After that both classes trade, so keep GOOGL only.
    if ticker=="GOOG" and d < datetime(2014,4,3).date():
        return "GOOGL"
    return ticker

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--start",required=True)
    ap.add_argument("--end",required=True)
    ap.add_argument("--tag",required=True)
    ap.add_argument("--out-dir",default="data/chunks_us50")
    args=ap.parse_args()

    start,end=ym(args.start),ym(args.end)
    out_dir=Path(args.out_dir); out_dir.mkdir(parents=True,exist_ok=True)

    con=duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    all_rows=[]; months=[]
    try:
        for y,m in month_iter(start,end):
            rows=remote_15m(con,y,m)
            months.append(f"{y:04d}-{m:02d}")
            for ticker,et,o,h,l,c,v in rows:
                ticker=normalize_ticker(str(ticker),et)
                ts=pd.Timestamp(et)
                if ts.tzinfo is None:
                    ts=ts.tz_localize("America/New_York")
                else:
                    ts=ts.tz_convert("America/New_York")
                utc=ts.tz_convert("UTC")
                all_rows.append({
                    "ticker":ticker,"t":int(utc.timestamp()*1000),
                    "o":float(o),"h":float(h),"l":float(l),"c":float(c),"v":float(v or 0.0)
                })
    finally:
        con.close()

    df=pd.DataFrame(all_rows)
    if df.empty:
        raise RuntimeError("no rows extracted")
    # Alias overlaps (e.g. GOOG/GOOGL around transitions) are resolved deterministically.
    df=df.sort_values(["ticker","t"]).drop_duplicates(["ticker","t"],keep="last").reset_index(drop=True)
    counts={str(k):int(v) for k,v in df.groupby("ticker").size().to_dict().items()}
    p=out_dir/f"us50_15m_{args.tag}.parquet"
    df.to_parquet(p,index=False,compression="zstd")
    manifest={
      "tag":args.tag,"start":args.start,"end_exclusive":args.end,
      "months":months,"rows":len(df),"by_symbol":counts,"file":str(p),
      "source_tickers":list(SOURCE_TICKERS)
    }
    (out_dir/f"us50_15m_{args.tag}.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print("CHUNK_SUMMARY",json.dumps(manifest),flush=True)

if __name__=="__main__":
    main()
