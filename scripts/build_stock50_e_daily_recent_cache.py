import json, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).parent))
import backtest_stock_track_b_e_cash_to_binance_futures_exec_v1 as x

OUT=Path("data/validation/stock50_e_daily_recent_cache.json")

def main():
    syms=x.STOCK50
    hf=x.remote_hf_15m(syms)
    gd={}
    with ThreadPoolExecutor(max_workers=12) as ex:
        fs={ex.submit(x.fetch_getdata,s):s for s in syms}
        for fut in as_completed(fs):
            s=fs[fut]
            try:gd[s]=fut.result()
            except Exception as e:
                gd[s]=[];print("GETDATA_CACHE_ERROR",s,repr(e),flush=True)
            print("GETDATA_CACHE",s,len(gd[s]),flush=True)
    out={};meta={}
    for s in syms:
        M=x.merge_cash(hf.get(s,[]),gd.get(s,[]))
        if len(M)<500:
            print("CACHE_SKIP",s,len(M),flush=True);continue
        M=x.cashhist.apply_splits(M,x.cashhist.detect_splits(M))
        daily=x.src.aggregate_daily(x.src.rth_only(M))
        rows=[]
        for z in daily:
            d=datetime.fromtimestamp(z["t"]/1000,x.UTC).astimezone(x.NY).date()
            rows.append({"date":d,"c":float(z["c"])})
        rows=x.enrich_daily(rows)
        if len(rows)<55:
            print("CACHE_SHORT",s,len(rows),flush=True);continue
        out[s]=[{**z,"date":z["date"].isoformat()} for z in rows]
        meta[s]={"rows":len(rows),"first":rows[0]["date"].isoformat(),"last":rows[-1]["date"].isoformat(),
                 "hf_15m":len(hf.get(s,[])),"recent_15m":len(gd.get(s,[]))}
        print("CACHE_SYMBOL",s,meta[s],flush=True)
    report={
      "generated_at":datetime.now(timezone.utc).isoformat(),
      "purpose":"Recent stock50 daily state cache for Track B-E execution calibration",
      "source":"HF/Finnhub RTH 15m warmup + getdata-finance recent public RTH 15m sample",
      "symbols":out,
      "meta":meta
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    print("FINAL",json.dumps({"symbols":len(out),"meta":meta},ensure_ascii=False),flush=True)

if __name__=="__main__":main()
