import json, sys, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).parent))
import backtest_stock_track_b_e_cash_to_binance_futures_exec_v1 as x

OUT=Path("data/validation/stock50_e_daily_recent_cache.json")


def fetch_yahoo_daily(sym,tries=4):
    q=urllib.parse.quote(sym)
    p1=int(datetime(2025,1,1,tzinfo=timezone.utc).timestamp())
    p2=int(datetime(2026,9,29,tzinfo=timezone.utc).timestamp())
    url=f"https://query1.finance.yahoo.com/v8/finance/chart/{q}?period1={p1}&period2={p2}&interval=1d&events=history&includeAdjustedClose=true"
    last=None
    for n in range(tries):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req,timeout=30) as resp:
                data=json.loads(resp.read().decode("utf-8"))
            res=((data.get("chart") or {}).get("result") or [None])[0]
            if not res:return []
            ts=res.get("timestamp") or []
            ind=res.get("indicators") or {}
            adj=((ind.get("adjclose") or [{}])[0].get("adjclose") or [])
            cls=((ind.get("quote") or [{}])[0].get("close") or [])
            rows=[]
            for i,t in enumerate(ts):
                px=(adj[i] if i<len(adj) and adj[i] is not None else (cls[i] if i<len(cls) else None))
                if px is None or float(px)<=0:continue
                d=datetime.fromtimestamp(int(t),timezone.utc).astimezone(x.NY).date()
                rows.append({"date":d,"c":float(px)})
            return x.enrich_daily(rows)
        except Exception as e:
            last=e
            time.sleep(1.5*(n+1))
    print("YAHOO_CACHE_ERROR",sym,repr(last),flush=True)
    return []

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
        source="cash_intraday"
        if len(rows)<55 or rows[-1]["date"]<datetime(2026,9,18,tzinfo=timezone.utc).date():
            yr=fetch_yahoo_daily(s)
            if len(yr)>=55:
                rows=yr;source="yahoo_adjusted_daily"
        if len(rows)<55:
            print("CACHE_SHORT",s,len(rows),flush=True);continue
        out[s]=[{**z,"date":z["date"].isoformat()} for z in rows]
        meta[s]={"rows":len(rows),"first":rows[0]["date"].isoformat(),"last":rows[-1]["date"].isoformat(),
                 "hf_15m":len(hf.get(s,[])),"recent_15m":len(gd.get(s,[])),"source":source}
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
