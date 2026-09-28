import json,duckdb
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HF="https://huggingface.co/datasets/mito0o852/OHLCV-1m/resolve/main/data"
NY=ZoneInfo("America/New_York")
CASES=[("NFLX",2015,7),("TQQQ",2014,1),("TQQQ",2021,1),("NVDA",2024,6),("DELL",2021,11)]
out={}
con=duckdb.connect();con.execute("INSTALL httpfs; LOAD httpfs;")
for sym,y,m in CASES:
    url=f"{HF}/ohlcv_{y:04d}-{m:02d}.parquet"
    q=f"""
    WITH src AS (
      SELECT timezone('America/New_York',timestamp) et,open,high,low,"close",volume
      FROM read_parquet('{url}') WHERE ticker=?
    ), rth AS (
      SELECT * FROM src WHERE cast(et as time)>=time '09:30:00' and cast(et as time)<time '16:00:00'
    )
    SELECT cast(et as date) d,arg_min(open,et) o,arg_max("close",et) c,min(low) l,max(high) h
    FROM rth GROUP BY cast(et as date) ORDER BY d
    """
    rows=con.execute(q,[sym]).fetchall()
    gaps=[]
    for i in range(1,len(rows)):
        d0,o0,c0,l0,h0=rows[i-1];d1,o1,c1,l1,h1=rows[i]
        if c0 and o1:
            ratio=float(c0)/float(o1);mag=ratio if ratio>=1 else 1/ratio
            if mag>=1.25:
                gaps.append({"prev_date":str(d0),"date":str(d1),"prev_close":float(c0),"open":float(o1),"ratio":ratio,"mag":mag})
    out[f"{sym}_{y}_{m:02d}"]={"days":[{"date":str(r[0]),"open":float(r[1]),"close":float(r[2])} for r in rows],"gaps":gaps}
con.close()
Path("data/validation/corporate_action_gap_probe.json").write_text(json.dumps(out,indent=2))
print(json.dumps({k:v["gaps"] for k,v in out.items()},indent=2))
