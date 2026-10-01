import argparse,bisect,json,math
from pathlib import Path
import backtest_trend_structure_v0_1_crypto as core

MS15=15*60*1000
HOUR=60*60*1000
DAY=24*HOUR
RISK_DOLLARS=400.0
CAPITAL=20000.0

DEFAULTS={
    "sweep_lookback":20,
    "sweep_min_atr":0.05,
    "sweep_max_atr":1.50,
    "disp_max_bars":3,
    "disp_body_atr":0.80,
    "disp_close_frac":0.70,
    "fvg_min_atr":0.10,
    "retest_hours":8,
    "stop_buffer_atr":0.15,
    "max_hold_hours":48,
    "cost_bps_per_side":6.0,
}

def load_json_bars(path):
    a=json.loads(Path(path).read_text())
    return [{"t":int(x[0]),"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in a]

def ema(vals,n):
    out=[]; e=None; k=2/(n+1)
    for x in vals:
        e=x if e is None else e+k*(x-e)
        out.append(e)
    return out

def enrich(bars):
    if not bars:return bars
    tr=[]; atr=[]; a=None
    for i,x in enumerate(bars):
        pc=bars[i-1]["c"] if i else x["c"]
        trv=max(x["h"]-x["l"],abs(x["h"]-pc),abs(x["l"]-pc))
        tr.append(trv)
        if i<13: atr.append(None)
        elif i==13:
            a=sum(tr[:14])/14; atr.append(a)
        else:
            a=(13*a+trv)/14; atr.append(a)
    e20=ema([x["c"] for x in bars],20)
    e50=ema([x["c"] for x in bars],50)
    e200=ema([x["c"] for x in bars],200)
    for i,x in enumerate(bars):
        x["atr"]=atr[i]; x["ema20"]=e20[i]; x["ema50"]=e50[i]; x["ema200"]=e200[i]
    return bars

def aggregate_1h(m15):
    out=[]; group=[]; key=None
    for z in m15:
        k=z["t"]//HOUR
        if key is None:key=k
        if k!=key:
            if len(group)==4 and [q["t"] for q in group]==[group[0]["t"]+i*MS15 for i in range(4)]:
                out.append({"t":group[0]["t"],"o":group[0]["o"],"h":max(q["h"] for q in group),
                            "l":min(q["l"] for q in group),"c":group[-1]["c"],"v":sum(q["v"] for q in group)})
            group=[]; key=k
        group.append(z)
    if len(group)==4 and [q["t"] for q in group]==[group[0]["t"]+i*MS15 for i in range(4)]:
        out.append({"t":group[0]["t"],"o":group[0]["o"],"h":max(q["h"] for q in group),
                    "l":min(q["l"] for q in group),"c":group[-1]["c"],"v":sum(q["v"] for q in group)})
    return enrich(out)

def aggregate_1d(m15):
    out=[]; group=[]; key=None
    for z in m15:
        k=z["t"]//DAY
        if key is None:key=k
        if k!=key:
            if len(group)>=92:
                out.append({"t":key*DAY,"o":group[0]["o"],"h":max(q["h"] for q in group),
                            "l":min(q["l"] for q in group),"c":group[-1]["c"],"v":sum(q["v"] for q in group)})
            group=[]; key=k
        group.append(z)
    if group and len(group)>=92:
        out.append({"t":key*DAY,"o":group[0]["o"],"h":max(q["h"] for q in group),
                    "l":min(q["l"] for q in group),"c":group[-1]["c"],"v":sum(q["v"] for q in group)})
    return out

def prepare_daily(d):
    enrich(d)
    return d,[x["t"]+DAY-1 for x in d]

def trend_at(d,dclose,hclose):
    di=bisect.bisect_right(dclose,hclose)-1
    if di<199:return None
    x=d[di]
    if x["c"]>x["ema200"] and x["ema50"]>x["ema200"]:return "LONG"
    if x["c"]<x["ema200"] and x["ema50"]<x["ema200"]:return "SHORT"
    return None

def clv(x):
    r=x["h"]-x["l"]
    return (x["c"]-x["l"])/r if r else .5

def body(x):
    return abs(x["c"]-x["o"])

def find_setup(H,D,Dclose,i,cfg):
    if i<cfg["sweep_lookback"] or not H[i].get("atr"):return None
    s=H[i]; A=s["atr"]
    trend=trend_at(D,Dclose,s["t"]+HOUR-1)
    if trend is None:return None
    prev=H[i-cfg["sweep_lookback"]:i]
    ph=max(x["h"] for x in prev); pl=min(x["l"] for x in prev)
    long_sweep=(s["l"]<pl-cfg["sweep_min_atr"]*A and s["c"]>pl and
                (pl-s["l"])<=cfg["sweep_max_atr"]*A)
    short_sweep=(s["h"]>ph+cfg["sweep_min_atr"]*A and s["c"]<ph and
                 (s["h"]-ph)<=cfg["sweep_max_atr"]*A)
    direction="LONG" if long_sweep and trend=="LONG" else "SHORT" if short_sweep and trend=="SHORT" else None
    if direction is None:return None

    for j in range(i+1,min(len(H),i+1+cfg["disp_max_bars"])):
        q=H[j]; qa=q.get("atr")
        if not qa or j<2:continue
        strong=body(q)>=cfg["disp_body_atr"]*qa
        if direction=="LONG":
            directional=q["c"]>q["o"] and clv(q)>=cfg["disp_close_frac"] and q["c"]>s["h"]
            gap_lo=H[j-2]["h"]; gap_hi=q["l"]; gap=gap_hi-gap_lo
            fvg=gap>=cfg["fvg_min_atr"]*qa
            if not (strong and directional and fvg):continue
            fvg_low,fvg_high=gap_lo,gap_hi
        else:
            directional=q["c"]<q["o"] and clv(q)<=1-cfg["disp_close_frac"] and q["c"]<s["l"]
            gap_low=q["h"]; gap_high=H[j-2]["l"]; gap=gap_high-gap_low
            fvg=gap>=cfg["fvg_min_atr"]*qa
            if not (strong and directional and fvg):continue
            fvg_low,fvg_high=gap_low,gap_high

        entry=(fvg_low+fvg_high)/2
        stop=(s["l"]-cfg["stop_buffer_atr"]*A) if direction=="LONG" else (s["h"]+cfg["stop_buffer_atr"]*A)
        risk=abs(entry-stop)
        if risk<=0 or risk<0.10*qa or risk>4.0*qa:continue

        ob=None
        for k in range(j-1,max(i-1,j-6),-1):
            z=H[k]
            if direction=="LONG" and z["c"]<z["o"]:
                ob=(min(z["o"],z["c"]),max(z["o"],z["c"]),k);break
            if direction=="SHORT" and z["c"]>z["o"]:
                ob=(min(z["o"],z["c"]),max(z["o"],z["c"]),k);break
        ob_overlap=bool(ob and ob[0]<=entry<=ob[1])
        return {"direction":direction,"sweep_i":i,"disp_i":j,"signal_t":q["t"]+HOUR-1,
                "entry":entry,"stop":stop,"risk":risk,"fvg_low":fvg_low,"fvg_high":fvg_high,
                "ob_overlap":ob_overlap,"ob_i":ob[2] if ob else None,
                "sweep_level":pl if direction=="LONG" else ph,
                "trend":trend}
    return None

def locate_entry(M,setup,cfg):
    ts=[x["t"] for x in M]
    start=setup["signal_t"]+1
    end=start+cfg["retest_hours"]*HOUR
    mi=bisect.bisect_left(ts,start)
    while mi<len(M) and M[mi]["t"]<end:
        z=M[mi]
        if z["l"]<=setup["entry"]<=z["h"]:
            return mi
        mi+=1
    return None

def runner_pivot_stop(H,hclose_times,zclose,direction,stop):
    hk=bisect.bisect_right(hclose_times,zclose)-1
    if hk<2:return stop
    p=hk-1
    A=H[p].get("atr")
    if not A:return stop
    if direction=="LONG" and H[p]["l"]<H[p-1]["l"] and H[p]["l"]<H[p+1]["l"]:
        return max(stop,H[p]["l"]-.20*A)
    if direction=="SHORT" and H[p]["h"]>H[p-1]["h"] and H[p]["h"]>H[p+1]["h"]:
        return min(stop,H[p]["h"]+.20*A)
    return stop

def simulate_trade(M,H,entry_i,setup,cfg,mode):
    direction=setup["direction"]; sign=1 if direction=="LONG" else -1
    entry=setup["entry"]; stop0=setup["stop"]; risk=setup["risk"]
    tp1=entry+sign*risk; tp2=entry+sign*2*risk
    size=RISK_DOLLARS/risk
    cost_rate=cfg["cost_bps_per_side"]/10000.0
    pnl=-size*entry*cost_rate
    remain=1.0; stop=stop0; events=[]; tp1_done=False; tp2_done=False
    hclose=[x["t"]+HOUR-1 for x in H]
    end_t=M[entry_i]["t"]+cfg["max_hold_hours"]*HOUR
    last=M[entry_i]
    for mi in range(entry_i,len(M)):
        z=M[mi]; last=z
        if z["t"]>=end_t:break
        hit_stop=z["l"]<=stop if direction=="LONG" else z["h"]>=stop
        if hit_stop:
            pnl+=remain*size*sign*(stop-entry)-remain*size*stop*cost_rate
            events.append({"type":"BE" if abs(stop-entry)<1e-12 else "STOP","t":z["t"],"price":stop,"fraction":remain})
            remain=0;break
        if mode=="fixed2r":
            hit_tp2=z["h"]>=tp2 if direction=="LONG" else z["l"]<=tp2
            if hit_tp2:
                pnl+=remain*size*sign*(tp2-entry)-remain*size*tp2*cost_rate
                events.append({"type":"TP2_FULL","t":z["t"],"price":tp2,"fraction":remain})
                remain=0;break
            continue

        hit_tp1=(z["h"]>=tp1 if direction=="LONG" else z["l"]<=tp1)
        if not tp1_done and hit_tp1:
            frac=.20
            pnl+=frac*size*sign*(tp1-entry)-frac*size*tp1*cost_rate
            remain-=frac;tp1_done=True;stop=entry
            events.append({"type":"TP1","t":z["t"],"price":tp1,"fraction":frac})
        hit_tp2=(z["h"]>=tp2 if direction=="LONG" else z["l"]<=tp2)
        if not tp2_done and hit_tp2:
            frac=.20
            pnl+=frac*size*sign*(tp2-entry)-frac*size*tp2*cost_rate
            remain-=frac;tp2_done=True;stop=tp1
            events.append({"type":"TP2","t":z["t"],"price":tp2,"fraction":frac})
        if tp2_done and remain>0:
            ns=runner_pivot_stop(H,hclose,z["t"]+MS15-1,direction,stop)
            if ns!=stop:
                stop=ns;events.append({"type":"TRAIL","t":z["t"],"price":stop})
    if remain>0:
        px=last["c"]
        pnl+=remain*size*sign*(px-entry)-remain*size*px*cost_rate
        events.append({"type":"TIME_EXIT","t":last["t"],"price":px,"fraction":remain})
        remain=0
    return {"entry_t":M[entry_i]["t"],"exit_t":events[-1]["t"],"direction":direction,
            "entry":entry,"stop":stop0,"tp1":tp1,"tp2":tp2,"pnl":pnl,"r":pnl/RISK_DOLLARS,
            "reason":events[-1]["type"],"ob_overlap":setup["ob_overlap"],"signal_t":setup["signal_t"],
            "sweep_t":H[setup["sweep_i"]]["t"],"disp_t":H[setup["disp_i"]]["t"],"events":events}

def suppress_overlap(trades):
    out=[]; active=-1
    for t in sorted(trades,key=lambda x:x["entry_t"]):
        if t["entry_t"]<=active:continue
        out.append(t);active=t["exit_t"]
    return out

def stats(trades):
    if not trades:return {"n":0,"win_rate":None,"net_r":0.0,"avg_r":None,"pf":None,"mdd_r":0.0,"return_on_20k":0.0}
    rs=[t["r"] for t in trades]
    wins=sum(r>0 for r in rs)
    gp=sum(r for r in rs if r>0);gl=-sum(r for r in rs if r<0)
    eq=0;peak=0;mdd=0
    for t in sorted(trades,key=lambda x:x["exit_t"]):
        eq+=t["r"];peak=max(peak,eq);mdd=max(mdd,peak-eq)
    return {"n":len(trades),"win_rate":wins/len(trades),"net_r":sum(rs),"avg_r":sum(rs)/len(rs),
            "pf":gp/gl if gl>0 else None,"mdd_r":mdd,"return_on_20k":sum(rs)*RISK_DOLLARS/CAPITAL}

def run_symbol(sym,root,cfg):
    M=core.load_15m(sym)
    H=aggregate_1h(M)
    D,Dclose=prepare_daily(aggregate_1d(M))
    candidates=[];setup_count=0
    for i in range(cfg["sweep_lookback"],len(H)-cfg["disp_max_bars"]):
        s=find_setup(H,D,Dclose,i,cfg)
        if not s:continue
        setup_count+=1
        ei=locate_entry(M,s,cfg)
        if ei is None:continue
        candidates.append((s,ei))
    fixed=[];scaled=[]
    for s,ei in candidates:
        fixed.append(simulate_trade(M,H,ei,s,cfg,"fixed2r"))
        scaled.append(simulate_trade(M,H,ei,s,cfg,"20_20_60"))
    fixed=suppress_overlap(fixed);scaled=suppress_overlap(scaled)
    return {"setup_count":setup_count,"filled_count":len(candidates),
            "fixed2r":{"stats":stats(fixed),"ob_overlap":stats([t for t in fixed if t["ob_overlap"]]),
                       "no_ob_overlap":stats([t for t in fixed if not t["ob_overlap"]]),"trades":fixed},
            "scaled_20_20_60":{"stats":stats(scaled),"ob_overlap":stats([t for t in scaled if t["ob_overlap"]]),
                               "no_ob_overlap":stats([t for t in scaled if not t["ob_overlap"]]),"trades":scaled}}

def combine(symbols,mode):
    all_trades=[]
    for sym,x in symbols.items():
        for t in x[mode]["trades"]:
            q=dict(t);q["symbol"]=sym;all_trades.append(q)
    return {"stats":stats(all_trades),"ob_overlap":stats([t for t in all_trades if t["ob_overlap"]]),
            "no_ob_overlap":stats([t for t in all_trades if not t["ob_overlap"]])}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",default="data/spot")
    ap.add_argument("--symbols",default="BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT")
    ap.add_argument("--out",default="data/validation/smc_liq_fvg_v01_crypto.json")
    ap.add_argument("--cost-bps",type=float,default=DEFAULTS["cost_bps_per_side"])
    args=ap.parse_args()
    cfg=dict(DEFAULTS);cfg["cost_bps_per_side"]=args.cost_bps
    root=Path(args.root);syms=[s.strip() for s in args.symbols.split(",") if s.strip()]
    result={"version":"0.1.1","strategy":"objective liquidity sweep + displacement + FVG first retest",
            "asset_class":"Binance USDT-M perpetual",
            "period":{"fetch_start":core.FETCH_START.isoformat(),"eval_start":core.EVAL_START.isoformat(),"eval_end_exclusive":core.EVAL_END.isoformat()},
            "signal_tf":"1h","execution_tf":"15m","trend_tf":"1d",
            "rules":{"trend":"LONG: completed daily close>EMA200 and EMA50>EMA200; SHORT inverse",
                     "sweep":"20x1H prior extreme sweep, 0.05-1.50 ATR penetration, close back inside",
                     "displacement":"within 1-3x1H; body>=0.8 ATR; close through sweep candle extreme; directional CLV>=0.70",
                     "fvg":"classic 3-candle FVG width>=0.10 ATR; entry at midpoint on first retest within 8h",
                     "stop":"sweep extreme +/-0.15 ATR",
                     "management_a":"full exit at 2R",
                     "management_b":"20% at 1R -> BE; 20% at 2R -> stop to 1R; 60% confirmed 1H pivot runner",
                     "timeout":"48h",
                     "ob":"diagnostic only: FVG midpoint overlaps body of last opposite 1H candle before displacement"},
            "config":cfg,"symbols":{}}
    for s in syms:
        print("BACKTEST",s,flush=True)
        result["symbols"][s]=run_symbol(s,root,cfg)
    result["combined"]={"fixed2r":combine(result["symbols"],"fixed2r"),
                        "scaled_20_20_60":combine(result["symbols"],"scaled_20_20_60")}
    out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,separators=(",",":")))
    summary={s:{"setups":x["setup_count"],"fills":x["filled_count"],
                "fixed2r":x["fixed2r"]["stats"],"scaled":x["scaled_20_20_60"]["stats"]} for s,x in result["symbols"].items()}
    summary["combined"]=result["combined"]
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()

# trigger: smc-liq-fvg-v011-direct-binance-data
