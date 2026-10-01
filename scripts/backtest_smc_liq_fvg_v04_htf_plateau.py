import bisect,json,calendar
from pathlib import Path
from collections import defaultdict
from datetime import datetime,timezone,timedelta
import backtest_smc_liq_fvg_v01 as smc
import backtest_trend_structure_v0_1_crypto as core

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/validation/smc_liq_fvg_v04_htf_plateau.json"
UTC=timezone.utc
SYMS=("BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","LINKUSDT")
W_LENS=(16,20,24)
M_LENS=(4,6,8)
STRONG_TPS=(2.5,3.0,3.5)

def ema(vals,n):
    e=None;k=2/(n+1);out=[]
    for x in vals:
        e=x if e is None else e+k*(x-e);out.append(e)
    return out

def aggregate_weekly(D):
    g=defaultdict(list)
    for z in D:
        dt=datetime.fromtimestamp(z["t"]/1000,UTC)
        m=(dt-timedelta(days=dt.weekday())).replace(hour=0,minute=0,second=0,microsecond=0)
        g[int(m.timestamp()*1000)].append(z)
    out=[]
    for k in sorted(g):
        xs=g[k]
        days={datetime.fromtimestamp(x["t"]/1000,UTC).weekday() for x in xs}
        if len(days)<7: continue
        out.append({"t":k,"ct":k+7*smc.DAY-1,"o":xs[0]["o"],"h":max(x["h"] for x in xs),
                    "l":min(x["l"] for x in xs),"c":xs[-1]["c"],"v":sum(x["v"] for x in xs)})
    return out

def month_next(y,m):
    if m==12:return int(datetime(y+1,1,1,tzinfo=UTC).timestamp()*1000)
    return int(datetime(y,m+1,1,tzinfo=UTC).timestamp()*1000)

def aggregate_monthly(D):
    g=defaultdict(list)
    for z in D:
        dt=datetime.fromtimestamp(z["t"]/1000,UTC);g[(dt.year,dt.month)].append(z)
    out=[]
    for (y,m) in sorted(g):
        xs=g[(y,m)]
        if len(xs)<calendar.monthrange(y,m)[1]:continue
        t=int(datetime(y,m,1,tzinfo=UTC).timestamp()*1000)
        out.append({"t":t,"ct":month_next(y,m)-1,"o":xs[0]["o"],"h":max(x["h"] for x in xs),
                    "l":min(x["l"] for x in xs),"c":xs[-1]["c"],"v":sum(x["v"] for x in xs)})
    return out

def enrich_many(bars,lens):
    vals=[x["c"] for x in bars]
    for n in lens:
        e=ema(vals,n)
        for i,x in enumerate(bars):x[f"ema{n}"]=e[i]
    return bars

def aligned_at(W,M,t,direction,wlen,mlen):
    wc=[x["ct"] for x in W];mc=[x["ct"] for x in M]
    wi=bisect.bisect_right(wc,t)-1;mi=bisect.bisect_right(mc,t)-1
    if wi<0 or mi<0:return False
    w=W[wi];m=M[mi]
    if direction=="LONG":return w["c"]>w[f"ema{wlen}"] and m["c"]>m[f"ema{mlen}"]
    return w["c"]<w[f"ema{wlen}"] and m["c"]<m[f"ema{mlen}"]

def resim(M,t,target_r,max_hold=48,cost_bps=6.0):
    direction=t["direction"];sign=1 if direction=="LONG" else -1
    entry=t["entry"];stop=t["stop"];risk=abs(entry-stop)
    if risk<=0:return None
    target=entry+sign*target_r*risk
    size=smc.RISK_DOLLARS/risk;cr=cost_bps/10000
    pnl=-size*entry*cr
    times=[x["t"] for x in M];i=bisect.bisect_left(times,t["entry_t"])
    end=t["entry_t"]+max_hold*smc.HOUR
    last=M[i];reason="TIME";exit_t=last["t"]
    for j in range(i,len(M)):
        z=M[j];last=z
        if z["t"]>=end:break
        stop_hit=z["l"]<=stop if direction=="LONG" else z["h"]>=stop
        if stop_hit:
            pnl+=size*sign*(stop-entry)-size*stop*cr;reason="STOP";exit_t=z["t"];break
        tp_hit=z["h"]>=target if direction=="LONG" else z["l"]<=target
        if tp_hit:
            pnl+=size*sign*(target-entry)-size*target*cr;reason="TP";exit_t=z["t"];break
    if reason=="TIME":
        px=last["c"];pnl+=size*sign*(px-entry)-size*px*cr;exit_t=last["t"]
    q=dict(t);q["r"]=pnl/smc.RISK_DOLLARS;q["exit_t"]=exit_t;q["target_r"]=target_r;q["reason_v04"]=reason
    return q

def metrics(ts):
    if not ts:return {"n":0,"win_rate":None,"net_r":0.0,"avg_r":None,"pf":None,"mdd_r":0.0,"max_ls":0}
    o=sorted(ts,key=lambda z:(z["exit_t"],z["symbol"]))
    rs=[t["r"] for t in o];p=[r for r in rs if r>0];n=[r for r in rs if r<0]
    eq=peak=mdd=0.0;cur=mx=0
    for r in rs:
        eq+=r;peak=max(peak,eq);mdd=max(mdd,peak-eq)
        if r<0:cur+=1;mx=max(mx,cur)
        else:cur=0
    return {"n":len(rs),"win_rate":len(p)/len(rs),"net_r":sum(rs),"avg_r":sum(rs)/len(rs),
            "pf":sum(p)/abs(sum(n)) if n else None,"mdd_r":mdd,"max_ls":mx}

def group_year(ts):
    d=defaultdict(list)
    for t in ts:d[str(datetime.fromtimestamp(t["entry_t"]/1000,UTC).year)].append(t)
    return {k:metrics(v) for k,v in sorted(d.items())}

def loo(ts):
    return {s:metrics([t for t in ts if t["symbol"]!=s]) for s in SYMS}

def main():
    data={};reg={}
    for s in SYMS:
        b=core.load_15m(s);data[s]=b
        D=smc.aggregate_1d(b)
        W=enrich_many(aggregate_weekly(D),W_LENS)
        M=enrich_many(aggregate_monthly(D),M_LENS)
        reg[s]=(W,M)
        print("DATA",s,len(b),len(W),len(M),flush=True)

    cfg=dict(smc.DEFAULTS);cfg.update({"trend_mode":"price_ema50","tp_r":2.0,"signal_minutes":60})
    orig=smc.core.load_15m;base=[]
    try:
        smc.core.load_15m=lambda sym:data[sym]
        for s in SYMS:
            r=smc.run_symbol(s,None,cfg)
            for t in r["fixed2r"]["trades"]:
                q=dict(t);q["symbol"]=s;base.append(q)
    finally:smc.core.load_15m=orig

    variants={}
    for wl in W_LENS:
        for ml in M_LENS:
            for tp in STRONG_TPS:
                ts=[]
                for t in base:
                    W,M=reg[t["symbol"]]
                    strong=aligned_at(W,M,t["signal_t"],t["direction"],wl,ml)
                    ts.append(resim(data[t["symbol"]],t,tp if strong else 2.0))
                key=f"w{wl}_m{ml}_tp{tp:g}"
                sy=defaultdict(list)
                for t in ts:sy[t["symbol"]].append(t)
                variants[key]={
                    "params":{"weekly_ema":wl,"monthly_ema":ml,"strong_tp_r":tp},
                    "overall":metrics(ts),
                    "years":group_year(ts),
                    "positive_symbols":sum(metrics(v)["net_r"]>0 for v in sy.values()),
                    "symbols":{s:metrics(sy.get(s,[])) for s in SYMS},
                    "leave_one_symbol_out":loo(ts),
                }
                print("VAR",key,json.dumps(variants[key]["overall"]),flush=True)

    out={"version":"0.4","base_signal":{"trend_mode":"price_ema50","normal_tp_r":2.0},
         "purpose":"higher-TF parameter plateau and leave-one-symbol-out robustness",
         "variants":variants}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,indent=2),encoding="utf-8")
    print("FINAL",json.dumps({k:v["overall"] for k,v in variants.items()},indent=2),flush=True)

if __name__=="__main__":main()
