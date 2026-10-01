import bisect, calendar, json, math, statistics
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

import backtest_smc_liq_fvg_v01 as smc
import backtest_trend_structure_v0_1_crypto as core

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/validation/easychart_synthesis_v01_crypto8.json"
UTC = timezone.utc
SYMS = ("BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","LINKUSDT")
TRAIN_END = int(datetime(2025,1,1,tzinfo=UTC).timestamp()*1000)

BASE_CFG = dict(smc.DEFAULTS)
BASE_CFG.update({
    "signal_minutes": 60,
    "trend_mode": "price_ema50",
    "tp_r": 2.0,
    "disp_body_atr": 0.80,
    "fvg_entry_depth": 0.50,
})

BREAK_CFG = {
    "lookback": 20,
    "break_buffer_atr": 0.10,
    "body_atr": 0.65,
    "clv": 0.75,
    "vol_mult": 1.10,
    "retest_bars": 8,
    "retest_tol_atr": 0.25,
    "stop_buffer_atr": 0.15,
    "risk_min_atr": 0.40,
    "risk_max_atr": 3.50,
    "normal_tp_r": 2.0,
    "strong_tp_r": 3.0,
    "cost_bps_per_side": 6.0,
    "max_hold_hours": 48,
    "reg_window": 80,
    "reg_k": 1.5,
    "reg_slope_atr_min": 0.01,
}

def ema(vals,n):
    out=[]; e=None; k=2.0/(n+1.0)
    for x in vals:
        e=x if e is None else e+k*(x-e)
        out.append(e)
    return out

def add_volume(H):
    vols=[x["v"] for x in H]
    for i,x in enumerate(H):
        x["vol_sma20"]=statistics.fmean(vols[i-19:i+1]) if i>=19 else None
    return H

def aggregate_weekly(D):
    g=defaultdict(list)
    for z in D:
        dt=datetime.fromtimestamp(z["t"]/1000,UTC)
        monday=(dt-timedelta(days=dt.weekday())).replace(hour=0,minute=0,second=0,microsecond=0)
        g[int(monday.timestamp()*1000)].append(z)
    out=[]
    for k in sorted(g):
        xs=g[k]
        days={datetime.fromtimestamp(x["t"]/1000,UTC).weekday() for x in xs}
        if len(days)<7: continue
        out.append({"t":k,"ct":k+7*smc.DAY-1,"o":xs[0]["o"],"h":max(x["h"] for x in xs),
                    "l":min(x["l"] for x in xs),"c":xs[-1]["c"],"v":sum(x["v"] for x in xs)})
    if out:
        e20=ema([x["c"] for x in out],20)
        for i,x in enumerate(out): x["ema20"]=e20[i]
    return out

def next_month_ms(y,m):
    return int(datetime(y+1,1,1,tzinfo=UTC).timestamp()*1000) if m==12 else int(datetime(y,m+1,1,tzinfo=UTC).timestamp()*1000)

def aggregate_monthly(D):
    g=defaultdict(list)
    for z in D:
        dt=datetime.fromtimestamp(z["t"]/1000,UTC)
        g[(dt.year,dt.month)].append(z)
    out=[]
    for (y,m) in sorted(g):
        xs=g[(y,m)]
        if len(xs)<calendar.monthrange(y,m)[1]: continue
        t=int(datetime(y,m,1,tzinfo=UTC).timestamp()*1000)
        out.append({"t":t,"ct":next_month_ms(y,m)-1,"o":xs[0]["o"],"h":max(x["h"] for x in xs),
                    "l":min(x["l"] for x in xs),"c":xs[-1]["c"],"v":sum(x["v"] for x in xs)})
    if out:
        e4=ema([x["c"] for x in out],4)
        e6=ema([x["c"] for x in out],6)
        for i,x in enumerate(out):
            x["ema4"]=e4[i]; x["ema6"]=e6[i]
    return out

def htf_context(W,M,t,direction):
    wc=[x["ct"] for x in W]; mc=[x["ct"] for x in M]
    wi=bisect.bisect_right(wc,t)-1; mi=bisect.bisect_right(mc,t)-1
    if wi<0 or mi<0:
        return {"w20":False,"m4":False,"m6":False,"strong":False}
    w=W[wi]; m=M[mi]
    if direction=="LONG":
        w20=w["c"]>w["ema20"]; m4=m["c"]>m["ema4"]; m6=m["c"]>m["ema6"]
    else:
        w20=w["c"]<w["ema20"]; m4=m["c"]<m["ema4"]; m6=m["c"]<m["ema6"]
    return {"w20":w20,"m4":m4,"m6":m6,"strong":w20 and m4}

def linreg(vals):
    n=len(vals)
    if n<2:return None
    xm=(n-1)/2.0; ym=statistics.fmean(vals)
    den=sum((i-xm)**2 for i in range(n))
    if den<=0:return None
    m=sum((i-xm)*(y-ym) for i,y in enumerate(vals))/den
    b=ym-m*xm
    resid=[y-(m*i+b) for i,y in enumerate(vals)]
    sd=math.sqrt(sum(r*r for r in resid)/n)
    return m,b,sd

def regression_channel(H,i,cfg):
    n=cfg["reg_window"]
    if i+1<n:return None
    xs=H[i-n+1:i+1]
    fit=linreg([z["c"] for z in xs])
    A=H[i].get("atr")
    if fit is None or not A or A<=0:return None
    m,b,sd=fit
    center=m*(n-1)+b
    return {"slope_atr":m/A,"center":center,"lower":center-cfg["reg_k"]*sd,"upper":center+cfg["reg_k"]*sd}

def clv(x):
    r=x["h"]-x["l"]
    return (x["c"]-x["l"])/r if r else 0.5

def body(x):
    return abs(x["c"]-x["o"])

def metrics(ts):
    if not ts:
        return {"n":0,"win_rate":None,"net_r":0.0,"avg_r":None,"pf":None,"mdd_r":0.0,"max_ls":0}
    o=sorted(ts,key=lambda z:(z["exit_t"],z["symbol"],z.get("track","")))
    rs=[t["r"] for t in o]
    pos=[r for r in rs if r>0]; neg=[r for r in rs if r<0]
    eq=peak=mdd=0.0; cur=mx=0
    for r in rs:
        eq+=r; peak=max(peak,eq); mdd=max(mdd,peak-eq)
        if r<0: cur+=1; mx=max(mx,cur)
        else: cur=0
    return {"n":len(rs),"win_rate":len(pos)/len(rs),"net_r":sum(rs),"avg_r":sum(rs)/len(rs),
            "pf":sum(pos)/abs(sum(neg)) if neg else None,"mdd_r":mdd,"max_ls":mx}

def split(ts):
    return [t for t in ts if t["entry_t"]<TRAIN_END],[t for t in ts if t["entry_t"]>=TRAIN_END]

def year_metrics(ts):
    d=defaultdict(list)
    for t in ts:
        d[str(datetime.fromtimestamp(t["entry_t"]/1000,UTC).year)].append(t)
    return {k:metrics(v) for k,v in sorted(d.items())}

def symbol_metrics(ts):
    d=defaultdict(list)
    for t in ts:d[t["symbol"]].append(t)
    return {s:metrics(d.get(s,[])) for s in SYMS}

def track_metrics(ts):
    d=defaultdict(list)
    for t in ts:d[t["track"]].append(t)
    return {k:metrics(v) for k,v in sorted(d.items())}

def loo(ts):
    return {s:metrics([t for t in ts if t["symbol"]!=s]) for s in SYMS}

def resim(M,t,target_r,cost_bps=6.0,max_hold=48):
    direction=t["direction"]; sign=1 if direction=="LONG" else -1
    entry=t["entry"]; stop=t["stop"]; risk=abs(entry-stop)
    if risk<=0:return None
    target=entry+sign*target_r*risk
    size=smc.RISK_DOLLARS/risk; cr=cost_bps/10000.0
    pnl=-size*entry*cr
    times=[x["t"] for x in M]; i=bisect.bisect_left(times,t["entry_t"])
    end=t["entry_t"]+max_hold*smc.HOUR
    last=M[i]; reason="TIME"; exit_t=last["t"]
    for j in range(i,len(M)):
        z=M[j]; last=z
        if z["t"]>=end: break
        hit_stop=z["l"]<=stop if direction=="LONG" else z["h"]>=stop
        if hit_stop:
            pnl+=size*sign*(stop-entry)-size*stop*cr; reason="STOP"; exit_t=z["t"]; break
        hit_tp=z["h"]>=target if direction=="LONG" else z["l"]<=target
        if hit_tp:
            pnl+=size*sign*(target-entry)-size*target*cr; reason="TP"; exit_t=z["t"]; break
    if reason=="TIME":
        px=last["c"]; pnl+=size*sign*(px-entry)-size*px*cr; exit_t=last["t"]
    q=dict(t); q["r"]=pnl/smc.RISK_DOLLARS; q["exit_t"]=exit_t; q["target_r"]=target_r; q["reason_synth"]=reason
    return q

def build_track_a(sym,M,W,MN):
    orig=smc.core.load_15m
    try:
        smc.core.load_15m=lambda s:M
        r=smc.run_symbol(sym,None,BASE_CFG)
    finally:
        smc.core.load_15m=orig
    out=[]
    H=add_volume(smc.aggregate_tf(M,60))
    htimes=[x["t"] for x in H]
    for t in r["fixed2r"]["trades"]:
        q=dict(t); q["symbol"]=sym; q["track"]="A_LIQ_FAKEOUT_FVG"
        q["htf"]=htf_context(W,MN,q["signal_t"],q["direction"])
        hi=bisect.bisect_right(htimes,q["sweep_t"])-1
        reg=regression_channel(H,hi,BREAK_CFG) if hi>=0 else None
        disp_i=bisect.bisect_right(htimes,q["disp_t"])-1
        vol_exp=False
        if disp_i>=0:
            vma=H[disp_i].get("vol_sma20")
            vol_exp=bool(vma and H[disp_i]["v"]>=1.20*vma)
        channel_fake=False
        if reg and hi>=0:
            sbar=H[hi]
            if q["direction"]=="LONG":
                channel_fake=sbar["l"]<reg["lower"] and sbar["c"]>reg["lower"]
            else:
                channel_fake=sbar["h"]>reg["upper"] and sbar["c"]<reg["upper"]
        q["quality"]={"htf":q["htf"]["strong"],"channel_fakeout":channel_fake,"vol_expansion":vol_exp,"ob_overlap":q.get("ob_overlap",False)}
        q["score"]=sum(bool(q["quality"][k]) for k in ("htf","channel_fakeout","vol_expansion"))
        tp=3.0 if q["htf"]["strong"] else 2.0
        q=resim(M,q,tp)
        out.append(q)
    return out

def breakout_candidates(sym,M,W,MN):
    H=add_volume(smc.aggregate_tf(M,60))
    D,Dclose=smc.prepare_daily(smc.aggregate_1d(M))
    out=[]
    for i in range(max(BREAK_CFG["lookback"],BREAK_CFG["reg_window"]),len(H)-BREAK_CFG["retest_bars"]-1):
        x=H[i]; A=x.get("atr"); vma=x.get("vol_sma20")
        if not A or not vma: continue
        sig_close=x["t"]+smc.HOUR-1
        if sig_close<int(core.EVAL_START.timestamp()*1000) or sig_close>=int(core.EVAL_END.timestamp()*1000): continue
        trend=smc.trend_at(D,Dclose,sig_close,"price_ema50")
        if trend is None: continue
        prev=H[i-BREAK_CFG["lookback"]:i]
        ph=max(z["h"] for z in prev); pl=min(z["l"] for z in prev)
        long_ok=(trend=="LONG" and x["c"]>ph+BREAK_CFG["break_buffer_atr"]*A and x["c"]>x["o"] and
                 body(x)>=BREAK_CFG["body_atr"]*A and clv(x)>=BREAK_CFG["clv"] and x["v"]>=BREAK_CFG["vol_mult"]*vma)
        short_ok=(trend=="SHORT" and x["c"]<pl-BREAK_CFG["break_buffer_atr"]*A and x["c"]<x["o"] and
                  body(x)>=BREAK_CFG["body_atr"]*A and clv(x)<=1-BREAK_CFG["clv"] and x["v"]>=BREAK_CFG["vol_mult"]*vma)
        if not (long_ok or short_ok): continue
        direction="LONG" if long_ok else "SHORT"; level=ph if long_ok else pl
        reg=regression_channel(H,i,BREAK_CFG)
        channel_align=bool(reg and ((direction=="LONG" and reg["slope_atr"]>=BREAK_CFG["reg_slope_atr_min"]) or
                                    (direction=="SHORT" and reg["slope_atr"]<=-BREAK_CFG["reg_slope_atr_min"])))
        for j in range(i+1,min(len(H),i+1+BREAK_CFG["retest_bars"])):
            z=H[j]; Aj=z.get("atr") or A
            if direction=="LONG":
                retest=z["l"]<=level+BREAK_CFG["retest_tol_atr"]*Aj and z["c"]>=level and z["c"]>z["o"]
                if not retest: continue
                entry=z["c"]; stop=min(z["l"],level-0.35*Aj)-BREAK_CFG["stop_buffer_atr"]*Aj
            else:
                retest=z["h"]>=level-BREAK_CFG["retest_tol_atr"]*Aj and z["c"]<=level and z["c"]<z["o"]
                if not retest: continue
                entry=z["c"]; stop=max(z["h"],level+0.35*Aj)+BREAK_CFG["stop_buffer_atr"]*Aj
            risk=abs(entry-stop)
            if risk<BREAK_CFG["risk_min_atr"]*Aj or risk>BREAK_CFG["risk_max_atr"]*Aj: break
            entry_t=z["t"]+smc.HOUR
            mi=bisect.bisect_left([b["t"] for b in M],entry_t)
            if mi>=len(M): break
            fill=M[mi]["o"]
            # gap/open slippage: reject pathological opens beyond stop
            if (direction=="LONG" and fill<=stop) or (direction=="SHORT" and fill>=stop): break
            q={"symbol":sym,"track":"B_BREAK_SRFLIP","direction":direction,"entry_t":M[mi]["t"],
               "signal_t":z["t"]+smc.HOUR-1,"entry":fill,"stop":stop,"break_level":level,
               "break_t":x["t"],"retest_t":z["t"],"ob_overlap":False}
            q["htf"]=htf_context(W,MN,q["signal_t"],direction)
            q["quality"]={"htf":q["htf"]["strong"],"channel_align":channel_align,"vol_expansion":True}
            q["score"]=sum(bool(v) for v in q["quality"].values())
            tp=BREAK_CFG["strong_tp_r"] if q["htf"]["strong"] else BREAK_CFG["normal_tp_r"]
            out.append(resim(M,q,tp,BREAK_CFG["cost_bps_per_side"],BREAK_CFG["max_hold_hours"]))
            break
    return suppress_symbol_overlap(out)

def suppress_symbol_overlap(ts):
    out=[]; active={}
    for t in sorted(ts,key=lambda z:(z["entry_t"],0 if z["track"].startswith("A_") else 1)):
        s=t["symbol"]
        if t["entry_t"]<=active.get(s,-1): continue
        out.append(t); active[s]=t["exit_t"]
    return out

def combine_tracks(a,b,require_b_channel=False,a_score_min=0):
    aa=[t for t in a if t.get("score",0)>=a_score_min]
    bb=[t for t in b if (not require_b_channel or t["quality"].get("channel_align"))]
    return suppress_symbol_overlap(aa+bb)

def summarize(ts):
    tr,ho=split(ts)
    return {"overall":metrics(ts),"train":metrics(tr),"holdout":metrics(ho),"years":year_metrics(ts),
            "symbols":symbol_metrics(ts),"tracks":track_metrics(ts),
            "positive_symbols":sum(v["net_r"]>0 for v in symbol_metrics(ts).values()),
            "leave_one_symbol_out":loo(ts)}

def main():
    data={}; contexts={}
    for s in SYMS:
        M=core.load_15m(s); data[s]=M
        D=smc.aggregate_1d(M); W=aggregate_weekly(D); MN=aggregate_monthly(D)
        contexts[s]=(W,MN)
        print("DATA",s,len(M),len(W),len(MN),flush=True)

    A=[];B=[]
    for s in SYMS:
        W,MN=contexts[s]
        a=build_track_a(s,data[s],W,MN)
        b=breakout_candidates(s,data[s],W,MN)
        A+=a;B+=b
        print("TRACK",s,"A",len(a),"B",len(b),flush=True)

    variants={
      "A_current": suppress_symbol_overlap(A),
      "A_score1": suppress_symbol_overlap([t for t in A if t["score"]>=1]),
      "A_score2": suppress_symbol_overlap([t for t in A if t["score"]>=2]),
      "B_break_srflip": suppress_symbol_overlap(B),
      "B_channel_aligned": suppress_symbol_overlap([t for t in B if t["quality"].get("channel_align")]),
      "AplusB": combine_tracks(A,B),
      "AplusB_Bchannel": combine_tracks(A,B,require_b_channel=True),
      "A_score1_plus_Bchannel": combine_tracks(A,B,require_b_channel=True,a_score_min=1),
    }
    out={"version":"0.1","name":"EasyChart public-concept synthesis",
         "concept_map":{
           "regime":"daily EMA trend + completed weekly/monthly alignment",
           "track_a":"liquidity sweep/fakeout -> displacement -> FVG retest",
           "track_b":"breakout -> SR flip retest",
           "channel":"80h regression-channel alignment/fakeout quality diagnostic",
           "order_block":"diagnostic only; prior tests did not justify hard filtering",
           "risk":"structural stop, fixed-R target; 3R only when weekly+monthly aligned",
           "patterns":"cup-handle/diamond/Adam-Eve omitted from v0.1 pending separate objective definitions",
         },
         "configs":{"track_a":BASE_CFG,"track_b":BREAK_CFG},
         "variants":{k:summarize(v) for k,v in variants.items()}}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2),encoding="utf-8")
    print("FINAL",json.dumps({k:v["overall"] for k,v in out["variants"].items()},indent=2),flush=True)

if __name__=="__main__":
    main()
