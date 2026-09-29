import json, statistics, time, urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path

OUT=Path("data/validation/stock50_e_daily_recent_cache.json")
SYMS=(
    "AAPL","AMZN","AVGO","CRCL","MSFT","MU","SNDK","SNXX","SOXL","SPCX",
    "AMD","BABA","INTC","JPM","KORU","MSTR","NFLX","SKHY","SOXS","V",
    "COST","GOOGL","LLY","META","NBIS","NVDA","QQQ","TSLA","UBER","WMT",
    "AMAT","CAT","DRAM","EWY","HD","MRVL","MUU","ORCL","SPY","TSM",
    "AAOI","BE","COIN","CRM","CSCO","DIS","HOOD","IBM","LITE","TQQQ"
)
P1=int(datetime(2025,1,1,tzinfo=timezone.utc).timestamp())
P2=int(datetime(2026,9,29,tzinfo=timezone.utc).timestamp())

def enrich(rows):
    e20=e50=None;a20=2/21;a50=2/51;cl=[]
    out=[]
    for z in rows:
        c=float(z["c"]);cl.append(c)
        e20=c if e20 is None else a20*c+(1-a20)*e20
        e50=c if e50 is None else a50*c+(1-a50)*e50
        q=dict(z);q["ema20"]=e20;q["ema50"]=e50
        q["ret20"]=c/cl[-21]-1 if len(cl)>=21 and cl[-21]>0 else None
        out.append(q)
    return out

def fetch(sym,tries=5):
    qs=urllib.parse.urlencode({"period1":P1,"period2":P2,"interval":"1d","events":"history","includeAdjustedClose":"true"})
    hosts=("query1.finance.yahoo.com","query2.finance.yahoo.com")
    last=None
    for n in range(tries):
        host=hosts[n%2]
        url=f"https://{host}/v8/finance/chart/{urllib.parse.quote(sym)}?{qs}"
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 stock-e-cache/1.0","Accept":"application/json"})
            with urllib.request.urlopen(req,timeout=25) as r:data=json.loads(r.read())
            res=(data.get("chart",{}).get("result") or [None])[0]
            if not res:raise RuntimeError(data.get("chart",{}).get("error"))
            ts=res.get("timestamp") or []
            quote=((res.get("indicators",{}).get("quote") or [{}])[0]).get("close") or []
            adjarr=((res.get("indicators",{}).get("adjclose") or [{}])[0]).get("adjclose") or []
            rows=[]
            for i,t in enumerate(ts):
                c=(adjarr[i] if i<len(adjarr) and adjarr[i] is not None else (quote[i] if i<len(quote) else None))
                if c is None or c<=0:continue
                d=datetime.fromtimestamp(int(t),timezone.utc).date()
                rows.append({"date":d,"c":float(c)})
            rows.sort(key=lambda z:z["date"])
            return enrich(rows)
        except Exception as e:
            last=e;time.sleep(1.5*(n+1))
    raise RuntimeError(f"{sym}: {last!r}")

def main():
    out={};meta={};errs={}
    with ThreadPoolExecutor(max_workers=8) as ex:
        fs={ex.submit(fetch,s):s for s in SYMS}
        for fut in as_completed(fs):
            s=fs[fut]
            try:
                rows=fut.result()
                if len(rows)>=55:
                    out[s]=[{**z,"date":z["date"].isoformat()} for z in rows]
                    meta[s]={"rows":len(rows),"first":rows[0]["date"].isoformat(),"last":rows[-1]["date"].isoformat()}
                print("YAHOO_DAILY",s,len(rows),meta.get(s),flush=True)
            except Exception as e:
                errs[s]=repr(e);print("YAHOO_ERROR",s,repr(e),flush=True)
    report={
      "generated_at":datetime.now(timezone.utc).isoformat(),
      "purpose":"Recent stock50 daily E-filter cache for futures execution calibration",
      "source":"Yahoo Finance chart API adjusted daily close when available, otherwise daily close",
      "symbols":out,"meta":meta,"errors":errs
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    print("FINAL",json.dumps({"symbols":len(out),"errors":errs,"last_dates":{s:v["last"] for s,v in meta.items()}},ensure_ascii=False),flush=True)

if __name__=="__main__":main()
