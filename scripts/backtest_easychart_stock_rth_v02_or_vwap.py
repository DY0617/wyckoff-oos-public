import bisect, json, statistics
from collections import defaultdict
from datetime import datetime, timezone, time
from pathlib import Path
from zoneinfo import ZoneInfo
import duckdb

DATA=Path("data/cache/stock53_recent5y_15m.parquet")
OUT=Path("data/validation/easychart_stock_rth_v02_or_vwap.json")
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

ATR_N=14
VOL_N=20
OR_BARS=2
SWEEP_MIN_ATR=.05
SWEEP_MAX_ATR=1.50
DISP_MAX_BARS=4
DISP_BODY_ATR=.60
DISP_CLV=.70
FVG_MIN_ATR=.08
RETEST_BARS=6
STOP_BUFFER_ATR=.15
COST_BPS_SIDE=6.0
RISK_DOLLARS=400.0
TP_R=2.0

def ts_ms(dt):
    if dt.tzinfo is None: dt=dt.replace(tzinfo=NY)
    return int(dt.timestamp()*1000)

def ema(vals,n):
    out=[];e=None;k=2/(n+1)
    for x in vals:
        e=x if e is None else e+k*(x-e);out.append(e)
    return out

def load15(con,sym):
    rows=con.execute("SELECT b,o,h,l,c,v FROM read_parquet(?) WHERE symbol=? ORDER BY b",[str(DATA),sym]).fetchall()
    out=[]
    for dt,o,h,l,c,v in rows:
        if dt.tzinfo is None: dt=dt.replace(tzinfo=NY)
        else: dt=dt.astimezone(NY)
        out.append({"t":ts_ms(dt),"dt":dt,"date":dt.date(),"o":float(o),"h":float(h),"l":float(l),"c":float(c),"v":float(v or 0)})
    return out

def enrich15(M):
    tr=[];a=None
    vols=[x["v"] for x in M]
    for i,x in enumerate(M):
        pc=M[i-1]["c"] if i else x["c"]
        tv=max(x["h"]-x["l"],abs(x["h"]-pc),abs(x["l"]-pc));tr.append(tv)
        if i<ATR_N-1:x["atr"]=None
        elif i==ATR_N-1:
            a=sum(tr[:ATR_N])/ATR_N;x["atr"]=a
        else:
            a=((ATR_N-1)*a+tv)/ATR_N;x["atr"]=a
        x["vol_sma20"]=statistics.fmean(vols[i-VOL_N+1:i+1]) if i>=VOL_N-1 else None
    # session VWAP using typical price
    by=defaultdict(list)
    for i,x in enumerate(M):by[x["date"]].append(i)
    for d,idxs in by.items():
        pv=vv=0.0
        for i in idxs:
            x=M[i];tp=(x["h"]+x["l"]+x["c"])/3.0
            pv+=tp*x["v"];vv+=x["v"];x["vwap"]=pv/vv if vv>0 else x["c"]
    return M

def build_daily(M):
    by=defaultdict(list)
    for x in M:by[x["date"]].append(x)
    out=[]
    for d in sorted(by):
        xs=by[d]
        # complete US equity RTH day = 26 x 15m bars
        if len(xs)!=26:continue
        out.append({"date":d,"t":xs[0]["t"],"ct":xs[-1]["t"]+15*60*1000-1,
                    "o":xs[0]["o"],"h":max(z["h"] for z in xs),"l":min(z["l"] for z in xs),
                    "c":xs[-1]["c"],"v":sum(z["v"] for z in xs)})
    for n in (20,50):
        e=ema([x["c"] for x in out],n)
        for i,x in enumerate(out):x[f"ema{n}"]=e[i]
    return out

def prior_daily_ctx(D,Dclose,t,direction):
    di=bisect.bisect_right(Dclose,t)-1
    if di<50:return {"trend":False,"slope":False}
    x=D[di]
    if direction=="LONG":
        trend=x["c"]>x["ema20"]>x["ema50"]
        slope=x["ema20"]>D[di-5]["ema20"]
    else:
        trend=x["c"]<x["ema20"]<x["ema50"]
        slope=x["ema20"]<D[di-5]["ema20"]
    return {"trend":trend,"slope":slope}

def clv(x):
    r=x["h"]-x["l"]
    return (x["c"]-x["l"])/r if r else .5

def body(x):return abs(x["c"]-x["o"])

def find_day_setups(sym,M,D,Dclose,spy_by_date):
    by=defaultdict(list)
    for i,x in enumerate(M):by[x["date"]].append(i)
    trades=[]
    for d in sorted(by):
        idxs=by[d]
        if len(idxs)!=26:continue
        if not (EVAL_START.date()<=d<EVAL_END.date()):continue
        day=[M[i] for i in idxs]
        orh=max(x["h"] for x in day[:OR_BARS]);orl=min(x["l"] for x in day[:OR_BARS])
        # signal window 10:00 through 14:30; leave room for displacement/retest/exit
        chosen=None
        for li in range(OR_BARS,21):
            s=day[li];A=s.get("atr")
            if not A or not s.get("vwap"):continue
            long_sweep=s["l"]<orl-SWEEP_MIN_ATR*A and s["c"]>orl and (orl-s["l"])<=SWEEP_MAX_ATR*A
            short_sweep=s["h"]>orh+SWEEP_MIN_ATR*A and s["c"]<orh and (s["h"]-orh)<=SWEEP_MAX_ATR*A
            for direction,ok in (("LONG",long_sweep),("SHORT",short_sweep)):
                if not ok:continue
                for dj in range(1,DISP_MAX_BARS+1):
                    j=li+dj
                    if j>=23 or j<2:break
                    q=day[j];qa=q.get("atr")
                    if not qa:continue
                    strong=body(q)>=DISP_BODY_ATR*qa
                    vol_exp=bool(q.get("vol_sma20") and q["v"]>=1.10*q["vol_sma20"])
                    if direction=="LONG":
                        directional=q["c"]>q["o"] and clv(q)>=DISP_CLV and q["c"]>s["h"]
                        vwap_ok=q["c"]>q["vwap"]
                        f_lo=day[j-2]["h"];f_hi=q["l"]
                    else:
                        directional=q["c"]<q["o"] and clv(q)<=1-DISP_CLV and q["c"]<s["l"]
                        vwap_ok=q["c"]<q["vwap"]
                        f_lo=q["h"];f_hi=day[j-2]["l"]
                    gap=f_hi-f_lo
                    fvg=gap>=FVG_MIN_ATR*qa
                    if not(strong and directional and vwap_ok and fvg):continue
                    entry=(f_lo+f_hi)/2
                    stop=s["l"]-STOP_BUFFER_ATR*A if direction=="LONG" else s["h"]+STOP_BUFFER_ATR*A
                    risk=abs(entry-stop)
                    if risk<=0 or risk<.20*qa or risk>3.5*qa:continue
                    # first retest after displacement bar, same day
                    ei=None
                    for k in range(j+1,min(26,j+1+RETEST_BARS)):
                        z=day[k]
                        if z["l"]<=entry<=z["h"]:
                            ei=k;break
                    if ei is None:continue
                    daily=prior_daily_ctx(D,Dclose,s["t"]-1,direction)
                    spy=spy_by_date.get(d,{"long":False,"short":False})
                    spy_align=spy["long"] if direction=="LONG" else spy["short"]
                    chosen={"symbol":sym,"date":str(d),"direction":direction,"entry":entry,"stop":stop,"risk":risk,
                            "entry_li":ei,"sweep_li":li,"disp_li":j,"daily":daily,"spy_align":spy_align,
                            "vol_exp":vol_exp,"orh":orh,"orl":orl}
                    break
                if chosen:break
            if chosen:break
        if chosen:
            trades.append(sim_day(day,chosen))
    return trades

def sim_day(day,s):
    sign=1 if s["direction"]=="LONG" else -1
    entry=s["entry"];stop=s["stop"];risk=s["risk"];target=entry+sign*TP_R*risk
    size=RISK_DOLLARS/risk;cr=COST_BPS_SIDE/10000.0
    pnl=-size*entry*cr;reason="EOD";exit_t=day[s["entry_li"]]["t"];last=day[s["entry_li"]]
    # conservative: same 15m entry bar can stop before target
    for k in range(s["entry_li"],26):
        z=day[k];last=z
        hit_stop=z["l"]<=stop if sign==1 else z["h"]>=stop
        if hit_stop:
            pnl+=size*sign*(stop-entry)-size*stop*cr;reason="STOP";exit_t=z["t"];break
        hit_tp=z["h"]>=target if sign==1 else z["l"]<=target
        if hit_tp:
            pnl+=size*sign*(target-entry)-size*target*cr;reason="TP";exit_t=z["t"];break
    else:
        px=last["c"];pnl+=size*sign*(px-entry)-size*px*cr;exit_t=last["t"]
    q=dict(s);q.update({"entry_t":day[s["entry_li"]]["t"],"exit_t":exit_t,"target":target,"r":pnl/RISK_DOLLARS,"reason":reason})
    return q

def metrics(ts):
    if not ts:return {"n":0,"win_rate":None,"net_r":0.0,"avg_r":None,"pf":None,"mdd_r":0.0,"max_ls":0}
    o=sorted(ts,key=lambda x:(x["exit_t"],x["symbol"]))
    rs=[x["r"] for x in o];pos=[r for r in rs if r>0];neg=[r for r in rs if r<0]
    eq=peak=mdd=0.0;cur=mx=0
    for r in rs:
        eq+=r;peak=max(peak,eq);mdd=max(mdd,peak-eq)
        if r<0:cur+=1;mx=max(mx,cur)
        else:cur=0
    return {"n":len(rs),"win_rate":len(pos)/len(rs),"net_r":sum(rs),"avg_r":sum(rs)/len(rs),
            "pf":sum(pos)/abs(sum(neg)) if neg else None,"mdd_r":mdd,"max_ls":mx}

def summarize(ts):
    by=defaultdict(list);yr=defaultdict(list)
    for t in ts:
        by[t["symbol"]].append(t);yr[t["date"][:4]].append(t)
    return {"overall":metrics(ts),"positive_symbols":sum(metrics(v)["net_r"]>0 for v in by.values()),
            "active_symbols":len(by),"symbols":{s:metrics(by.get(s,[])) for s in SYMS},
            "years":{y:metrics(v) for y,v in sorted(yr.items())}}

def split(ts):
    cut=ts_ms(HOLDOUT_START)
    return [t for t in ts if t["entry_t"]<cut],[t for t in ts if t["entry_t"]>=cut]

def main():
    con=duckdb.connect()
    data={s:enrich15(load15(con,s)) for s in SYMS}
    con.close()
    spy=data["SPY"]
    spy_by=defaultdict(dict)
    spy_days=defaultdict(list)
    for x in spy:spy_days[x["date"]].append(x)
    for d,xs in spy_days.items():
        if len(xs)!=26:continue
        # use information available by 10:00: first 30m close vs opening-range midpoint and session vwap
        orh=max(z["h"] for z in xs[:2]);orl=min(z["l"] for z in xs[:2]);mid=(orh+orl)/2
        c=xs[1]["c"];vw=xs[1]["vwap"]
        spy_by[d]={"long":c>mid and c>vw,"short":c<mid and c<vw}

    alltr=[]
    for s in SYMS:
        D=build_daily(data[s]);Dc=[x["ct"] for x in D]
        tr=find_day_setups(s,data[s],D,Dc,spy_by)
        alltr+=tr
        print("SYM",s,len(tr),flush=True)

    variants={
      "raw":alltr,
      "daily_trend":[t for t in alltr if t["daily"]["trend"]],
      "daily_trend_slope":[t for t in alltr if t["daily"]["trend"] and t["daily"]["slope"]],
      "spy_align":[t for t in alltr if t["spy_align"]],
      "daily_plus_spy":[t for t in alltr if t["daily"]["trend"] and t["spy_align"]],
      "daily_spy_vol":[t for t in alltr if t["daily"]["trend"] and t["spy_align"] and t["vol_exp"]],
    }

    out={"version":"0.2","strategy":"US stock RTH Opening-Range liquidity sweep + VWAP + displacement + FVG",
         "period":{"start":EVAL_START.isoformat(),"end_exclusive":EVAL_END.isoformat(),"holdout_start":HOLDOUT_START.isoformat()},
         "rules":{
           "opening_range":"09:30-10:00 ET first two 15m bars",
           "sweep":"after 10:00, sweep OR high/low by 0.05-1.50 ATR then close back inside",
           "displacement":"within next 1-4 bars, body>=0.60 ATR, CLV>=0.70, close through sweep candle extreme",
           "vwap":"displacement close must be on trade side of session VWAP",
           "fvg":"classic 3-bar 15m FVG >=0.08 ATR; entry at midpoint first retest within 6 bars",
           "entry_fill":"15m low<=entry<=high",
           "stop":"beyond sweep extreme +0.15 ATR",
           "exit":"2R target or stop; otherwise flatten at 16:00 ET",
           "ambiguity":"STOP before TP on same 15m candle",
           "cost":"6 bps per side"
         },
         "variants":{}}
    for k,ts in variants.items():
        tr,ho=split(ts)
        out["variants"][k]={"overall":summarize(ts),"train":summarize(tr),"holdout":summarize(ho)}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2),encoding="utf-8")
    print("FINAL",json.dumps({k:{"overall":v["overall"]["overall"],"train":v["train"]["overall"],"holdout":v["holdout"]["overall"]} for k,v in out["variants"].items()},indent=2),flush=True)

if __name__=="__main__":main()
