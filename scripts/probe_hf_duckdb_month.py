import json,duckdb,time
from pathlib import Path
URL="https://huggingface.co/datasets/mito0o852/OHLCV-1m/resolve/main/data/ohlcv_2006-09.parquet"
SYMS=("AAPL","AMZN","AVGO","MSFT","MU","AMD","INTC","JPM","MSTR","NFLX","V","COST","GOOG","NVDA","QQQ","WMT","AMAT","CAT","EWY","HD","ORCL","SPY","TSM","CRM","CSCO","DIS","IBM")
out={}
try:
    con=duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    ph=",".join(["?"]*len(SYMS))
    q=f"""
    WITH src AS (
      SELECT ticker, timezone('America/New_York', timestamp) AS et,
             open,high,low,close,volume
      FROM read_parquet('{URL}')
      WHERE ticker IN ({ph})
    ), rth AS (
      SELECT * FROM src
      WHERE CAST(et AS TIME) >= TIME '09:30:00'
        AND CAST(et AS TIME) < TIME '16:00:00'
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
    t=time.time(); rows=con.execute(q,list(SYMS)).fetchall()
    out={"ok":True,"sec":time.time()-t,"row_count":len(rows),"sample":[[str(x) for x in r] for r in rows[:5]]}
except Exception as e:
    out={"ok":False,"error":repr(e)}
Path("data/validation/hf_duckdb_probe.json").parent.mkdir(parents=True,exist_ok=True)
Path("data/validation/hf_duckdb_probe.json").write_text(json.dumps(out,indent=2))
print(json.dumps(out))
