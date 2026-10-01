import bisect, json, statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import duckdb

DATA=Path("data/cache/stock53_recent5y_15m.parquet")
OUT=Path("data/validation/easychart_stock_trend_cont_v03.json")
NY=ZoneInfo("America/New_York")

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

BREAK_LOOKBACK=20
PULLBACK_DAYS=5
RECLAIM_BUFFER_ATR=0.10
PULLBACK_TOL_ATR=0.50
STOP_BUFFER_ATR=0.20
TP_R=2.0
MAX_HOLD_DAYS=10
COST_BPS_SIDE=6.0
RISK_DOLLARS=400.0

def ms(dt):
    if dt.tzinfo is None:dt=dt.replace(tzinfo=NY)
    return int(dt.timestamp()*1000)

def ema(vals,n):
    out=[];e=None;k=2/(n+1)
    for x in vals:
        e=x if e is None else e+k*(x-e);out.append(e)
    return out

def enrich_daily(D):
    if not D:return D
    tr=[];a=None
    for i,x in enumerate(D):
        pc=D[i-1]["c"] if i else x["c"]
        tv=max(x["h"]-x["l"],abs(x["h"]-pc),abs(x["l"]-pc));tr.append(tv)
        if i<13:x["atr"]=None
        elif i==13:
            a=sum(tr[:14])/14;x["atr"]=a
        else:
            a=(13*a+tv)/14;x["atr"]=a
    for n in (20,50):
        e=ema([x["c"] for x in D],n)
        for i,x in enumerate(D):x[f"ema{n}"]=e[i]
    vols=[x["v"] for x in D]
    for i,x in enumerate(D):
        x["vol_sma20"]=statistics.fmean(vols[i-19:i+1]) if i>=19 else None
    return D

def load15(con,sym):
    rows=con.execute("SELECT b,o,h,l,c,v FROM read_parquet(?) WHERE symbol=? ORDER BY b",[str(DATA),sym]).fetchall()
    out=[]
    for dt,o,h,l,c,v in rows:
        if dt.tzinfo is None:dt=dt.replace(tzinfo=NY)
        else:dt=dt.astimezone(NY)
        out.append({"t":ms(dt),"dt":dt,"date":dt.date(),"o":float(o),"h":float(h),"l":float(l),"c":float(c),"v":float(v or 0)})
    return out

def daily_from_15m(M):
    by=defaultdict(list)
    for x in M:by[x["date"]].append(x)
    out=[]
    for d in sorted(by):
        xs=by[d]
        if len(xs)!=26:continue
        out.append({"date":d,"t":xs[0]["t"],"ct":xs[-1]["t"]+15*60*1000-1,
                    "o":xs[0]["o"],"h":max(z["h"] for z in xs),"l":min(z["l"] for z in xs),
                    "c":xs[-1]["c"],"v":sum(z["v"] for z in xs)})
    return enrich_daily(out)

def ret(D,i,n=20):
    if i<n or D[i-n]["c"]<=0:return None
    return D[i]["c"]/D[i-n]["c"]-1

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
        by[t["symbol"]].append(t);yr[str(datetime.fromtimestamp(t["entry_t"]/1000,NY).year)].append(t)
    return {"overall":metrics(ts),
            "positive_symbols":sum(metrics(v)["net_r"]>0 for v in by.values()),
            "active_symbols":len(by),
            "symbols":{s:metrics(by.get(s,[])) for s in SYMS},
            "years":{k:metrics(v) for k,v in sorted(yr.items())}}

def split(ts):
    cut=ms(HOLDOUT_START)
    return [t for t in ts if t["entry_t"]<cut],[t for t in ts if t["entry_t"]>=cut]

def market_ctx(spyD,spy_idx):
    if spy_idx<50:return {"bull":False,"bear":False}
    x=spyD[spy_idx]
    return {
      "bull":x["c"]>x["ema20"]>x["ema50"],
      "bear":x["c"]<x["ema20"]<x["ema50"],
    }

def build_symbol(sym,M,D,spyD,spy_date_to_i):
    day_to_bars=defaultdict(list)
    for i,x in enumerate(M):day_to_bars[x["date"]].append(i)
    date_to_di={x["date"]:i for i,x in enumerate(D)}
    trades=[]
    active_until=-1

    for bi in range(max(50,BREAK_LOOKBACK),len(D)-PULLBACK_DAYS-1):
        b=D[bi]
        if b["ct"]<ms(EVAL_START) or b["ct"]>=ms(EVAL_END):continue
        A=b.get("atr")
        if not A or not b.get("vol_sma20"):continue

        prev=D[bi-BREAK_LOOKBACK:bi]
        ph=max(x["h"] for x in prev)
        pl=min(x["l"] for x in prev)
        long_break=b["c"]>ph and b["c"]>b["ema20"]>b["ema50"]
        short_break=b["c"]<pl and b["c"]<b["ema20"]<b["ema50"]
        if not(long_break or short_break):continue

        direction="LONG" if long_break else "SHORT"
        level=ph if long_break else pl
        vol_exp=b["v"]>=1.20*b["vol_sma20"]

        sdi=spy_date_to_i.get(b["date"])
        if sdi is None:continue
        mkt=market_ctx(spyD,sdi)
        market_align=mkt["bull"] if direction=="LONG" else mkt["bear"]

        rr=ret(D,bi,20); sr=ret(spyD,sdi,20)
        rs20=(rr-sr) if rr is not None and sr is not None else None
        rs_align=(rs20 is not None and ((direction=="LONG" and rs20>0) or (direction=="SHORT" and rs20<0)))

        # Search first pullback/reclaim in next 1..5 complete sessions.
        found=None
        for pj in range(bi+1,min(len(D),bi+1+PULLBACK_DAYS)):
            pd=D[pj];PA=pd.get("atr") or A
            if direction=="LONG":
                pull=pd["l"]<=level+PULLBACK_TOL_ATR*PA and pd["c"]>=level-0.25*PA
            else:
                pull=pd["h"]>=level-PULLBACK_TOL_ATR*PA and pd["c"]<=level+0.25*PA
            if not pull:continue

            idxs=day_to_bars.get(pd["date"],[])
            if len(idxs)!=26:continue
            # 15m reclaim trigger. Use only bars after first 30m to reduce opening noise.
            local=[M[i] for i in idxs]
            start=2
            for li in range(start,25):
                z=local[li]
                if direction=="LONG":
                    reclaim=z["c"]>=level+RECLAIM_BUFFER_ATR*PA and z["c"]>z["o"]
                else:
                    reclaim=z["c"]<=level-RECLAIM_BUFFER_ATR*PA and z["c"]<z["o"]
                if not reclaim:continue
                entry_i=idxs[li+1] if li+1<len(idxs) else None
                if entry_i is None:break
                entry=M[entry_i]["o"]
                if direction=="LONG":
                    stop=min(pd["l"],level-0.50*PA)-STOP_BUFFER_ATR*PA
                    if entry<=stop:break
                else:
                    stop=max(pd["h"],level+0.50*PA)+STOP_BUFFER_ATR*PA
                    if entry>=stop:break
                risk=abs(entry-stop)
                if risk<0.25*PA or risk>4.0*PA:break
                found=(entry_i,entry,stop,risk,pd["date"],li,PA)
                break
            if found:break

        if not found:continue
        entry_i,entry,stop,risk,pdate,li,PA=found
        if M[entry_i]["t"]<=active_until:continue
        t=simulate(M,entry_i,entry,stop,risk,direction,sym)
        t.update({"break_date":str(b["date"]),"pullback_date":str(pdate),"break_level":level,
                  "market_align":market_align,"rs20":rs20,"rs_align":rs_align,"vol_exp":vol_exp})
        trades.append(t);active_until=t["exit_t"]
    return trades

def simulate(M,entry_i,entry,stop,risk,direction,sym):
    sign=1 if direction=="LONG" else -1
    target=entry+sign*TP_R*risk
    size=RISK_DOLLARS/risk;cr=COST_BPS_SIDE/10000.0
    pnl=-size*entry*cr;reason="TIME";last=M[entry_i];exit_t=M[entry_i]["t"]
    entry_date=M[entry_i]["date"]
    # up to MAX_HOLD_DAYS RTH sessions
    seen_dates=[]
    for k in range(entry_i,len(M)):
        z=M[k]
        if z["date"] not in seen_dates:seen_dates.append(z["date"])
        if len(seen_dates)>MAX_HOLD_DAYS:break
        last=z
        hit_stop=z["l"]<=stop if direction=="LONG" else z["h"]>=stop
        if hit_stop:
            pnl+=size*sign*(stop-entry)-size*stop*cr;reason="STOP";exit_t=z["t"];break
        hit_tp=z["h"]>=target if direction=="LONG" else z["l"]<=target
        if hit_tp:
            pnl+=size*sign*(target-entry)-size*target*cr;reason="TP";exit_t=z["t"];break
        exit_t=z["t"]
    if reason=="TIME":
        px=last["c"];pnl+=size*sign*(px-entry)-size*px*cr
    return {"symbol":sym,"direction":direction,"entry_t":M[entry_i]["t"],"exit_t":exit_t,
            "entry":entry,"stop":stop,"target":target,"risk":risk,"r":pnl/RISK_DOLLARS,"reason":reason}

def main():
    con=duckdb.connect()
    data={s:load15(con,s) for s in SYMS}
    con.close()
    daily={s:daily_from_15m(data[s]) for s in SYMS}
    spyD=daily["SPY"];spy_date_to_i={x["date"]:i for i,x in enumerate(spyD)}

    alltr=[]
    for s in SYMS:
        tr=build_symbol(s,data[s],daily[s],spyD,spy_date_to_i)
        alltr+=tr
        print("SYM",s,len(tr),flush=True)

    variants={
      "raw":alltr,
      "market_align":[t for t in alltr if t["market_align"]],
      "rs_align":[t for t in alltr if t["rs_align"]],
      "volume_breakout":[t for t in alltr if t["vol_exp"]],
      "market_rs":[t for t in alltr if t["market_align"] and t["rs_align"]],
      "market_rs_volume":[t for t in alltr if t["market_align"] and t["rs_align"] and t["vol_exp"]],
    }

    out={"version":"0.3","strategy":"US stock trend continuation: market regime + relative strength + breakout + first pullback",
         "period":{"start":EVAL_START.isoformat(),"end_exclusive":EVAL_END.isoformat(),"holdout_start":HOLDOUT_START.isoformat()},
         "rules":{
           "breakout":"completed RTH daily close beyond prior 20-session high/low and EMA20/50 aligned",
           "market_regime":"SPY completed daily EMA20/EMA50 alignment in trade direction",
           "relative_strength":"20-session return minus SPY 20-session return, sign aligned with trade direction",
           "volume":"breakout-day volume >=1.20x 20-session average",
           "pullback":"within next 5 sessions, revisit breakout level within 0.50 ATR without losing it by >0.25 ATR close",
           "trigger":"after first 30m, 15m close reclaims breakout level by 0.10 ATR; enter next 15m open",
           "stop":"pullback session extreme / breakout level structural stop +0.20 ATR buffer",
           "target":"2R fixed",
           "max_hold":"10 RTH sessions",
           "execution":"15m OHLC, same-bar STOP before TP, 6 bps/side"
         },
         "variants":{}}
    for k,ts in variants.items():
        tr,ho=split(ts)
        out["variants"][k]={"overall":summarize(ts),"train":summarize(tr),"holdout":summarize(ho)}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2),encoding="utf-8")
    print("FINAL",json.dumps({k:{"overall":v["overall"]["overall"],"train":v["train"]["overall"],"holdout":v["holdout"]["overall"]} for k,v in out["variants"].items()},indent=2),flush=True)

if __name__=="__main__":main()
