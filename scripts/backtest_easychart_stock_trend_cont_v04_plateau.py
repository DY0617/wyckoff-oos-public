import bisect, json, statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import duckdb

DATA=Path("data/cache/stock53_recent5y_15m.parquet")
OUT=Path("data/validation/easychart_stock_trend_cont_v04_plateau.json")
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

def build_symbol(sym,M,D,spyD,spy_date_to_i,lookback=20,pullback_days=5,reclaim_buffer=.10,tp_r=2.0):
    day_to_bars=defaultdict(list)
    for i,x in enumerate(M):day_to_bars[x["date"]].append(i)
    date_to_di={x["date"]:i for i,x in enumerate(D)}
    trades=[]
    active_until=-1

    for bi in range(max(50,lookback),len(D)-pullback_days-1):
        b=D[bi]
        if b["ct"]<ms(EVAL_START) or b["ct"]>=ms(EVAL_END):continue
        A=b.get("atr")
        if not A or not b.get("vol_sma20"):continue

        prev=D[bi-lookback:bi]
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
        for pj in range(bi+1,min(len(D),bi+1+pullback_days)):
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
                    reclaim=z["c"]>=level+reclaim_buffer*PA and z["c"]>z["o"]
                else:
                    reclaim=z["c"]<=level-reclaim_buffer*PA and z["c"]<z["o"]
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
        t=simulate(M,entry_i,entry,stop,risk,direction,sym,tp_r)
        t.update({"break_date":str(b["date"]),"pullback_date":str(pdate),"break_level":level,
                  "market_align":market_align,"rs20":rs20,"rs_align":rs_align,
                  "break_vol_ratio":(b["v"]/b["vol_sma20"] if b.get("vol_sma20") else None),
                  "vol_exp":vol_exp})
        trades.append(t);active_until=t["exit_t"]
    return trades

def simulate(M,entry_i,entry,stop,risk,direction,sym,tp_r=2.0):
    sign=1 if direction=="LONG" else -1
    target=entry+sign*tp_r*risk
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

def score_train(ts):
    tr,_=split(ts);m=metrics(tr)
    if m["n"]<300 or m["avg_r"] is None or m["avg_r"]<=0 or (m["pf"] or 0)<1.10:
        return -1e9
    return m["net_r"] - 0.25*m["mdd_r"]

def main():
    con=duckdb.connect()
    data={s:load15(con,s) for s in SYMS}
    con.close()
    daily={s:daily_from_15m(data[s]) for s in SYMS}
    spyD=daily["SPY"];spy_date_to_i={x["date"]:i for i,x in enumerate(spyD)}

    structural=[
      ("L15_P5_R10_T2",15,5,.10,2.0),
      ("L20_P5_R10_T2",20,5,.10,2.0),
      ("L25_P5_R10_T2",25,5,.10,2.0),
      ("L30_P5_R10_T2",30,5,.10,2.0),
      ("L20_P3_R10_T2",20,3,.10,2.0),
      ("L20_P7_R10_T2",20,7,.10,2.0),
      ("L20_P5_R05_T2",20,5,.05,2.0),
      ("L20_P5_R15_T2",20,5,.15,2.0),
      ("L20_P5_R10_T15",20,5,.10,1.5),
      ("L20_P5_R10_T25",20,5,.10,2.5),
    ]
    outvars={}
    for name,lb,pb,rb,tp in structural:
        rows=[]
        for s in SYMS:
            rows+=build_symbol(s,data[s],daily[s],spyD,spy_date_to_i,lb,pb,rb,tp)
        for vm in (1.10,1.20,1.30):
            key=f"{name}_V{int(vm*100)}"
            ts=[t for t in rows if t.get("break_vol_ratio") is not None and t["break_vol_ratio"]>=vm]
            tr,ho=split(ts)
            outvars[key]={
              "params":{"lookback":lb,"pullback_days":pb,"reclaim_buffer_atr":rb,"tp_r":tp,"volume_mult":vm},
              "score_train_only":score_train(ts),
              "overall":summarize(ts),"train":summarize(tr),"holdout":summarize(ho)
            }
        print("STRUCT",name,len(rows),flush=True)

    ranking=sorted(outvars,key=lambda k:outvars[k]["score_train_only"],reverse=True)
    out={"version":"0.4","strategy":"stock trend continuation robustness plateau",
         "selection_note":"ranked only on 2021-04 to 2024-04 train; holdout never used for ranking",
         "ranking":ranking,"selected_by_train":ranking[0],"variants":outvars}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2),encoding="utf-8")
    top=ranking[:10]
    print("FINAL",json.dumps({k:{
      "params":outvars[k]["params"],
      "score":outvars[k]["score_train_only"],
      "overall":outvars[k]["overall"]["overall"],
      "train":outvars[k]["train"]["overall"],
      "holdout":outvars[k]["holdout"]["overall"]
    } for k in top},indent=2),flush=True)

if __name__=="__main__":main()
