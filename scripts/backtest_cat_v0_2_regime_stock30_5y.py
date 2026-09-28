import json, math, os, statistics, time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import duckdb

UTC=timezone.utc; NY=ZoneInfo("America/New_York")
HF_BASE="https://huggingface.co/datasets/mito0o852/OHLCV-1m/resolve/main/data"
SYMS=("AAPL","AMZN","AVGO","MSFT","MU","AMD","INTC","JPM","NFLX","V","COST","GOOGL","META","NVDA","QQQ","TSLA","UBER","WMT","AMAT","CAT","HD","ORCL","SPY","TSM","CRM","CSCO","DIS","IBM","COIN","MSTR")
SOURCE=tuple(sorted(set(SYMS+("FB","GOOG"))))
EVAL_START=datetime(2021,9,28,tzinfo=UTC); EVAL_END=datetime(2026,4,1,tzinfo=UTC); WARMUP_START=EVAL_START-timedelta(days=500)
FEE_BPS=4.0; SLIP_BPS=2.0; COST_BPS=FEE_BPS+SLIP_BPS
DONCHIAN=20; STOP_ATR=2.0; TRAIL_ATR=3.0
OUT=Path(os.environ.get("OUT","data/validation/cat_v0_2_regime_stock30_5y.json"))

def month_iter(start,end):
    y,m=start.year,start.month
    while (y,m)<=(end.year,end.month):
        yield y,m; m+=1
        if m==13:y,m=y+1,1

def canonical(ticker,d):
    if ticker=="FB":return "META" if d<datetime(2022,6,9).date() else None
    if ticker=="META":return "META" if d>=datetime(2022,6,9).date() else None
    if ticker=="GOOG":return "GOOGL" if d<datetime(2014,4,3).date() else None
    if ticker=="GOOGL":return "GOOGL" if d>=datetime(2014,4,3).date() else None
    return ticker if ticker in SYMS else None

def remote(con,y,m):
    url=f"{HF_BASE}/ohlcv_{y:04d}-{m:02d}.parquet"; ph=",".join(["?"]*len(SOURCE))
    q=f"""
    WITH src AS (
      SELECT ticker,timezone('America/New_York',timestamp) et,open,high,low,"close",volume
      FROM read_parquet('{url}') WHERE ticker IN ({ph})
    ),rth AS (
      SELECT * FROM src WHERE cast(et as time)>=time '09:30:00' and cast(et as time)<time '16:00:00'
    )
    SELECT ticker,cast(et as date) d,arg_min(open,et) o,max(high) h,min(low) l,arg_max("close",et) c,sum(volume) v
    FROM rth GROUP BY ticker,cast(et as date) ORDER BY ticker,d
    """
    return con.execute(q,list(SOURCE)).fetchall()

def collect():
    con=duckdb.connect(); con.execute("INSTALL httpfs; LOAD httpfs;")
    by={s:[] for s in SYMS}
    for y,m in month_iter(WARMUP_START,EVAL_END-timedelta(days=1)):
        rows=None
        for a in range(6):
            try: rows=remote(con,y,m); print("MONTH",y,m,len(rows),flush=True); break
            except Exception as e: print("RETRY",y,m,a+1,repr(e),flush=True); time.sleep(min(30,4*(a+1)))
        if rows is None: raise RuntimeError(f"missing {y}-{m:02d}")
        for ticker,d,o,h,l,c,v in rows:
            sym=canonical(str(ticker),d)
            if not sym:continue
            dt=datetime(d.year,d.month,d.day,tzinfo=NY).astimezone(UTC)
            if not (WARMUP_START<=dt<EVAL_END):continue
            by[sym].append({"date":str(d),"t":int(dt.timestamp()*1000),"ct":int((dt+timedelta(hours=23,minutes=59)).timestamp()*1000),"o":float(o),"h":float(h),"l":float(l),"c":float(c),"v":float(v or 0)})
    con.close()
    for s in by: by[s].sort(key=lambda z:z["date"])
    return by

def detect_splits(D):
    common=(1.5,2,3,4,5,7,10,15,20); ev=[]
    for i in range(1,len(D)):
        prev=D[i-1]["c"]; op=D[i]["o"]
        if prev<=0 or op<=0:continue
        ratio=prev/op; mag=ratio if ratio>=1 else 1/ratio
        if mag<1.35:continue
        f=min(common,key=lambda q:abs(mag/q-1.0))
        if abs(mag/f-1.0)<=.05: ev.append((i,(1/f if ratio>1 else f)))
    return ev

def adjust(D):
    ev=detect_splits(D)
    if not ev:return D
    out=[]
    for i,x in enumerate(D):
        pm=1.0
        for idx,f in ev:
            if i<idx:pm*=f
        q=x.copy()
        for k in ("o","h","l","c"):q[k]*=pm
        out.append(q)
    return out

def ema(vals,n):
    k=2/(n+1); out=[]; e=None
    for x in vals:e=x if e is None else e+k*(x-e);out.append(e)
    return out

def enrich(D):
    if not D:return D
    cs=[x["c"] for x in D]; e200=ema(cs,200); a=None
    for i,x in enumerate(D):
        pc=cs[i-1] if i else x["c"]; tr=max(x["h"]-x["l"],abs(x["h"]-pc),abs(x["l"]-pc)); a=tr if a is None else ((a*13)+tr)/14
        x["ema200"]=e200[i]; x["atr14"]=a
        for n in (20,60,120):x[f"ret{n}"]=x["c"]/D[i-n]["c"]-1 if i>=n and D[i-n]["c"]>0 else None
        x["prior20h"]=max(z["h"] for z in D[i-20:i]) if i>=20 else None
        x["prior20l"]=min(z["l"] for z in D[i-20:i]) if i>=20 else None
    return D

def signal(x):
    if any(x.get(f"ret{n}") is None for n in (20,60,120)) or x.get("prior20h") is None:return None
    pos=sum(x[f"ret{n}"]>0 for n in (20,60,120)); neg=sum(x[f"ret{n}"]<0 for n in (20,60,120))
    if pos>=2 and x["c"]>x["ema200"] and x["c"]>x["prior20h"]:return "LONG"
    if neg>=2 and x["c"]<x["ema200"] and x["c"]<x["prior20l"]:return "SHORT"
    return None

def cost(px):return px*COST_BPS/10000

def sim(sym,D,bench):
    trades=[];i=200;lo=int(EVAL_START.timestamp()*1000);hi=int(EVAL_END.timestamp()*1000)
    while i<len(D)-1:
        x=D[i]
        if not (lo<=x["t"]<hi):i+=1;continue
        side=signal(x)
        if not side:i+=1;continue
        bx=bench.get(x["date"])
        if bx is None:i+=1;continue
        if side=="LONG" and not (bx["c"]>bx["ema200"]):i+=1;continue
        if side=="SHORT" and not (bx["c"]<bx["ema200"]):i+=1;continue
        e=D[i+1]; sign=1 if side=="LONG" else -1
        entry=e["o"]; risk=STOP_ATR*x["atr14"]
        if risk<=0 or entry-sign*risk<=0:i+=1;continue
        stop=entry-sign*risk; realized=-cost(entry)/risk; hi_c=lo_c=entry; exit_i=i+1; exit_px=None;reason="END"
        j=i+1
        while j<len(D) and D[j]["t"]<hi:
            b=D[j];exit_i=j
            if side=="LONG":
                if b["o"]<=stop:exit_px=b["o"];reason="GAP_STOP"
                elif b["l"]<=stop:exit_px=stop;reason="STOP"
            else:
                if b["o"]>=stop:exit_px=b["o"];reason="GAP_STOP"
                elif b["h"]>=stop:exit_px=stop;reason="STOP"
            if exit_px is not None:
                realized+=sign*(exit_px-entry)/risk-cost(exit_px)/risk;break
            hi_c=max(hi_c,b["c"]);lo_c=min(lo_c,b["c"])
            if side=="LONG":stop=max(stop,hi_c-TRAIL_ATR*b["atr14"])
            else:stop=min(stop,lo_c+TRAIL_ATR*b["atr14"])
            j+=1
        if exit_px is None:
            b=D[min(exit_i,len(D)-1)];exit_px=b["c"];reason="END_MARK";realized+=sign*(exit_px-entry)/risk-cost(exit_px)/risk
        trades.append({"symbol":sym,"direction":side,"signal_t":x["ct"],"entry_t":e["t"],"exit_t":D[exit_i]["ct"],"entry":entry,"exit":exit_px,"initial_risk":risk,"risk_pct":risk/entry,"r":realized,"reason":reason})
        i=exit_i+1
    return trades

def metrics(ts):
    ts=sorted(ts,key=lambda z:(z["exit_t"],z["symbol"]));rs=[x["r"] for x in ts];pos=[r for r in rs if r>0];neg=[r for r in rs if r<0]
    eq=peak=0.;dd=0.;cur=mx=0
    for r in rs:
        eq+=r;peak=max(peak,eq);dd=min(dd,eq-peak)
        if r<0:cur+=1;mx=max(mx,cur)
        else:cur=0
    return {"trades":len(ts),"long":sum(x["direction"]=="LONG" for x in ts),"short":sum(x["direction"]=="SHORT" for x in ts),"wins":len(pos),"losses":len(neg),"win_rate":len(pos)/len(ts) if ts else None,"total_r":sum(rs),"avg_r":statistics.fmean(rs) if rs else None,"profit_factor":sum(pos)/abs(sum(neg)) if neg else None,"max_drawdown_r":dd,"max_losing_streak":mx}

def main():
    raw=collect();all=[];by={};data={}
    for sym,D in raw.items():
        D=enrich(adjust(D))
        if len(D)>=201:data[sym]=D
    bench={x["date"]:x for x in data["SPY"]}
    for sym,D in data.items():
        t=sim(sym,D,bench);all+=t;by[sym]=metrics(t);print("RESULT",sym,len(t),round(sum(x["r"] for x in t),3),flush=True)
    byy=defaultdict(list)
    for t in all:byy[str(datetime.fromtimestamp(t["entry_t"]/1000,UTC).year)].append(t)
    out={"strategy":"CAT_v0.2_REGIME","asset_class":"us_stock_underlying_proxy_for_futures","period":{"start":EVAL_START.isoformat(),"end_exclusive":EVAL_END.isoformat()},"rules":{"market_regime":"SPY completed RTH daily close > EMA200 permits longs; < EMA200 permits shorts","trend":"2 of ret20/60/120 same sign + symbol EMA200","entry":"prior-20d Donchian close breakout, next RTH session open","stop":"2 ATR14","trail":"3 ATR14 from best completed close","tp":"none","cost_bps_per_fill":COST_BPS},"summary":metrics(all),"years":{k:metrics(v) for k,v in sorted(byy.items())},"symbols":by,"trades":all}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,indent=2),encoding="utf-8");print(json.dumps({"summary":out["summary"]},indent=2),flush=True)

if __name__=="__main__":main()
