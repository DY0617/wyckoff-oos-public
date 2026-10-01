import bisect, calendar, json, math, statistics
from collections import defaultdict
from datetime import datetime, timezone, timedelta, time
from pathlib import Path
from zoneinfo import ZoneInfo
import duckdb

ROOT=Path(__file__).resolve().parents[1]
DATA=Path("data/cache/stock53_recent5y_15m.parquet")
OUT=Path("data/validation/easychart_a_stock_v01.json")
NY=ZoneInfo("America/New_York")
UTC=timezone.utc

SYMS=(
"AAPL","AMZN","AVGO","CRCL","DELL","MSFT","MU","SNDK","SNXX","SOXL","SPCX",
"AMD","BABA","INTC","JPM","KORU","MSTR","NFLX","SKHY","SMCI","SOXS","V",
"COST","GOOGL","LLY","META","NBIS","NVDA","QQQ","TSLA","UBER","WMT",
"AMAT","CAT","DRAM","EWY","HD","MRVL","MUU","ORCL","SPY","TSM",
"AAOI","AXTI","BE","COIN","CRM","CSCO","DIS","HOOD","IBM","LITE","TQQQ"
)
EVAL_START=datetime(2021,4,1,tzinfo=NY)
EVAL_END=datetime(2026,4,1,tzinfo=NY)
HOLDOUT_START=datetime(2024,4,1,tzinfo=NY)

GAP_MIN=0.10
SLOPE50_MIN=0.10
SWEEP_LOOKBACK=20
SWEEP_MIN_ATR=0.05
SWEEP_MAX_ATR=1.50
DISP_MAX_BARS=3
DISP_BODY_ATR=0.80
DISP_CLV=0.70
FVG_MIN_ATR=0.10
ENTRY_DEPTH=0.50
RETEST_15M_BARS=32
STOP_BUFFER_ATR=0.15
MAX_HOLD_15M_BARS=192
COST_BPS_SIDE=6.0
RISK_DOLLARS=400.0

def ms(dt):
    if dt.tzinfo is None: dt=dt.replace(tzinfo=NY)
    return int(dt.timestamp()*1000)

def ema(vals,n):
    out=[];e=None;k=2.0/(n+1.0)
    for x in vals:
        e=x if e is None else e+k*(x-e);out.append(e)
    return out

def enrich(bars):
    if not bars:return bars
    tr=[];atr=[];a=None
    for i,x in enumerate(bars):
        pc=bars[i-1]["c"] if i else x["c"]
        tv=max(x["h"]-x["l"],abs(x["h"]-pc),abs(x["l"]-pc));tr.append(tv)
        if i<13:atr.append(None)
        elif i==13:
            a=sum(tr[:14])/14;atr.append(a)
        else:
            a=(13*a+tv)/14;atr.append(a)
    for n in (20,50,200):
        e=ema([x["c"] for x in bars],n)
        for i,x in enumerate(bars):x[f"ema{n}"]=e[i]
    for i,x in enumerate(bars):x["atr"]=atr[i]
    return bars

def load15(con,sym):
    rows=con.execute("SELECT b,o,h,l,c,v FROM read_parquet(?) WHERE symbol=? ORDER BY b",[str(DATA),sym]).fetchall()
    out=[]
    for dt,o,h,l,c,v in rows:
        if dt.tzinfo is None:dt=dt.replace(tzinfo=NY)
        else:dt=dt.astimezone(NY)
        out.append({"t":ms(dt),"dt":dt,"o":float(o),"h":float(h),"l":float(l),"c":float(c),"v":float(v or 0)})
    return out

def aggregate_daily(M):
    g=defaultdict(list)
    for z in M:g[z["dt"].date()].append(z)
    out=[]
    for d in sorted(g):
        xs=g[d]
        if len(xs)<24:continue
        out.append({"t":xs[0]["t"],"ct":xs[-1]["t"]+15*60*1000-1,"date":d,
                    "o":xs[0]["o"],"h":max(x["h"] for x in xs),"l":min(x["l"] for x in xs),
                    "c":xs[-1]["c"],"v":sum(x["v"] for x in xs)})
    return enrich(out)

def aggregate_1h_rth(M):
    g=defaultdict(list)
    for z in M:
        dt=z["dt"]
        mins=(dt.hour*60+dt.minute)-(9*60+30)
        if mins<0:continue
        bucket=mins//60
        if bucket<0 or bucket>5:continue
        start=dt.replace(hour=9,minute=30,second=0,microsecond=0)+timedelta(hours=bucket)
        g[(dt.date(),bucket,start)].append(z)
    out=[]
    for (_,_,start),xs in sorted(g.items(),key=lambda kv:kv[0][2]):
        xs=sorted(xs,key=lambda x:x["t"])
        if len(xs)!=4:continue
        if [x["dt"].minute for x in xs] not in ([30,45,0,15],[0,15,30,45]):
            pass
        out.append({"t":xs[0]["t"],"ct":xs[-1]["t"]+15*60*1000-1,"date":start.date(),
                    "o":xs[0]["o"],"h":max(x["h"] for x in xs),"l":min(x["l"] for x in xs),
                    "c":xs[-1]["c"],"v":sum(x["v"] for x in xs)})
    return enrich(out)

def aggregate_weekly(D):
    g=defaultdict(list)
    for z in D:
        iso=z["date"].isocalendar();g[(iso.year,iso.week)].append(z)
    out=[]
    for k in sorted(g):
        xs=g[k]
        if len(xs)<3:continue
        out.append({"t":xs[0]["t"],"ct":xs[-1]["ct"],"o":xs[0]["o"],"h":max(x["h"] for x in xs),
                    "l":min(x["l"] for x in xs),"c":xs[-1]["c"],"v":sum(x["v"] for x in xs)})
    if out:
        e=ema([x["c"] for x in out],20)
        for i,x in enumerate(out):x["ema20"]=e[i]
    return out

def aggregate_monthly(D):
    g=defaultdict(list)
    for z in D:g[(z["date"].year,z["date"].month)].append(z)
    out=[]
    for k in sorted(g):
        xs=g[k]
        if len(xs)<10:continue
        out.append({"t":xs[0]["t"],"ct":xs[-1]["ct"],"o":xs[0]["o"],"h":max(x["h"] for x in xs),
                    "l":min(x["l"] for x in xs),"c":xs[-1]["c"],"v":sum(x["v"] for x in xs)})
    if out:
        e4=ema([x["c"] for x in out],4)
        for i,x in enumerate(out):x["ema4"]=e4[i]
    return out

def clv(x):
    r=x["h"]-x["l"]
    return (x["c"]-x["l"])/r if r else .5

def body(x):return abs(x["c"]-x["o"])

def daily_ctx(D,Dclose,t,direction):
    di=bisect.bisect_right(Dclose,t)-1
    if di<55:return None
    x=D[di];A=x.get("atr")
    if not A or A<=0:return None
    sign=1 if direction=="LONG" else -1
    trend=(x["c"]>x["ema50"] and x["ema20"]>x["ema50"]) if direction=="LONG" else (x["c"]<x["ema50"] and x["ema20"]<x["ema50"])
    gap=sign*(x["ema20"]-x["ema50"])/A
    slope=sign*(x["ema50"]-D[di-5]["ema50"])/A
    return {"ok":trend and gap>=GAP_MIN and slope>=SLOPE50_MIN,"gap":gap,"slope50":slope}

def htf_strong(W,M,t,direction):
    wc=[x["ct"] for x in W];mc=[x["ct"] for x in M]
    wi=bisect.bisect_right(wc,t)-1;mi=bisect.bisect_right(mc,t)-1
    if wi<0 or mi<0:return False
    w=W[wi];m=M[mi]
    if direction=="LONG":return w["c"]>w["ema20"] and m["c"]>m["ema4"]
    return w["c"]<w["ema20"] and m["c"]<m["ema4"]

def find_setup(H,D,Dclose,i):
    if i<SWEEP_LOOKBACK or i>=len(H)-DISP_MAX_BARS:return None
    s=H[i];A=s.get("atr")
    if not A:return None
    prev=H[i-SWEEP_LOOKBACK:i]
    ph=max(x["h"] for x in prev);pl=min(x["l"] for x in prev)
    long_sweep=s["l"]<pl-SWEEP_MIN_ATR*A and s["c"]>pl and (pl-s["l"])<=SWEEP_MAX_ATR*A
    short_sweep=s["h"]>ph+SWEEP_MIN_ATR*A and s["c"]<ph and (s["h"]-ph)<=SWEEP_MAX_ATR*A
    for direction,ok in (("LONG",long_sweep),("SHORT",short_sweep)):
        if not ok:continue
        dc=daily_ctx(D,Dclose,s["ct"],direction)
        if not dc or not dc["ok"]:continue
        for j in range(i+1,min(len(H),i+1+DISP_MAX_BARS)):
            q=H[j];qa=q.get("atr")
            if not qa or q["date"]!=s["date"] or j<2:continue
            strong=body(q)>=DISP_BODY_ATR*qa
            if direction=="LONG":
                directional=q["c"]>q["o"] and clv(q)>=DISP_CLV and q["c"]>s["h"]
                lo=H[j-2]["h"];hi=q["l"]
            else:
                directional=q["c"]<q["o"] and clv(q)<=1-DISP_CLV and q["c"]<s["l"]
                lo=q["h"];hi=H[j-2]["l"]
            gap=hi-lo
            if not(strong and directional and gap>=FVG_MIN_ATR*qa):continue
            entry=(lo+hi)/2
            stop=s["l"]-STOP_BUFFER_ATR*A if direction=="LONG" else s["h"]+STOP_BUFFER_ATR*A
            risk=abs(entry-stop)
            if risk<=0 or risk<.10*qa or risk>4*qa:continue
            return {"direction":direction,"signal_t":q["ct"],"entry":entry,"stop":stop,"risk":risk,
                    "sweep_t":s["t"],"disp_t":q["t"],"fvg_low":lo,"fvg_high":hi,"daily":dc}
    return None

def locate_entry(M,setup):
    ts=[x["t"] for x in M]
    mi=bisect.bisect_left(ts,setup["signal_t"]+1)
    end=min(len(M),mi+RETEST_15M_BARS)
    while mi<end:
        z=M[mi]
        if z["l"]<=setup["entry"]<=z["h"]:return mi
        mi+=1
    return None

def simulate(M,ei,s,target_r,symbol):
    direction=s["direction"];sign=1 if direction=="LONG" else -1
    entry=s["entry"];stop=s["stop"];risk=s["risk"]
    target=entry+sign*target_r*risk
    size=RISK_DOLLARS/risk;cr=COST_BPS_SIDE/10000
    pnl=-size*entry*cr;last=M[ei];reason="TIME"
    end=min(len(M),ei+MAX_HOLD_15M_BARS)
    exit_t=M[ei]["t"]
    for k in range(ei,end):
        z=M[k];last=z
        hit_stop=z["l"]<=stop if direction=="LONG" else z["h"]>=stop
        if hit_stop:
            pnl+=size*sign*(stop-entry)-size*stop*cr;reason="STOP";exit_t=z["t"];break
        hit_tp=z["h"]>=target if direction=="LONG" else z["l"]<=target
        if hit_tp:
            pnl+=size*sign*(target-entry)-size*target*cr;reason="TP";exit_t=z["t"];break
    else:
        px=last["c"];pnl+=size*sign*(px-entry)-size*px*cr;exit_t=last["t"]
    q=dict(s);q.update({"symbol":symbol,"entry_t":M[ei]["t"],"exit_t":exit_t,"target_r":target_r,"r":pnl/RISK_DOLLARS,"reason":reason})
    return q

def suppress(ts):
    out=[];active={}
    for t in sorted(ts,key=lambda x:(x["entry_t"],x["symbol"])):
        if t["entry_t"]<=active.get(t["symbol"],-1):continue
        out.append(t);active[t["symbol"]]=t["exit_t"]
    return out

def spy_ctx(spyD,spyDc,t,direction):
    di=bisect.bisect_right(spyDc,t)-1
    if di<55:return {"daily_align":False,"slope_align":False}
    x=spyD[di];A=x.get("atr")
    if not A:return {"daily_align":False,"slope_align":False}
    sign=1 if direction=="LONG" else -1
    daily=(x["c"]>x["ema50"] and x["ema20"]>x["ema50"]) if direction=="LONG" else (x["c"]<x["ema50"] and x["ema20"]<x["ema50"])
    slope=sign*(x["ema50"]-spyD[di-5]["ema50"])/A>=0
    return {"daily_align":daily,"slope_align":slope}

def metrics(ts):
    if not ts:return {"n":0,"win_rate":None,"net_r":0.0,"avg_r":None,"pf":None,"mdd_r":0.0,"max_ls":0}
    o=sorted(ts,key=lambda x:(x["exit_t"],x["symbol"]))
    rs=[x["r"] for x in o];pos=[r for r in rs if r>0];neg=[r for r in rs if r<0]
    eq=peak=mdd=0;cur=mx=0
    for r in rs:
        eq+=r;peak=max(peak,eq);mdd=max(mdd,peak-eq)
        if r<0:cur+=1;mx=max(mx,cur)
        else:cur=0
    return {"n":len(rs),"win_rate":len(pos)/len(rs),"net_r":sum(rs),"avg_r":sum(rs)/len(rs),
            "pf":sum(pos)/abs(sum(neg)) if neg else None,"mdd_r":mdd,"max_ls":mx}

def summarize(ts):
    by=defaultdict(list);yr=defaultdict(list)
    for t in ts:
        by[t["symbol"]].append(t);yr[str(datetime.fromtimestamp(t["entry_t"]/1000,NY).year)].append(t)
    return {"overall":metrics(ts),"positive_symbols":sum(metrics(v)["net_r"]>0 for v in by.values()),
            "active_symbols":len(by),"symbols":{s:metrics(by.get(s,[])) for s in SYMS},
            "years":{k:metrics(v) for k,v in sorted(yr.items())}}

def main():
    con=duckdb.connect()
    data={s:load15(con,s) for s in SYMS}
    con.close()
    spyD=aggregate_daily(data["SPY"]);spyDc=[x["ct"] for x in spyD]
    trades=[]
    for sym in SYMS:
        M=data[sym];H=aggregate_1h_rth(M);D=aggregate_daily(M);Dc=[x["ct"] for x in D]
        W=aggregate_weekly(D);MN=aggregate_monthly(D)
        rows=[]
        for i in range(SWEEP_LOOKBACK,len(H)-DISP_MAX_BARS):
            if H[i]["ct"]<ms(EVAL_START) or H[i]["ct"]>=ms(EVAL_END):continue
            s=find_setup(H,D,Dc,i)
            if not s:continue
            ei=locate_entry(M,s)
            if ei is None:continue
            strong=htf_strong(W,MN,s["signal_t"],s["direction"])
            t=simulate(M,ei,s,3.0 if strong else 2.0,sym)
            t["htf_strong"]=strong;t["spy"]=spy_ctx(spyD,spyDc,t["signal_t"],t["direction"])
            rows.append(t)
        rows=suppress(rows);trades+=rows
        print("SYM",sym,len(rows),flush=True)
    trades=suppress(trades)

    variants={
      "base":trades,
      "spy_daily_align":[t for t in trades if t["spy"]["daily_align"]],
      "spy_daily_slope":[t for t in trades if t["spy"]["daily_align"] and t["spy"]["slope_align"]],
    }
    out={"version":"0.1","strategy":"EasyChart A adapted to US stocks RTH",
         "period":{"start":EVAL_START.isoformat(),"end_exclusive":EVAL_END.isoformat(),"holdout_start":HOLDOUT_START.isoformat()},
         "fixed_from_crypto":{"gap_min_atr":GAP_MIN,"ema50_slope5_min_atr":SLOPE50_MIN,"normal_tp_r":2.0,"htf_tp_r":3.0},
         "stock_adaptations":["RTH only 09:30-16:00 ET","1H bars anchored at 09:30 ET; incomplete 15:30-16:00 half-hour excluded from signal generation",
                              "daily/weekly/monthly built from RTH","sweep and displacement must complete in same session",
                              "entry is first 15m RTH bar with low<=entry<=high","same-bar STOP before TP","6 bps per side","48 RTH hours max hold"],
         "variants":{}}
    for k,ts in variants.items():
        train=[t for t in ts if t["entry_t"]<ms(HOLDOUT_START)]
        hold=[t for t in ts if t["entry_t"]>=ms(HOLDOUT_START)]
        out["variants"][k]={"overall":summarize(ts),"train":summarize(train),"holdout":summarize(hold)}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,indent=2),encoding="utf-8")
    print("FINAL",json.dumps({k:{"overall":v["overall"]["overall"],"train":v["train"]["overall"],"holdout":v["holdout"]["overall"]} for k,v in out["variants"].items()},indent=2),flush=True)

if __name__=="__main__":main()
