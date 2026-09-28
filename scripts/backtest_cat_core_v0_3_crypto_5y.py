import csv, io, json, math, os, statistics, time, urllib.request, zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

UTC=timezone.utc
VISION="https://data.binance.vision/data/futures/um"
SYMBOLS=("BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","LINKUSDT")
START=datetime(2020,10,1,tzinfo=UTC)
EVAL_START=datetime(2021,9,28,tzinfo=UTC)
EVAL_END=datetime(2026,9,28,tzinfo=UTC)
TRAIN_END=datetime(2024,9,28,tzinfo=UTC)
VALID_END=datetime(2025,9,28,tzinfo=UTC)
FEE_BPS=4.0; SLIP_BPS=2.0; COST_BPS=FEE_BPS+SLIP_BPS
DONCHIAN=20; STOP_ATR=2.0; TRAIL_ATR=3.0
OUT=Path(os.environ.get("OUT","data/validation/cat_core_v0_3_crypto_5y.json"))

def norm_ts(x):
    v=int(x); return v//1000 if v>100_000_000_000_000 else v

def month_iter(a,b):
    y,m=a.year,a.month
    while (y,m)<=(b.year,b.month):
        yield y,m
        m+=1
        if m==13:y,m=y+1,1

def getzip(url,required=True):
    last=None
    for n in range(6):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"cat-v0.1"})
            with urllib.request.urlopen(req,timeout=45) as r: raw=r.read()
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                txt=z.read(z.namelist()[0]).decode("utf-8")
            out=[]
            for row in csv.reader(io.StringIO(txt)):
                if not row or not row[0].lstrip("-").isdigit():continue
                out.append({"t":norm_ts(row[0]),"ct":norm_ts(row[6]),"o":float(row[1]),"h":float(row[2]),"l":float(row[3]),"c":float(row[4]),"v":float(row[5])})
            return out
        except urllib.error.HTTPError as e:
            last=e
            if e.code==404 and not required:return []
            time.sleep(min(15,2+n*2))
        except Exception as e:
            last=e; time.sleep(min(15,2+n*2))
    if required: raise RuntimeError(f"download failed {url}: {last!r}")
    return []

def fetch1d(sym):
    rows=[]; seen=False
    last_month=datetime(EVAL_END.year,EVAL_END.month,1,tzinfo=UTC)
    for y,m in month_iter(START,last_month):
        d=datetime(y,m,1,tzinfo=UTC)
        if d>=last_month:break
        u=f"{VISION}/monthly/klines/{sym}/1d/{sym}-1d-{y:04d}-{m:02d}.zip"
        p=getzip(u,False)
        if not p:
            if seen: raise RuntimeError(f"missing completed month {sym} {y}-{m:02d}")
            continue
        seen=True; rows.extend(p); print("MONTH",sym,y,m,len(p),flush=True)
    cur=last_month
    while cur<EVAL_END:
        nxt=datetime.fromtimestamp(cur.timestamp()+86400,UTC)
        if nxt>EVAL_END:break
        u=f"{VISION}/daily/klines/{sym}/1d/{sym}-1d-{cur:%Y-%m-%d}.zip"
        p=getzip(u,False)
        if not p: break
        rows.extend(p); cur=nxt
    lo=int(START.timestamp()*1000); hi=int(EVAL_END.timestamp()*1000)
    d={x["t"]:x for x in rows if lo<=x["t"]<hi}
    return [d[k] for k in sorted(d)]

def ema(vals,n):
    k=2/(n+1); out=[]; e=None
    for x in vals:
        e=x if e is None else e+k*(x-e); out.append(e)
    return out

def enrich(D):
    cs=[x["c"] for x in D]; e200=ema(cs,200)
    atr=[]; a=None
    for i,x in enumerate(D):
        pc=cs[i-1] if i else x["c"]
        tr=max(x["h"]-x["l"],abs(x["h"]-pc),abs(x["l"]-pc))
        a=tr if a is None else ((a*13)+tr)/14
        atr.append(a)
    for i,x in enumerate(D):
        x["ema200"]=e200[i]; x["atr14"]=atr[i]
        for n in (20,60,120):
            x[f"ret{n}"]=x["c"]/D[i-n]["c"]-1 if i>=n and D[i-n]["c"]>0 else None
        x["prior20h"]=max(z["h"] for z in D[i-20:i]) if i>=20 else None
        x["prior20l"]=min(z["l"] for z in D[i-20:i]) if i>=20 else None
    return D

def cost(px): return px*COST_BPS/10000

def signal(x):
    if any(x.get(f"ret{n}") is None for n in (20,60,120)) or x.get("prior20h") is None:return None
    pos=sum(x[f"ret{n}"]>0 for n in (20,60,120))
    neg=sum(x[f"ret{n}"]<0 for n in (20,60,120))
    if pos>=2 and x["c"]>x["ema200"] and x["c"]>x["prior20h"]:return "LONG"
    if neg>=2 and x["c"]<x["ema200"] and x["c"]<x["prior20l"]:return "SHORT"
    return None

def sim(sym,D,bench):
    trades=[]; i=200
    while i<len(D)-1:
        x=D[i]
        if not (int(EVAL_START.timestamp()*1000)<=x["ct"]<int(EVAL_END.timestamp()*1000)):
            i+=1; continue
        side=signal(x)
        if side!="LONG":
            i+=1; continue
        bx=bench.get(x["t"])
        if bx is None or any(bx.get(f"ret{n}") is None for n in (20,60,120)):
            i+=1; continue
        if sum(bx[f"ret{n}"]>0 for n in (20,60,120)) < 2:
            i+=1; continue
        ebar=D[i+1]
        if ebar["t"]>=int(EVAL_END.timestamp()*1000):break
        sign=1 if side=="LONG" else -1
        entry=ebar["o"]
        risk=STOP_ATR*x["atr14"]
        if risk<=0: i+=1; continue
        stop=entry-sign*risk
        if stop<=0: i+=1; continue
        realized=-cost(entry)/risk
        hi_close=entry; lo_close=entry; reason="END"; exit_i=i+1; exit_px=None
        j=i+1
        while j<len(D) and D[j]["t"]<int(EVAL_END.timestamp()*1000):
            b=D[j]; exit_i=j
            if side=="LONG":
                if b["o"]<=stop:
                    exit_px=b["o"]; reason="GAP_STOP"
                elif b["l"]<=stop:
                    exit_px=stop; reason="STOP"
            else:
                if b["o"]>=stop:
                    exit_px=b["o"]; reason="GAP_STOP"
                elif b["h"]>=stop:
                    exit_px=stop; reason="STOP"
            if exit_px is not None:
                realized += sign*(exit_px-entry)/risk - cost(exit_px)/risk
                break
            hi_close=max(hi_close,b["c"]); lo_close=min(lo_close,b["c"])
            if side=="LONG":
                stop=max(stop,hi_close-TRAIL_ATR*b["atr14"])
            else:
                stop=min(stop,lo_close+TRAIL_ATR*b["atr14"])
            j+=1
        if exit_px is None:
            b=D[min(exit_i,len(D)-1)]; exit_px=b["c"]; reason="END_MARK"
            realized += sign*(exit_px-entry)/risk - cost(exit_px)/risk
        trades.append({"symbol":sym,"direction":side,"signal_t":x["ct"],"entry_t":ebar["t"],"exit_t":D[exit_i]["ct"],"entry":entry,"exit":exit_px,"initial_risk":risk,"risk_pct":risk/entry,"r":realized,"reason":reason,
                       "ret20":x["ret20"],"ret60":x["ret60"],"ret120":x["ret120"]})
        i=exit_i+1
    return trades

def metrics(ts):
    ts=sorted(ts,key=lambda z:(z["exit_t"],z["symbol"])); rs=[x["r"] for x in ts]
    pos=[r for r in rs if r>0]; neg=[r for r in rs if r<0]
    eq=peak=0.0; dd=0.0; cur=mx=0
    for r in rs:
        eq+=r; peak=max(peak,eq); dd=min(dd,eq-peak)
        if r<0: cur+=1; mx=max(mx,cur)
        else: cur=0
    return {"trades":len(ts),"long":sum(x["direction"]=="LONG" for x in ts),"short":sum(x["direction"]=="SHORT" for x in ts),
            "wins":len(pos),"losses":len(neg),"win_rate":len(pos)/len(ts) if ts else None,
            "total_r":sum(rs),"avg_r":statistics.fmean(rs) if rs else None,
            "profit_factor":sum(pos)/abs(sum(neg)) if neg else None,"max_drawdown_r":dd,"max_losing_streak":mx}

def split(t):
    d=datetime.fromtimestamp(t/1000,UTC)
    if d<TRAIN_END:return "development"
    if d<VALID_END:return "validation"
    return "oos"

def main():
    all=[]; counts={}; data={}
    for s in SYMBOLS:
        D=enrich(fetch1d(s)); counts[s]=len(D); data[s]=D
    bench={x["t"]:x for x in data["BTCUSDT"]}
    for s,D in data.items():
        t=sim(s,D,bench); all+=t
        print("RESULT",s,len(t),round(sum(x["r"] for x in t),3),flush=True)
    bys=defaultdict(list); byy=defaultdict(list); bysym=defaultdict(list)
    for t in all:
        bys[split(t["entry_t"])].append(t)
        byy[str(datetime.fromtimestamp(t["entry_t"]/1000,UTC).year)].append(t)
        bysym[t["symbol"]].append(t)
    out={"strategy":"CAT_CORE_v0.3","asset_class":"crypto_perpetual","rules":{
         "direction":"LONG only",
         "market_filter":"BTC completed daily 20/60/120d returns: at least 2 positive",
         "symbol_trend":"2 of ret20/60/120 positive + close>EMA200",
         "entry":"close > prior-20d high, next daily open",
         "stop":"2 ATR14","trail":"3 ATR14 from best completed close","tp":"none","cost_bps_per_fill":COST_BPS},
         "summary":metrics(all),
         "splits":{k:metrics(v) for k,v in sorted(bys.items())},
         "years":{k:metrics(v) for k,v in sorted(byy.items())},
         "symbols":{k:metrics(v) for k,v in sorted(bysym.items())},
         "data_counts":counts,"trades":all}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2),encoding="utf-8")
    print(json.dumps({"summary":out["summary"],"splits":out["splits"]},indent=2),flush=True)

if __name__=="__main__":main()
