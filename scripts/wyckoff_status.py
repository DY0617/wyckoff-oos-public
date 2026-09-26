import json
import math
from pathlib import Path
from datetime import datetime, timezone

SYMBOLS=("BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT")
ROOT=Path("data/spot")
OUT=Path("data/wyckoff_status.json")

# Track B production defaults selected by corrected v6 walk-forward robustness test. Optimizers may pass overrides without mutating live defaults.
LOCAL_DEFAULTS={"range_max_atr":12.0,"range_er_max":0.80,"penetration_min":0.25,"penetration_max":2.50,"test_overlap_atr":1.50,"test_spread_max":1.25,"test_volume_max":1.05,"entry_buffer_atr":0.05,"stop_buffer_atr":0.25,"rr_long_min":1.10,"rr_long_max":2.00,"rr_short_min":1.10,"rr_short_max":1.80,"target_distance_atr":3.50,"return30_min":-0.05,"ema_gap_atr_max":2.0,"trigger_window":9}
STRUCT_DEFAULTS={"climax_spread_min":1.25,"climax_volume_min":1.40,"penetration_min":0.15,"penetration_max":1.50,"test_spread_max":0.90,"test_volume_anchor_max":0.85,"test_volume_sma_max":0.90,"entry_buffer_atr":0.05,"stop_buffer_atr":0.25,"rr_min":2.0,"trigger_window":12}

def params(defaults, overrides=None):
    p=defaults.copy()
    if overrides:p.update(overrides)
    return p

def symbol_tick(symbol):
    try:
        x=json.loads((ROOT/symbol/"filters.json").read_text())
        return float(x.get("tick_size") or 0)
    except Exception:
        return 0.0

def floor_tick(x,tick):
    return math.floor((x+1e-12)/tick)*tick if tick else x

def ceil_tick(x,tick):
    return math.ceil((x-1e-12)/tick)*tick if tick else x

def quantize_signal_levels(signal,track,symbol):
    if not signal:return signal
    tick=symbol_tick(symbol)
    entry=signal.get("entry"); stop=signal.get("stop")
    if not tick or entry is None or stop is None:return signal
    direction=(signal.get("direction") if track=="B" else
               ("LONG" if signal.get("bias")=="ACCUMULATION" else "SHORT"))
    if direction not in ("LONG","SHORT"):return signal
    if direction=="LONG":
        signal["entry"]=ceil_tick(entry,tick); signal["stop"]=floor_tick(stop,tick)
        for k in ("tp1","tp2","target"):
            if signal.get(k) is not None:signal[k]=floor_tick(signal[k],tick)
    else:
        signal["entry"]=floor_tick(entry,tick); signal["stop"]=ceil_tick(stop,tick)
        for k in ("tp1","tp2","target"):
            if signal.get(k) is not None:signal[k]=ceil_tick(signal[k],tick)
    target=signal.get("tp2") if track=="B" else signal.get("target")
    if target is not None:
        risk=abs(signal["entry"]-signal["stop"])
        signal["rr"]=((target-signal["entry"])/risk if direction=="LONG"
                      else (signal["entry"]-target)/risk) if risk else -99
    return signal

def bars(symbol,tf,n):
    a=json.loads((ROOT/symbol/f"{tf}.json").read_text())
    out=[]
    for x in a[-n:]:
        out.append({"t":int(x[0]),"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])})
    return out

def ema(v,n):
    k=2/(n+1); e=None; out=[]
    for x in v:
        e=x if e is None else e+k*(x-e); out.append(e)
    return out

def sma(v,n):
    out=[]
    for i in range(len(v)):
        out.append(sum(v[i-n+1:i+1])/n if i>=n-1 else None)
    return out

def enrich(b):
    c=[x["c"] for x in b]; sp=[x["h"]-x["l"] for x in b]; vol=[x["v"] for x in b]
    e20,e50=ema(c,20),ema(c,50); ss,vs=sma(sp,20),sma(vol,20)
    tr=[]
    for i,x in enumerate(b):
        pc=b[i-1]["c"] if i else x["c"]
        tr.append(max(x["h"]-x["l"],abs(x["h"]-pc),abs(x["l"]-pc)))
    at=[]; a=None
    for i,x in enumerate(tr):
        if i<13: at.append(None)
        elif i==13: a=sum(tr[:14])/14; at.append(a)
        else: a=(13*a+x)/14; at.append(a)
    for i,x in enumerate(b):
        x.update(ema20=e20[i],ema50=e50[i],ssma=ss[i],vsma=vs[i],atr=at[i],spread=sp[i],
                 clv=((x["c"]-x["l"])/sp[i] if sp[i] else .5))
    return b

def pivots(b):
    # Confirmed 3-bar pivots: the center bar is confirmed only after the next bar closes.
    hi=[];lo=[]
    for i in range(1,len(b)-1):
        if b[i]["h"]>b[i-1]["h"] and b[i]["h"]>=b[i+1]["h"]:hi.append(i)
        if b[i]["l"]<b[i-1]["l"] and b[i]["l"]<=b[i+1]["l"]:lo.append(i)
    return hi,lo

def range_stats(p,atr, cfg=None):
    cfg=params(LOCAL_DEFAULTS,cfg)
    sup=min(z["l"] for z in p); res=max(z["h"] for z in p); height=res-sup
    travel=sum(abs(p[i]["c"]-p[i-1]["c"]) for i in range(1,len(p)))
    er=abs(p[-1]["c"]-p[0]["c"])/travel if travel else 0
    valid=bool(atr and atr<=height<=cfg["range_max_atr"]*atr and er<=cfg["range_er_max"]
               and any(z["l"]<=sup+atr for z in p)
               and any(z["h"]>=res-atr for z in p))
    return sup,res,er,valid

def reclaim_index(h,ai,boundary,direction,max_bars):
    end=min(len(h)-1,ai+max_bars)
    for j in range(ai,end+1):
        if direction=="LONG" and h[j]["c"]>=boundary:return j
        if direction=="SHORT" and h[j]["c"]<=boundary:return j
    return None

def pretrigger_invalid(h,start,end,sup,res,fallback_atr=None):
    outside=0
    for j in range(start,end+1):
        q=h[j]; atr=q.get("atr") or fallback_atr
        if atr and (q["c"]<sup-.75*atr or q["c"]>res+.75*atr):return True
        is_out=q["c"]<sup or q["c"]>res
        outside=outside+1 if is_out else 0
        if outside>=2:return True
    return False

def local_liquidity_fib_tp1(h,direction,anchor_i,reclaim_i,test_i,entry,stop,sup,res):
    """Choose Track-B TP1 from pre-existing 4H liquidity with Fibonacci confluence.
    Uses only bars known by the Test bar: no future bars / lookahead.
    TP2 remains the frozen opposite range boundary.
    """
    q=h[test_i]; atr=q.get("atr")
    risk=abs(entry-stop)
    tp2=res if direction=="LONG" else sup
    if not atr or risk<=0:
        return (entry+tp2)/2,{"method":"MIDPOINT_FALLBACK","score":0,"fib_ratio":None,"zone_types":[]},None

    sign=1 if direction=="LONG" else -1
    # Confirmed 3-bar pivot liquidity known by the Test close.
    raw=[{"price":tp2,"base_score":2,"types":{"RANGE_BOUNDARY"}}]
    start=max(1,test_i-48)
    for i in range(start,test_i):
        if i+1>test_i: break
        if direction=="LONG":
            is_pivot=h[i]["h"]>h[i-1]["h"] and h[i]["h"]>=h[i+1]["h"]
            px=h[i]["h"]
        else:
            is_pivot=h[i]["l"]<h[i-1]["l"] and h[i]["l"]<=h[i+1]["l"]
            px=h[i]["l"]
        if is_pivot:
            raw.append({"price":px,"base_score":1,"types":{"PIVOT_LIQUIDITY"}})

    # Merge nearby liquidity into zones. Multiple pivots naturally become
    # equal-high/equal-low liquidity clusters.
    raw.sort(key=lambda x:x["price"])
    zones=[]
    tol=.20*atr
    for r in raw:
        if zones and abs(r["price"]-zones[-1]["price"])<=tol:
            z=zones[-1]
            n=z["n"]
            z["price"]=(z["price"]*n+r["price"])/(n+1)
            z["n"]=n+1
            z["base_score"]+=r["base_score"]
            z["types"].update(r["types"])
            if z["n"]>=2:z["types"].add("LIQUIDITY_CLUSTER")
        else:
            zones.append({"price":r["price"],"base_score":r["base_score"],"types":set(r["types"]),"n":1})

    # Fibonacci extension of the initial spring/UTAD reclaim leg.
    if direction=="LONG":
        origin=h[anchor_i]["l"]
        leg_end=max(x["h"] for x in h[anchor_i:reclaim_i+1])
        leg=max(0.0,leg_end-origin)
        fibs=[(1.272,origin+1.272*leg),(1.618,origin+1.618*leg)]
    else:
        origin=h[anchor_i]["h"]
        leg_end=min(x["l"] for x in h[anchor_i:reclaim_i+1])
        leg=max(0.0,origin-leg_end)
        fibs=[(1.272,origin-1.272*leg),(1.618,origin-1.618*leg)]

    fib_tol=.25*atr
    candidates=[]
    for z in zones:
        dist=sign*(z["price"]-entry)
        rr=dist/risk
        # TP1 must sit materially in profit but before TP2.
        before_tp2=(z["price"]<tp2-.10*risk) if direction=="LONG" else (z["price"]>tp2+.10*risk)
        if rr<.65 or not before_tp2:
            continue
        near=[(ratio,px) for ratio,px in fibs if abs(z["price"]-px)<=fib_tol]
        score=z["base_score"]+(1 if near else 0)
        # Accept either a real liquidity cluster or pivot+Fib confluence.
        strong_liq=("LIQUIDITY_CLUSTER" in z["types"] and z["base_score"]>=2)
        fib_confluence=bool(near and z["base_score"]>=1)
        if not (strong_liq or fib_confluence):
            continue
        candidates.append((rr,z,score,near))

    if candidates:
        rr,z,score,near=min(candidates,key=lambda x:x[0])
        ratio=near[0][0] if near else None
        return z["price"],{"method":"LIQUIDITY_FIB_CONFLUENCE","score":score,"fib_ratio":ratio,
                           "zone_types":sorted(z["types"]),"rr":rr},fibs

    # Robust fallback when no meaningful pre-TP2 confluence exists.
    base_rr=sign*(tp2-entry)/risk
    rr=max(.75,min(1.0,base_rr/2))
    px=entry+sign*rr*risk
    return px,{"method":"ADAPTIVE_R_FALLBACK","score":0,"fib_ratio":None,"zone_types":[],"rr":rr},fibs

def local(h,d,cfg=None):
    cfg=params(LOCAL_DEFAULTS,cfg)
    x=d[-1]; r30=x["c"]/d[-31]["c"]-1
    L=x["c"]>=x["ema20"] or r30<=-.03; S=x["c"]<=x["ema20"] or r30>=.03
    direction=("LONG" if x["c"]>=x["ema20"] else "SHORT") if L and S else ("LONG" if L else "SHORT" if S else "NEUTRAL")
    cur=h[-1]; A=cur["atr"]; current=h[-13:-1]
    sup,res,er,valid=range_stats(current,A,cfg)
    anchor=None; reclaim=None; test=None; state="RANGE" if valid else "NO VALID RANGE"

    # Search recent candidate anchors. Every anchor freezes its own preceding 12 closed 4H bars.
    for ai in range(max(12,len(h)-40),len(h)):
        a=h[ai]; aa=a["atr"]
        if not aa:continue
        fp=h[ai-12:ai]; fs,fr,fer,fvalid=range_stats(fp,aa,cfg)
        if not fvalid:continue
        pen=(fs-a["l"]) if direction=="LONG" else (a["h"]-fr)
        if not (.02*aa<=pen<=cfg["penetration_max"]*aa):continue
        ri=reclaim_index(h,ai,fs if direction=="LONG" else fr,direction,3)
        if ri is None:continue
        # Anchor is the most extreme bar from penetration through reclaim.
        ext=min(range(ai,ri+1),key=lambda k:h[k]["l"]) if direction=="LONG" else max(range(ai,ri+1),key=lambda k:h[k]["h"])
        anchor=(ext,fs,fr,fer,ai); reclaim=ri

    if anchor:
        ai,sup,res,er,penetration_i=anchor; a=h[ai]; state="ANCHOR/RECLAIM"
        for j in range(reclaim+1,min(len(h),reclaim+17)):
            q=h[j]
            if not q["atr"] or not q["ssma"] or not q["vsma"]:continue
            if direction=="LONG":
                ok=q["l"]>a["l"] and q["l"]<=sup+cfg["test_overlap_atr"]*q["atr"] and q["spread"]<=cfg["test_spread_max"]*q["ssma"] and (q["v"]<=cfg["test_volume_max"]*a["v"] or q["v"]<=cfg["test_volume_max"]*q["vsma"]) and q["clv"]>=.35
            else:
                ok=q["h"]<a["h"] and q["h"]>=res-cfg["test_overlap_atr"]*q["atr"] and q["spread"]<=cfg["test_spread_max"]*q["ssma"] and (q["v"]<=cfg["test_volume_max"]*a["v"] or q["v"]<=cfg["test_volume_max"]*q["vsma"]) and q["clv"]<=.65
            if ok:
                test=j
                break

    entry=stop=tp1=tp2=rr=None; tp1_meta=None; tp3_fib_refs=None; actionable=False; filters={}; invalid=False
    if test is not None:
        q=h[test]; a=h[anchor[0]]; da=d[-1]["atr"]; age=len(h)-1-test
        slope=(d[-1]["ema20"]-d[-11]["ema20"])/(10*da); gap=abs(d[-1]["ema20"]-d[-1]["ema50"])
        penetration=(sup-a["l"])/q["atr"] if direction=="LONG" else (a["h"]-res)/q["atr"]
        if direction=="LONG":
            entry=q["h"]+cfg["entry_buffer_atr"]*q["atr"]; stop=a["l"]-cfg["stop_buffer_atr"]*q["atr"]; tp2=res
            tp1,tp1_meta,tp3_fib_refs=local_liquidity_fib_tp1(h,direction,anchor[0],reclaim,test,entry,stop,sup,res)
            rr=(tp2-entry)/(entry-stop) if entry>stop else -99
            filters={"penetration":penetration>=cfg["penetration_min"],"rr":cfg["rr_long_min"]<=rr<=cfg["rr_long_max"],"distance":tp2-entry<=cfg["target_distance_atr"]*q["atr"],"return30":r30>=cfg["return30_min"],"ema_gap":gap<=cfg["ema_gap_atr_max"]*da}
        else:
            entry=q["l"]-cfg["entry_buffer_atr"]*q["atr"]; stop=a["h"]+cfg["stop_buffer_atr"]*q["atr"]; tp2=sup
            tp1,tp1_meta,tp3_fib_refs=local_liquidity_fib_tp1(h,direction,anchor[0],reclaim,test,entry,stop,sup,res)
            rr=(entry-tp2)/(stop-entry) if stop>entry else -99
            filters={"penetration":penetration>=cfg["penetration_min"],"rr":cfg["rr_short_min"]<=rr<=cfg["rr_short_max"],"slope":slope>-.01,"distance":entry-tp2<=cfg["target_distance_atr"]*q["atr"],"return30":r30<=-cfg["return30_min"],"ema_gap":gap<=cfg["ema_gap_atr_max"]*da}
        invalid=pretrigger_invalid(h,test+1,len(h)-1,sup,res,q["atr"]) if test+1<len(h) else False
        actionable=all(filters.values()) and age<=cfg["trigger_window"] and not invalid
        state="INVALID" if invalid else ("ENTRY READY" if actionable else ("EXPIRED" if age>cfg["trigger_window"] else "FILTERED"))

    return {"direction":direction,"state":state,"range_valid":valid,"support":sup if valid or anchor else None,"resistance":res if valid or anchor else None,
            "efficiency_ratio":round(er,5),"anchor_open_ms":h[anchor[0]]["t"] if anchor else None,
            "reclaim_open_ms":h[reclaim]["t"] if reclaim is not None else None,"test_open_ms":h[test]["t"] if test is not None else None,
            "entry":entry,"stop":stop,"tp1":tp1,"tp2":tp2,"tp1_meta":tp1_meta,"tp3_fib_refs":tp3_fib_refs,
            "rr":rr,"filters":filters,"pretrigger_invalid":invalid,"actionable":actionable,
            "management":{"tp_policy":"LIQUIDITY_FIB_CONFLUENCE","tp1_fraction":0.30,"stop_after_tp1":"BE",
                          "tp2_fraction":0.30,"stop_after_tp2":tp1,"runner_fraction":0.40,
                          "runner":"4H confirmed-pivot trailing","tp3_fib_refs":"context-only"}}

def structural(d,h,cfg=None):
    cfg=params(STRUCT_DEFAULTS,cfg)
    hi,lo=pivots(d); seq=[]
    for i in range(50,len(d)):
        x=d[i]
        if not x["atr"] or not x["ssma"] or not x["vsma"]:continue
        r=x["c"]/d[i-30]["c"]-1; slope=(x["ema20"]-d[i-10]["ema20"])/(10*x["atr"])
        acc=sum((r<=-.08,x["c"]<x["ema20"]<x["ema50"],slope<=-.10))>=2
        dist=sum((r>=.08,x["c"]>x["ema20"]>x["ema50"],slope>=.10))>=2
        low=x["l"]<=min(z["l"] for z in d[i-19:i+1]); high=x["h"]>=max(z["h"] for z in d[i-19:i+1])
        climax=x["spread"]>=cfg["climax_spread_min"]*x["ssma"] and x["v"]>=cfg["climax_volume_min"]*x["vsma"]
        if acc and low and climax and x["clv"]>=.35:seq.append(("ACC",i))
        if dist and high and climax and x["clv"]<=.65:seq.append(("DIST",i))

    best=None
    for typ,sc in seq:
        opp=hi if typ=="ACC" else lo
        # First qualifying opposite confirmed pivot 3-15 daily bars after climax.
        ar=None
        for j in opp:
            if sc+3<=j<=sc+15:
                move=(d[j]["h"]-d[sc]["l"]) if typ=="ACC" else (d[sc]["h"]-d[j]["l"])
                if move>=max(.04*d[sc]["c"],1.5*d[sc]["atr"]):
                    ar=j; break
        if ar is None:continue

        st=None
        for j in range(ar+3,min(len(d),ar+31)):
            q=d[j]
            near=q["l"]<=d[sc]["l"]+1.1*q["atr"] if typ=="ACC" else q["h"]>=d[sc]["h"]-1.1*q["atr"]
            beyond=q["c"]>=d[sc]["l"]-.4*q["atr"] if typ=="ACC" else q["c"]<=d[sc]["h"]+.4*q["atr"]
            if near and beyond and q["v"]<=d[sc]["v"] and q["spread"]<=d[sc]["spread"]:
                st=j; break
        if st is None:continue

        # Structural boundaries = medians of confirmed pivot clusters within 1 daily ATR
        # of the preliminary SC/ST support and AR/BC resistance seeds.
        A=d[-1]["atr"]; age=len(d)-1-sc; window=d[sc:]
        seed_s=min(d[sc]["l"],d[st]["l"]) if typ=="ACC" else d[ar]["l"]
        seed_r=d[ar]["h"] if typ=="ACC" else max(d[sc]["h"],d[st]["h"])
        low_prices=[d[j]["l"] for j in lo if sc<=j<len(d) and abs(d[j]["l"]-seed_s)<=A]
        high_prices=[d[j]["h"] for j in hi if sc<=j<len(d) and abs(d[j]["h"]-seed_r)<=A]
        # SC/ST and AR/BC are legitimate structural observations even when not pivots.
        low_prices += [seed_s]; high_prices += [seed_r]
        low_prices.sort(); high_prices.sort()
        sup=low_prices[len(low_prices)//2] if len(low_prices)%2 else (low_prices[len(low_prices)//2-1]+low_prices[len(low_prices)//2])/2
        res=high_prices[len(high_prices)//2] if len(high_prices)%2 else (high_prices[len(high_prices)//2-1]+high_prices[len(high_prices)//2])/2
        if sup>=res:continue

        inside=sum(sup-A<=q["c"]<=res+A for q in window)/len(window)
        touches_s=sum(q["l"]<=sup+A for q in window); touches_r=sum(q["h"]>=res-A for q in window)
        valid=18<=age<=105 and res-sup>=2.5*A and inside>=.60 and touches_s>=2 and touches_r>=2
        internal=sum(sc<j<len(d)-1 for j in hi+lo)
        phase="A"
        if valid and len(d)-1-ar>=5 and internal>=2:phase="B"

        anchor=reclaim=test=None; breakout=None; lps=None
        # Only inspect 4H bars that overlap the active structural range age.
        for ai in range(max(1,len(h)-160),len(h)):
            a=h[ai]; aa=a["atr"]
            if not aa or a["ssma"] is None or a["vsma"] is None:continue
            pen=(sup-a["l"]) if typ=="ACC" else (a["h"]-res)
            if cfg["penetration_min"]*aa<=pen<=cfg["penetration_max"]*aa:
                ri=reclaim_index(h,ai,sup if typ=="ACC" else res,"LONG" if typ=="ACC" else "SHORT",2)
                if ri is not None:
                    ext=min(range(ai,ri+1),key=lambda k:h[k]["l"]) if typ=="ACC" else max(range(ai,ri+1),key=lambda k:h[k]["h"])
                    anchor=ext; reclaim=ri
            if typ=="ACC" and a["c"]>=res+.25*aa and a["spread"]>=1.3*a["ssma"] and a["v"]>=1.2*a["vsma"]:breakout=ai
            if typ=="DIST" and a["c"]<=sup-.25*aa and a["spread"]>=1.3*a["ssma"] and a["v"]>=1.2*a["vsma"]:breakout=ai

        if anchor is not None:
            a=h[anchor]
            for j in range(reclaim+1,min(len(h),reclaim+9)):
                q=h[j]
                if typ=="ACC":
                    ok=q["l"]>a["l"] and q["l"]<=sup+q["atr"] and q["spread"]<=cfg["test_spread_max"]*q["ssma"] and (q["v"]<=cfg["test_volume_anchor_max"]*a["v"] or q["v"]<=cfg["test_volume_sma_max"]*q["vsma"]) and q["clv"]>=.5
                else:
                    ok=q["h"]<a["h"] and q["h"]>=res-q["atr"] and q["spread"]<=cfg["test_spread_max"]*q["ssma"] and (q["v"]<=cfg["test_volume_anchor_max"]*a["v"] or q["v"]<=cfg["test_volume_sma_max"]*q["vsma"]) and q["clv"]<=.5
                if ok:test=j; break
            if test is not None:phase="C"

        # LPS/LPSY: first confirmed directional pivot 2-12 bars after SOS/SOW.
        if breakout is not None:
            hp,lp=pivots(h)
            candidates=lp if typ=="ACC" else hp
            for j in candidates:
                if breakout+2<=j<=min(len(h)-2,breakout+12):
                    if typ=="ACC" and h[j]["l"]>=res-h[j]["atr"]:lps=j; break
                    if typ=="DIST" and h[j]["h"]<=sup+h[j]["atr"]:lps=j; break
            phase="D"

        entry=stop=target=rr=None; actionable=False; trigger_expires_open_ms=None
        if test is not None:
            q=h[test]; a=h[anchor]
            if typ=="ACC":
                entry=q["h"]+cfg["entry_buffer_atr"]*q["atr"]; stop=a["l"]-cfg["stop_buffer_atr"]*q["atr"]; target=res
                rr=(target-entry)/(entry-stop) if entry>stop else -99
            else:
                entry=q["l"]-cfg["entry_buffer_atr"]*q["atr"]; stop=a["h"]+cfg["stop_buffer_atr"]*q["atr"]; target=sup
                rr=(entry-target)/(stop-entry) if stop>entry else -99
            actionable=rr>=cfg["rr_min"] and len(h)-1-test<=cfg["trigger_window"]
            exp=min(len(h)-1,test+cfg["trigger_window"]); trigger_expires_open_ms=h[exp]["t"]

        state="VALID RANGE" if valid else "PRELIMINARY"
        if not valid and phase in ("B","C","D"):state="INVALID"
        best={"bias":"ACCUMULATION" if typ=="ACC" else "DISTRIBUTION","phase":phase,"state":state,
              "support":sup,"resistance":res,"sc_bc_open_ms":d[sc]["t"],"ar_open_ms":d[ar]["t"],"st_open_ms":d[st]["t"],
              "anchor_open_ms":h[anchor]["t"] if anchor is not None else None,
              "reclaim_open_ms":h[reclaim]["t"] if reclaim is not None else None,
              "test_open_ms":h[test]["t"] if test is not None else None,
              "breakout_open_ms":h[breakout]["t"] if breakout is not None else None,
              "lps_lpsy_open_ms":h[lps]["t"] if lps is not None else None,
              "entry":entry,"stop":stop,"target":target,"rr":rr,"trigger_expires_open_ms":trigger_expires_open_ms,
              "actionable":bool(valid and actionable)}
    return best or {"bias":"NONE","phase":"NONE","state":"NO STRUCTURAL SEQUENCE","support":None,"resistance":None,"actionable":False}

def main():
    out={"version":5,"strategy":"Wyckoff Alert v1.6 CONSERVATIVE","market":"Binance Spot fallback","generated_at_ms":int(datetime.now(timezone.utc).timestamp()*1000),"symbols":{}}
    for s in SYMBOLS:
        d=enrich(bars(s,"1d",200)); h=enrich(bars(s,"4h",800))
        val={"1d_rows":len(d),"4h_rows":len(h),"1d_unique":len({x["t"] for x in d}),"4h_unique":len({x["t"] for x in h}),
             "1d_gaps":sum(d[i]["t"]-d[i-1]["t"]!=86400000 for i in range(1,len(d))),
             "4h_gaps":sum(h[i]["t"]-h[i-1]["t"]!=14400000 for i in range(1,len(h))),
             "latest_1d_open_ms":d[-1]["t"],"latest_4h_open_ms":h[-1]["t"]}
        A=quantize_signal_levels(structural(d,h),"A",s); B=quantize_signal_levels(local(h,d),"B",s)
        out["symbols"][s]={"validation":val,"last_closed_4h_price":h[-1]["c"],"track_a":A,"track_b":B,"actionable":bool(A["actionable"] or B["actionable"])}
    OUT.write_text(json.dumps(out,ensure_ascii=False,separators=(",",":")))
    print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
