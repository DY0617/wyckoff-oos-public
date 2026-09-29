import csv, io, json, statistics, time, urllib.request, urllib.error, zipfile
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/validation/ptc_v0_1_crypto_pilot.json"
UTC=timezone.utc

SYMBOLS=("BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT")
FETCH_START=datetime(2023,1,1,tzinfo=UTC)
EVAL_START=datetime(2023,9,1,tzinfo=UTC)
EVAL_END=datetime(2026,9,1,tzinfo=UTC)

FEE_BPS=4.0
SLIP_BPS=2.0
COST_BPS=FEE_BPS+SLIP_BPS
CONFIRM_WINDOW_BARS=8
ENTRY_VALID_BARS=4
MAX_HOLD_BARS=48*4
ENTRY_BUFFER_ATR=0.05
STOP_BUFFER_ATR=0.10
STOP_MIN_ATR=0.8
STOP_MAX_ATR=2.0
TP1_R=1.5
TP2_R=2.5

def month_iter(start,end):
    y,m=start.year,start.month
    while (y,m)<(end.year,end.month):
        yield y,m
        m+=1
        if m==13:y,m=y+1,1

def fetch_zip(url,attempts=5):
    last=None
    for a in range(1,attempts+1):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"ptc-v0.1/1.0"})
            with urllib.request.urlopen(req,timeout=60) as r:return r.read()
        except urllib.error.HTTPError as e:
            if e.code==404:return None
            last=e
        except Exception as e:
            last=e
        time.sleep(min(20,2*a))
    raise RuntimeError(f"download failed: {url} {last!r}")

def normalize_ms(x):
    v=int(float(x))
    while v>10_000_000_000_000:v//=1000
    if v<10_000_000_000:v*=1000
    return v

def load_15m(sym):
    out=[]
    lo=int(FETCH_START.timestamp()*1000);hi=int(EVAL_END.timestamp()*1000)
    for y,m in month_iter(FETCH_START,EVAL_END):
        url=f"https://data.binance.vision/data/futures/um/monthly/klines/{sym}/15m/{sym}-15m-{y:04d}-{m:02d}.zip"
        raw=fetch_zip(url)
        if raw is None:
            print("MISSING",sym,y,m,flush=True);continue
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            txt=z.read(z.namelist()[0]).decode("utf-8-sig")
        n=0
        for r in csv.reader(io.StringIO(txt)):
            if not r:continue
            try:
                t=normalize_ms(r[0]);o,h,l,c,v=map(float,r[1:6])
            except Exception:
                continue
            if lo<=t<hi:
                out.append({"t":t,"ct":t+15*60_000,"o":o,"h":h,"l":l,"c":c,"v":v});n+=1
        print("MONTH",sym,f"{y:04d}-{m:02d}",n,flush=True)
    dedup={x["t"]:x for x in out}
    out=[dedup[k] for k in sorted(dedup)]
    print("LOADED",sym,len(out),flush=True)
    return out

def aggregate(base,minutes):
    ms=minutes*60_000;b=defaultdict(list)
    for x in base:b[(x["t"]//ms)*ms].append(x)
    need=minutes//15;out=[]
    for k in sorted(b):
        xs=sorted(b[k],key=lambda z:z["t"])
        if len(xs)!=need or xs[0]["t"]!=k or xs[-1]["ct"]!=k+ms:continue
        out.append({"t":k,"ct":k+ms,"o":xs[0]["o"],"h":max(z["h"] for z in xs),
                    "l":min(z["l"] for z in xs),"c":xs[-1]["c"],"v":sum(z["v"] for z in xs)})
    return out

def ema(vals,n):
    k=2/(n+1);e=None;out=[]
    for x in vals:
        e=x if e is None else e+k*(x-e);out.append(e)
    return out

def enrich(D):
    if not D:return D
    cs=[x["c"] for x in D]
    e20=ema(cs,20);e50=ema(cs,50);e200=ema(cs,200);atr=None
    for i,x in enumerate(D):
        pc=cs[i-1] if i else x["c"]
        tr=max(x["h"]-x["l"],abs(x["h"]-pc),abs(x["l"]-pc))
        atr=tr if atr is None else ((atr*13)+tr)/14
        x["atr14"]=atr;x["ema20"]=e20[i];x["ema50"]=e50[i];x["ema200"]=e200[i]
        x["ema20_5ago"]=e20[i-5] if i>=5 else None
        x["prior4h"]=max(z["h"] for z in D[i-4:i]) if i>=4 else None
        x["prior4l"]=min(z["l"] for z in D[i-4:i]) if i>=4 else None
    return D

def regime4(x):
    if x is None or x.get("ema20_5ago") is None:return None
    if x["c"]>x["ema200"] and x["ema20"]>x["ema50"]>x["ema200"] and x["ema20"]>x["ema20_5ago"]:
        return "LONG"
    if x["c"]<x["ema200"] and x["ema20"]<x["ema50"]<x["ema200"] and x["ema20"]<x["ema20_5ago"]:
        return "SHORT"
    return None

def pullback1(x,side):
    A=x["atr14"]
    if A is None or A<=0:return False
    if side=="LONG":
        return x["c"]<=x["ema20"] and x["c"]>x["ema50"] and x["l"]>=x["ema50"]-0.25*A
    return x["c"]>=x["ema20"] and x["c"]<x["ema50"] and x["h"]<=x["ema50"]+0.25*A

def confirm15(x,side):
    if x.get("prior4h") is None or x.get("prior4l") is None:return False
    if side=="LONG":return x["c"]>x["ema20"] and x["c"]>x["prior4h"]
    return x["c"]<x["ema20"] and x["c"]<x["prior4l"]

def cost(px,frac=1.0):return frac*px*COST_BPS/10000.0

def metrics(ts):
    o=sorted(ts,key=lambda z:(z["exit_t"],z["symbol"],z["direction"]))
    rs=[x["r"] for x in o];pos=[r for r in rs if r>0];neg=[r for r in rs if r<0]
    eq=peak=0.0;dd=0.0;cur=mx=0
    for r in rs:
        eq+=r;peak=max(peak,eq);dd=min(dd,eq-peak)
        if r<0:cur+=1;mx=max(mx,cur)
        else:cur=0
    holds=[x["hold_hours"] for x in o]
    return {"trades":len(o),"long":sum(x["direction"]=="LONG" for x in o),
            "short":sum(x["direction"]=="SHORT" for x in o),
            "wins":len(pos),"losses":len(neg),"win_rate":len(pos)/len(o) if o else None,
            "total_r":sum(rs),"avg_r":statistics.fmean(rs) if rs else None,
            "profit_factor":sum(pos)/abs(sum(neg)) if neg else None,
            "max_drawdown_r":dd,"max_losing_streak":mx,
            "tp1_hit_rate":sum(x["tp1_hit"] for x in o)/len(o) if o else None,
            "tp2_hit_rate":sum(x["tp2_hit"] for x in o)/len(o) if o else None,
            "avg_hold_hours":statistics.fmean(holds) if holds else None,
            "median_hold_hours":statistics.median(holds) if holds else None}

def simulate_symbol(sym,b15):
    q15=enrich([dict(x) for x in b15])
    h1=enrich(aggregate(b15,60));h4=enrich(aggregate(b15,240))
    t15=[x["t"] for x in q15];ct4=[x["ct"] for x in h4]
    lo=int(EVAL_START.timestamp()*1000);hi=int(EVAL_END.timestamp()*1000)
    trades=[];st=defaultdict(int);busy_until=-1

    for x in h1:
        if x["ct"]<lo or x["ct"]>=hi:continue
        if x["ct"]<busy_until:
            st["pullback_while_busy"]+=1;continue
        k=bisect_left(ct4,x["ct"]+1)-1
        if k<0:continue
        side=regime4(h4[k])
        if side is None or not pullback1(x,side):continue
        st["pullback_setups"]+=1

        start=bisect_left(t15,x["ct"])
        confirm_idx=None
        for j in range(start,min(start+CONFIRM_WINDOW_BARS,len(q15))):
            b=q15[j]
            if b["t"]>=hi:break
            if confirm15(b,side):
                confirm_idx=j;break
        confirm_expiry=x["ct"]+CONFIRM_WINDOW_BARS*15*60_000
        if confirm_idx is None:
            st["confirmation_expired"]+=1
            busy_until=confirm_expiry
            continue
        st["confirmed"]+=1
        c=q15[confirm_idx];A=c["atr14"]
        segment_start=bisect_left(t15,x["t"])
        seg=q15[segment_start:confirm_idx+1]
        if not seg:
            st["invalid_segment"]+=1;busy_until=c["ct"];continue

        if side=="LONG":
            entry=c["h"]+ENTRY_BUFFER_ATR*A
            sl=min(z["l"] for z in seg)-STOP_BUFFER_ATR*A
            risk=entry-sl
            tp1=entry+TP1_R*risk;tp2=entry+TP2_R*risk
        else:
            entry=c["l"]-ENTRY_BUFFER_ATR*A
            sl=max(z["h"] for z in seg)+STOP_BUFFER_ATR*A
            risk=sl-entry
            tp1=entry-TP1_R*risk;tp2=entry-TP2_R*risk
        risk_atr=risk/A if A and A>0 else None
        if risk<=0 or risk_atr is None or not (STOP_MIN_ATR<=risk_atr<=STOP_MAX_ATR):
            st["structural_risk_skipped"]+=1
            busy_until=c["ct"]
            continue
        st["valid_orders"]+=1

        pstart=bisect_left(t15,c["ct"])
        fill_idx=None;fill_px=None
        for j in range(pstart,min(pstart+ENTRY_VALID_BARS,len(q15))):
            b=q15[j]
            if b["t"]>=hi:break
            if side=="LONG":
                if b["o"]>=entry:fill_idx=j;fill_px=b["o"];break
                if b["h"]>=entry:fill_idx=j;fill_px=entry;break
            else:
                if b["o"]<=entry:fill_idx=j;fill_px=b["o"];break
                if b["l"]<=entry:fill_idx=j;fill_px=entry;break
        order_expiry=c["ct"]+ENTRY_VALID_BARS*15*60_000
        if fill_idx is None:
            st["entry_expired"]+=1;busy_until=order_expiry;continue
        st["filled"]+=1

        pnl=-cost(fill_px,1.0);remaining=1.0;tp1_hit=False;tp2_hit=False
        exit_t=q15[fill_idx]["ct"];exit_px=fill_px;reason="TIME"
        last_idx=min(fill_idx+MAX_HOLD_BARS-1,len(q15)-1)

        for j in range(fill_idx,last_idx+1):
            b=q15[j]
            if b["t"]>=hi:
                last_idx=j;break

            if side=="LONG":
                if b["o"]<=sl:
                    pnl+=remaining*(b["o"]-fill_px)-cost(b["o"],remaining)
                    exit_px=b["o"];exit_t=b["ct"];reason="GAP_SL";remaining=0.0;break
                if b["l"]<=sl:
                    pnl+=remaining*(sl-fill_px)-cost(sl,remaining)
                    exit_px=sl;exit_t=b["ct"];reason="SL";remaining=0.0;break

                if not tp1_hit and b["o"]>=tp1:
                    frac=min(0.5,remaining);pnl+=frac*(b["o"]-fill_px)-cost(b["o"],frac)
                    remaining-=frac;tp1_hit=True
                elif not tp1_hit and b["h"]>=tp1:
                    frac=min(0.5,remaining);pnl+=frac*(tp1-fill_px)-cost(tp1,frac)
                    remaining-=frac;tp1_hit=True

                if remaining>0 and b["o"]>=tp2:
                    pnl+=remaining*(b["o"]-fill_px)-cost(b["o"],remaining)
                    remaining=0.0;tp2_hit=True;exit_px=b["o"];exit_t=b["ct"];reason="TP2_GAP";break
                if remaining>0 and b["h"]>=tp2:
                    pnl+=remaining*(tp2-fill_px)-cost(tp2,remaining)
                    remaining=0.0;tp2_hit=True;exit_px=tp2;exit_t=b["ct"];reason="TP2";break
            else:
                if b["o"]>=sl:
                    pnl+=remaining*(fill_px-b["o"])-cost(b["o"],remaining)
                    exit_px=b["o"];exit_t=b["ct"];reason="GAP_SL";remaining=0.0;break
                if b["h"]>=sl:
                    pnl+=remaining*(fill_px-sl)-cost(sl,remaining)
                    exit_px=sl;exit_t=b["ct"];reason="SL";remaining=0.0;break

                if not tp1_hit and b["o"]<=tp1:
                    frac=min(0.5,remaining);pnl+=frac*(fill_px-b["o"])-cost(b["o"],frac)
                    remaining-=frac;tp1_hit=True
                elif not tp1_hit and b["l"]<=tp1:
                    frac=min(0.5,remaining);pnl+=frac*(fill_px-tp1)-cost(tp1,frac)
                    remaining-=frac;tp1_hit=True

                if remaining>0 and b["o"]<=tp2:
                    pnl+=remaining*(fill_px-b["o"])-cost(b["o"],remaining)
                    remaining=0.0;tp2_hit=True;exit_px=b["o"];exit_t=b["ct"];reason="TP2_GAP";break
                if remaining>0 and b["l"]<=tp2:
                    pnl+=remaining*(fill_px-tp2)-cost(tp2,remaining)
                    remaining=0.0;tp2_hit=True;exit_px=tp2;exit_t=b["ct"];reason="TP2";break

            if j==last_idx and remaining>0:
                px=b["c"]
                pnl+=remaining*((px-fill_px) if side=="LONG" else (fill_px-px))-cost(px,remaining)
                exit_px=px;exit_t=b["ct"];reason="TIME";remaining=0.0;break

        if remaining>0:
            b=q15[last_idx];px=b["c"]
            pnl+=remaining*((px-fill_px) if side=="LONG" else (fill_px-px))-cost(px,remaining)
            exit_px=px;exit_t=b["ct"];reason="END";remaining=0.0

        rr=pnl/risk
        trades.append({"symbol":sym,"direction":side,"pullback_t":x["ct"],"confirm_t":c["ct"],
                       "entry_t":q15[fill_idx]["t"],"exit_t":exit_t,
                       "entry":entry,"fill":fill_px,"sl":sl,"tp1":tp1,"tp2":tp2,
                       "planned_risk":risk,"risk_atr":risk_atr,"r":rr,"reason":reason,
                       "tp1_hit":tp1_hit,"tp2_hit":tp2_hit,
                       "hold_hours":max(0.0,(exit_t-q15[fill_idx]["t"])/3_600_000)})
        busy_until=exit_t

    st=dict(st)
    st["confirmation_rate"]=st.get("confirmed",0)/st.get("pullback_setups",1) if st.get("pullback_setups",0) else None
    st["entry_fill_rate"]=st.get("filled",0)/st.get("valid_orders",1) if st.get("valid_orders",0) else None
    st["structural_skip_rate"]=st.get("structural_risk_skipped",0)/st.get("confirmed",1) if st.get("confirmed",0) else None
    return trades,st

def main():
    alltr=[];symbols={}
    for sym in SYMBOLS:
        b15=load_15m(sym);ts,st=simulate_symbol(sym,b15)
        symbols[sym]={"metrics":metrics(ts),"stats":st};alltr+=ts
        print("RESULT",sym,json.dumps(symbols[sym]),flush=True)
    years=defaultdict(list);dirs=defaultdict(list)
    for t in alltr:
        years[str(datetime.fromtimestamp(t["entry_t"]/1000,UTC).year)].append(t)
        dirs[t["direction"]].append(t)
    out={"strategy":"PTC v0.1 frozen pilot","asset_class":"Binance USDT-M perpetual",
         "period":{"fetch_start":FETCH_START.isoformat(),"eval_start":EVAL_START.isoformat(),"eval_end_exclusive":EVAL_END.isoformat()},
         "summary":metrics(alltr),"directions":{k:metrics(v) for k,v in sorted(dirs.items())},
         "years":{k:metrics(v) for k,v in sorted(years.items())},"symbols":symbols,"trades":alltr}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2),encoding="utf-8")
    print("FINAL",json.dumps({k:v for k,v in out.items() if k!="trades"},indent=2),flush=True)

if __name__=="__main__":main()
