import json,duckdb,time
from pathlib import Path
URL="https://huggingface.co/datasets/mito0o852/OHLCV-1m/resolve/main/data/ohlcv_2024-01.parquet"
SYMS=("AAPL","MSFT","META","FB","GOOG","GOOGL")
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
    )
    SELECT ticker,count(*) n,min(et) first_et,max(et) last_et
    FROM rth GROUP BY ticker ORDER BY ticker
    """
    t=time.time(); rows=con.execute(q,list(SYMS)).fetchall()
    out={"ok":True,"sec":time.time()-t,"rows":[[str(x) for x in r] for r in rows]}
except Exception as e:
    out={"ok":False,"error":repr(e)}
Path("data/validation/hf_duckdb_probe.json").parent.mkdir(parents=True,exist_ok=True)
Path("data/validation/hf_duckdb_probe.json").write_text(json.dumps(out,indent=2))
print(json.dumps(out))
