import csv, io, json, math, sys, time, urllib.parse, urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

sys.path.insert(0, str(Path(__file__).parent))
import backtest_wyckoff_exact_touch_ct as bt
import wyckoff_status as w

SYMS=("AAPL","AMZN","AVGO","AMD","INTC","META","MSFT","NVDA","TSLA")
EVAL_START={
"AAPL":1782849600000,
"AMZN":1778011200000,
"AVGO":1784145600000,
"AMD":1785528000000,
"INTC":1777406400000,
"META":1782158400000,
"MSFT":1784145600000,
"NVDA":1782158400000,
"TSLA":1776974400000,
}
BINANCE_FIRST={
"AAPL":1775484000000,
"AMZN":1770648300000,
"AVGO":1776692700000,
"AMD":1778074200000,
"INTC":1770042600000,
"META":1774535400000,
"MSFT":1776691800000,
"NVDA":1774536300000,
"TSLA":1769610600000,
}
END_MS=int(datetime(2026,9,26,tzinfo=timezone.utc).timestamp()*1000)-1
HF_BASE="https://huggingface.co/datasets/mito0o852/OHLCV-1m/resolve/main/data"
PROXY="https://zmbeamtclazjtfxyysre.supabase.co/functions/v1/stock-tradifi-history-export"
GETDATA_BASE="https://raw.githubusercontent.com/getdata-finance"
OUT=Path("data/validation/stock9_spot_vs_binance_same_window.json")
NY=ZoneInfo("America/New_York"); UTC=timezone.utc
TF15=15*60*1000
FEE_BPS=4.0; SLIPPAGE_BPS=2.0
A_OFF={"climax_spread_min":999.0,"climax_volume_min":999.0}

def day_key(z):
    return datetime.fromtimestamp(z["t"]/1000,UTC).astimezone(NY).date()

def aggregate_4h(bars):
    groups=defaultdict(list)
    for z in bars:
        dt=datetime.fromtimestamp(z["t"]/1000,UTC).astimezone(NY)
        mins=(dt.hour*60+dt.minute)-(9*60+30)
        if mins<0 or mins>=390: continue
        bucket=0 if mins<240 else 1
        groups[(dt.date(),bucket)].append(z)
    out=[]
    for _,g in sorted(groups.items()):
        g.sort(key=lambda x:x["t"]); last=g[-1]
        out.append({"t":g[0]["t"],"o":g[0]["o"],"h":max(x["h"] for x in g),
                    "l":min(x["l"] for x in g),"c":last["c"],"v":sum(x["v"] for x in g),
                    "ct":last.get("ct",last["t"]+TF15-1)})
    return out

def aggregate_daily(bars):
    groups=defaultdict(list)
    for z in bars:
        dt=datetime.fromtimestamp(z["t"]/1000,UTC).astimezone(NY)
        mins=dt.hour*60+dt.minute
        if not (570<=mins<960): continue
        groups[dt.date()].append(z)
    out=[]
    for _,g in sorted(groups.items()):
        g.sort(key=lambda x:x["t"]); last=g[-1]
        out.append({"t":g[0]["t"],"o":g[0]["o"],"h":max(x["h"] for x in g),
                    "l":min(x["l"] for x in g),"c":last["c"],"v":sum(x["v"] for x in g),
                    "ct":last.get("ct",last["t"]+TF15-1)})
    return out

def get_json(path,params=None,tries=5):
    kind={"/fapi/v1/exchangeInfo":"exchangeInfo","/fapi/v1/klines":"klines"}[path]
    p={"kind":kind}
    if params: p.update(params)
    url=PROXY+"?"+urllib.parse.urlencode(p)
    last=None
    for n in range(tries):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"wyckoff-same-window/1.0"})
            with urllib.request.urlopen(req,timeout=60) as r:
                return json.loads(r.read())
        except Exception as e:
            last=e
            if n+1>=tries: raise
            time.sleep(1.5*(n+1))
    raise last

def fetch_binance_15m(sym,start_ms):
    out=[]; cursor=start_ms
    while cursor<=END_MS:
        rows=get_json("/fapi/v1/klines",{"symbol":sym+"USDT","interval":"15m","startTime":cursor,"endTime":END_MS,"limit":1000})
        if not rows: break
        for x in rows:
            t=int(x[0]); ct=int(x[6])
            if ct>END_MS: continue
            out.append({"t":t,"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5]),"ct":ct})
        nxt=int(rows[-1][0])+TF15
        if nxt<=cursor: break
        cursor=nxt
        if len(rows)<1000: break
        time.sleep(.02)
    d={z["t"]:z for z in out}
    return [d[k] for k in sorted(d)]

def rth_only(bars):
    out=[]
    for z in bars:
        dt=datetime.fromtimestamp(z["t"]/1000,UTC).astimezone(NY)
        m=dt.hour*60+dt.minute
        if 570<=m<960: out.append(z)
    return out

def fetch_getdata(sym):
    repo=f"{sym.lower()}-15m-ohlcv-stocks-historical-data"
    url=f"{GETDATA_BASE}/{repo}/main/{sym}_15m.csv"
    req=urllib.request.Request(url,headers={"User-Agent":"wyckoff-validation/1.0"})
    with urllib.request.urlopen(req,timeout=60) as r:
        txt=r.read().decode("utf-8")
    out=[]
    for row in csv.DictReader(io.StringIO(txt)):
        dt=datetime.fromisoformat(row["datetime"])
        t=int(dt.timestamp()*1000)
        if t>END_MS: continue
        out.append({"t":t,"o":float(row["open"]),"h":float(row["high"]),"l":float(row["low"]),
                    "c":float(row["close"]),"v":float(row["volume"] or 0),"ct":t+TF15-1})
    return rth_only(out)

def fetch_hf_warmup():
    con=duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    by={s:[] for s in SYMS}
    for month in ("2026-01","2026-02","2026-03"):
        url=f"{HF_BASE}/ohlcv_{month}.parquet"
        qs=",".join(["?"]*len(SYMS))
        q=f"""
        WITH src AS (
          SELECT ticker, timezone('America/New_York', timestamp) et,
                 open, high, low, close, volume
          FROM read_parquet('{url}')
          WHERE ticker IN ({qs})
        ), rth AS (
          SELECT * FROM src
          WHERE CAST(et AS TIME)>=TIME '09:30:00'
            AND CAST(et AS TIME)<TIME '16:00:00'
        ), agg AS (
          SELECT ticker,time_bucket(INTERVAL '15 minutes',et) b,
                 arg_min(open,et) o,max(high) h,min(low) l,arg_max(close,et) c,sum(volume) v
          FROM rth GROUP BY ticker,b
        )
        SELECT ticker,b,o,h,l,c,v FROM agg ORDER BY ticker,b
        """
        rows=con.execute(q,list(SYMS)).fetchall()
        print("HF",month,"rows",len(rows),flush=True)
        for s,et,o,h,l,c,v in rows:
            if et.tzinfo is None: et=et.replace(tzinfo=NY)
            else: et=et.astimezone(NY)
            t=int(et.astimezone(UTC).timestamp()*1000)
            by[s].append({"t":t,"o":float(o),"h":float(h),"l":float(l),"c":float(c),"v":float(v or 0),"ct":t+TF15-1})
    con.close()
    return by

def merge_spot(hf,getd):
    # Prefer the newer public GitHub cash sample on overlapping timestamps.
    d={z["t"]:z for z in hf}
    for z in getd: d[z["t"]]=z
    return [d[k] for k in sorted(d) if k<=END_MS]

def filters(meta):
    by={x.get("filterType"):x for x in meta.get("filters",[])}
    pf=by.get("PRICE_FILTER",{}); lf=by.get("LOT_SIZE",{})
    return float(pf.get("tickSize") or .01),float(lf.get("stepSize") or 0),float(lf.get("minQty") or 0)

def run_engine(sym,M,eval_start,tick=.01,step=0,minqty=0):
    H=w.enrich(aggregate_4h(rth_only(M)))
    D=w.enrich(aggregate_daily(rth_only(M)))
    old_dataset,old_filters=bt.dataset,bt.symbol_filters
    try:
        bt._CACHE.clear()
        bt.dataset=lambda _s,D=D,H=H,M=M:(D,H,M)
        bt.symbol_filters=lambda _s:(tick,step,minqty)
        r=bt.simulate(sym,a_params=A_OFF,b_params=None,start_ms=eval_start,end_ms=END_MS,
                      fee_bps=FEE_BPS,slippage_bps=SLIPPAGE_BPS,
                      a_mode="snapshot",b_runner_mode="pivot",b_scale_mode="30_30_40")
        ts=[t for t in r["trades"] if t["track"]=="B" and t["reason"]!="OPEN_MARK"]
        return {"data":{"m15":len(M),"h4":len(H),"d1":len(D),"first":M[0]["t"] if M else None,"last":M[-1]["t"] if M else None},
                "trades":ts}
    finally:
        bt.dataset,bt.symbol_filters=old_dataset,old_filters

def stats(ts):
    n=len(ts); wns=sum(t["pnl"]>0 for t in ts); ls=sum(t["pnl"]<0 for t in ts)
    net=sum(t["r"] for t in ts); gp=sum(t["r"] for t in ts if t["r"]>0); gl=sum(t["r"] for t in ts if t["r"]<0)
    return {"trades":n,"wins":wns,"losses":ls,"win_rate":wns/n if n else None,
            "net_r":net,"avg_r":net/n if n else None,"profit_factor":gp/abs(gl) if gl<0 else None}

def portfolio(per,mode):
    ts=[]
    for s,x in per.items():
        for t in x[mode]["trades"]: ts.append({"symbol":s,**t})
    ts.sort(key=lambda x:x["exit_t"])
    eq=20000.0; peak=eq; mdd=0.0
    for t in ts:
        eq+=t["pnl"]; peak=max(peak,eq); mdd=max(mdd,(peak-eq)/peak if peak else 0)
    return {**stats(ts),"max_drawdown_fixed_20k":mdd,"trades":ts}

def main():
    hf=fetch_hf_warmup()
    ex=get_json("/fapi/v1/exchangeInfo")
    meta={x["symbol"]:x for x in ex.get("symbols",[])}
    per={}; errors={}
    old_cap,old_risk=bt.CAP,bt.RISK; bt.CAP=20000.0;bt.RISK=400.0
    try:
        for i,s in enumerate(SYMS,1):
            try:
                spot=merge_spot(hf[s],fetch_getdata(s))
                fut=fetch_binance_15m(s,BINANCE_FIRST[s])
                ftick,fstep,fmin=filters(meta[s+"USDT"])
                sr=run_engine(s,spot,EVAL_START[s],.01,0,0)
                br=run_engine(s,fut,EVAL_START[s],ftick,fstep,fmin)
                per[s]={"eval_start_ms":EVAL_START[s],"SPOT":sr,"BINANCE":br}
                print("RESULT",i,s,"SPOT",stats(sr["trades"]),"BINANCE",stats(br["trades"]),flush=True)
            except Exception as e:
                errors[s]=repr(e); print("ERROR",s,repr(e),flush=True)
    finally:
        bt.CAP,bt.RISK=old_cap,old_risk

    spot=portfolio(per,"SPOT"); binance=portfolio(per,"BINANCE")
    report={
      "generated_at":datetime.now(UTC).isoformat(),
      "purpose":"Same-symbol, same-evaluation-window spot-vs-Binance TradFi comparison",
      "symbols":list(SYMS),
      "period":{"end_exclusive":"2026-09-26T00:00:00Z",
                "per_symbol_eval_start_ms":EVAL_START},
      "data":{
        "SPOT":"HF/Finnhub 1m->15m through 2026-03-25 stitched to getdata-finance public GitHub 15m cash sample from 2026-03-26 through 2026-09-25; RTH only",
        "BINANCE":"Binance USD-M TradFi perpetual 15m via existing public export proxy; RTH bars build structure, all 15m bars manage positions",
        "note":"Spot and Binance use their own native prices; this is a native-market backtest comparison, not cross-market execution simulation."
      },
      "shared_rules":{
        "track":"B frozen","entry_fill":"exact planned-price touch low<=entry<=high",
        "fees_bps_per_fill":FEE_BPS,"slippage_bps_per_fill":SLIPPAGE_BPS,
        "management":"TP1 30%=>BE; TP2 30%=>TP1; 40% confirmed 4H pivot runner"
      },
      "totals":{
        "SPOT":{k:v for k,v in spot.items() if k!="trades"},
        "BINANCE":{k:v for k,v in binance.items() if k!="trades"}
      },
      "per_symbol":{
        s:{
          "eval_start_ms":x["eval_start_ms"],
          "SPOT":{**stats(x["SPOT"]["trades"]),"data":x["SPOT"]["data"]},
          "BINANCE":{**stats(x["BINANCE"]["trades"]),"data":x["BINANCE"]["data"]}
        } for s,x in per.items()
      },
      "errors":errors,
      "trades":{"SPOT":spot["trades"],"BINANCE":binance["trades"]}
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("FINAL",json.dumps({"totals":report["totals"],"errors":errors},ensure_ascii=False),flush=True)

if __name__=="__main__":
    main()
