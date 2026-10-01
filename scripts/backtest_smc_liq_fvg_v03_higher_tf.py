import bisect,json,calendar
from pathlib import Path
from collections import defaultdict
from datetime import datetime,timezone,timedelta
import backtest_smc_liq_fvg_v01 as smc
import backtest_trend_structure_v0_1_crypto as core

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/validation/smc_liq_fvg_v03_higher_tf.json"
UTC=timezone.utc
SYMS=("BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","LINKUSDT")
TRAIN_END=int(datetime(2025,1,1,tzinfo=UTC).timestamp()*1000)

SIGNAL_CONFIGS={
    "strict":{"signal_minutes":60,"tp_r":2.0},
    "price50":{"signal_minutes":60,"tp_r":2.0,"trend_mode":"price_ema50"},
    "disp090":{"signal_minutes":60,"tp_r":2.0,"disp_body_atr":0.90},
}

def ema(vals,n):
    k=2.0/(n+1.0);e=None;out=[]
    for x in vals:
        e=x if e is None else e+k*(x-e);out.append(e)
    return out

def enrich_regime(bars):
    if not bars:return bars
    c=[x["c"] for x in bars]
    for n in (6,12,20,50):
        e=ema(c,n)
        for i,x in enumerate(bars):x[f"ema{n}"]=e[i]
    for i,x in enumerate(bars):
        x["ema20_4ago"]=bars[i-4]["ema20"] if i>=4 else None
        x["ema6_3ago"]=bars[i-3]["ema6"] if i>=3 else None
    return bars

def aggregate_weekly(D):
    groups=defaultdict(list)
    for z in D:
        dt=datetime.fromtimestamp(z["t"]/1000,UTC)
        monday=(dt-timedelta(days=dt.weekday())).replace(hour=0,minute=0,second=0,microsecond=0)
        groups[int(monday.timestamp()*1000)].append(z)
    out=[]
    for k in sorted(groups):
        xs=groups[k]
        # Need a complete Mon-Sun week; partial first/last weeks are excluded.
        days={datetime.fromtimestamp(x["t"]/1000,UTC).weekday() for x in xs}
        if len(days)<7:continue
        out.append({"t":k,"ct":k+7*smc.DAY-1,"o":xs[0]["o"],"h":max(x["h"] for x in xs),
                    "l":min(x["l"] for x in xs),"c":xs[-1]["c"],"v":sum(x["v"] for x in xs)})
    return enrich_regime(out)

def month_next_ms(y,m):
    if m==12:return int(datetime(y+1,1,1,tzinfo=UTC).timestamp()*1000)
    return int(datetime(y,m+1,1,tzinfo=UTC).timestamp()*1000)

def aggregate_monthly(D):
    groups=defaultdict(list)
    for z in D:
        dt=datetime.fromtimestamp(z["t"]/1000,UTC)
        groups[(dt.year,dt.month)].append(z)
    out=[]
    for (y,m) in sorted(groups):
        xs=groups[(y,m)]
        # require all calendar days; crypto is 24/7
        if len(xs)<calendar.monthrange(y,m)[1]:continue
        t=int(datetime(y,m,1,tzinfo=UTC).timestamp()*1000)
        out.append({"t":t,"ct":month_next_ms(y,m)-1,"o":xs[0]["o"],"h":max(x["h"] for x in xs),
                    "l":min(x["l"] for x in xs),"c":xs[-1]["c"],"v":sum(x["v"] for x in xs)})
    return enrich_regime(out)

def ctx_at(W,M,t,direction):
    wi=bisect.bisect_right([x["ct"] for x in W],t)-1
    mi=bisect.bisect_right([x["ct"] for x in M],t)-1
    w=W[wi] if wi>=0 else None;m=M[mi] if mi>=0 else None
    long=direction=="LONG"
    def side(ok_long,ok_short):return ok_long if long else ok_short
    return {
      "w_price20": bool(w and side(w["c"]>w["ema20"],w["c"]<w["ema20"])),
      "w_20_50": bool(w and side(w["ema20"]>w["ema50"],w["ema20"]<w["ema50"])),
      "w_slope20": bool(w and w.get("ema20_4ago") is not None and side(w["ema20"]>w["ema20_4ago"],w["ema20"]<w["ema20_4ago"])),
      "m_price6": bool(m and side(m["c"]>m["ema6"],m["c"]<m["ema6"])),
      "m_6_12": bool(m and side(m["ema6"]>m["ema12"],m["ema6"]<m["ema12"])),
      "m_slope6": bool(m and m.get("ema6_3ago") is not None and side(m["ema6"]>m["ema6_3ago"],m["ema6"]<m["ema6_3ago"])),
    }

def metrics(ts):
    if not ts:return {"n":0,"win_rate":None,"net_r":0.0,"avg_r":None,"pf":None,"mdd_r":0.0,"max_ls":0}
    o=sorted(ts,key=lambda z:(z["exit_t"],z["symbol"]))
    rs=[t["r"] for t in o];pos=[r for r in rs if r>0];neg=[r for r in rs if r<0]
    eq=peak=mdd=0.0;cur=mx=0
    for r in rs:
        eq+=r;peak=max(peak,eq);mdd=max(mdd,peak-eq)
        if r<0:cur+=1;mx=max(mx,cur)
        else:cur=0
    return {"n":len(rs),"win_rate":len(pos)/len(rs),"net_r":sum(rs),"avg_r":sum(rs)/len(rs),
            "pf":sum(pos)/abs(sum(neg)) if neg else None,"mdd_r":mdd,"max_ls":mx}

def split(ts):
    return [t for t in ts if t["entry_t"]<TRAIN_END],[t for t in ts if t["entry_t"]>=TRAIN_END]

def summarize(ts):
    tr,ho=split(ts)
    sy=defaultdict(list)
    for t in ts:sy[t["symbol"]].append(t)
    return {"overall":metrics(ts),"train":metrics(tr),"holdout":metrics(ho),
            "positive_symbols":sum(metrics(v)["net_r"]>0 for v in sy.values()),
            "symbols":{k:metrics(v) for k,v in sorted(sy.items())}}

def filter_by(ts,key):
    return [t for t in ts if t["ctx"].get(key)]

def filter_combo(ts,keys,minimum=None):
    if minimum is None:minimum=len(keys)
    return [t for t in ts if sum(bool(t["ctx"].get(k)) for k in keys)>=minimum]

def resim_target(M,t,target_r,max_hold_hours=48,cost_bps=6.0):
    direction=t["direction"];sign=1 if direction=="LONG" else -1
    entry=t["entry"];stop=t["stop"];risk=abs(entry-stop)
    if risk<=0:return None
    target=entry+sign*target_r*risk
    size=smc.RISK_DOLLARS/risk;cost_rate=cost_bps/10000.0
    pnl=-size*entry*cost_rate
    ts=[x["t"] for x in M];i=bisect.bisect_left(ts,t["entry_t"])
    end=t["entry_t"]+max_hold_hours*smc.HOUR
    last=M[i]
    reason="TIME"
    for j in range(i,len(M)):
        z=M[j];last=z
        if z["t"]>=end:break
        hit_stop=z["l"]<=stop if direction=="LONG" else z["h"]>=stop
        if hit_stop:
            pnl+=size*sign*(stop-entry)-size*stop*cost_rate;reason="STOP";break
        hit_tp=z["h"]>=target if direction=="LONG" else z["l"]<=target
        if hit_tp:
            pnl+=size*sign*(target-entry)-size*target*cost_rate;reason="TP";break
    else:
        j=len(M)-1
    if reason=="TIME":
        px=last["c"];pnl+=size*sign*(px-entry)-size*px*cost_rate
    q=dict(t);q["r"]=pnl/smc.RISK_DOLLARS;q["exit_t"]=last["t"] if reason=="TIME" else M[j]["t"];q["target_r"]=target_r;q["reason_v03"]=reason
    return q

def adaptive(ts,data,strong_keys,strong_tp):
    out=[]
    for t in ts:
        aligned=all(t["ctx"].get(k) for k in strong_keys)
        out.append(resim_target(data[t["symbol"]],t,strong_tp if aligned else 2.0))
    return out

def main():
    data={};regimes={}
    for s in SYMS:
        b=core.load_15m(s);data[s]=b
        D=smc.aggregate_1d(b)
        regimes[s]=(aggregate_weekly(D),aggregate_monthly(D))
        print("DATA",s,len(b),"W",len(regimes[s][0]),"M",len(regimes[s][1]),flush=True)

    orig=smc.core.load_15m
    result={"version":"0.3","purpose":"completed weekly/monthly regime filters and adaptive TP","signal_configs":{}}
    try:
        smc.core.load_15m=lambda sym:data[sym]
        for cfg_name,ov in SIGNAL_CONFIGS.items():
            cfg=dict(smc.DEFAULTS);cfg.update(ov)
            trades=[]
            for s in SYMS:
                r=smc.run_symbol(s,None,cfg)
                W,M=regimes[s]
                for t in r["fixed2r"]["trades"]:
                    q=dict(t);q["symbol"]=s;q["ctx"]=ctx_at(W,M,q["signal_t"],q["direction"]);trades.append(q)

            variants={
              "all":trades,
              "w_price20":filter_by(trades,"w_price20"),
              "w_20_50":filter_by(trades,"w_20_50"),
              "w_slope20":filter_by(trades,"w_slope20"),
              "m_price6":filter_by(trades,"m_price6"),
              "m_6_12":filter_by(trades,"m_6_12"),
              "m_slope6":filter_by(trades,"m_slope6"),
              "w_price20+m_price6":filter_combo(trades,("w_price20","m_price6")),
              "w_20_50+m_6_12":filter_combo(trades,("w_20_50","m_6_12")),
              "w_slope20+m_slope6":filter_combo(trades,("w_slope20","m_slope6")),
              "htf_vote_3of6":filter_combo(trades,("w_price20","w_20_50","w_slope20","m_price6","m_6_12","m_slope6"),3),
              "htf_vote_4of6":filter_combo(trades,("w_price20","w_20_50","w_slope20","m_price6","m_6_12","m_slope6"),4),
            }
            adapt={
              "adaptive_wm_2p5":adaptive(trades,data,("w_price20","m_price6"),2.5),
              "adaptive_wm_3r":adaptive(trades,data,("w_price20","m_price6"),3.0),
              "adaptive_struct_2p5":adaptive(trades,data,("w_20_50","m_6_12"),2.5),
              "adaptive_struct_3r":adaptive(trades,data,("w_20_50","m_6_12"),3.0),
            }
            result["signal_configs"][cfg_name]={
                "config":cfg,
                "filters":{k:summarize(v) for k,v in variants.items()},
                "adaptive_tp":{k:summarize(v) for k,v in adapt.items()},
            }
            print("CFG",cfg_name,json.dumps({
                "filters":{k:summarize(v)["overall"] for k,v in variants.items()},
                "adaptive":{k:summarize(v)["overall"] for k,v in adapt.items()}
            }),flush=True)
    finally:
        smc.core.load_15m=orig

    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print("FINAL",json.dumps({c:{
       "filters":{k:v["overall"] for k,v in x["filters"].items()},
       "adaptive":{k:v["overall"] for k,v in x["adaptive_tp"].items()}
    } for c,x in result["signal_configs"].items()},indent=2),flush=True)

if __name__=="__main__":main()
