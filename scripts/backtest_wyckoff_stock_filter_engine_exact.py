import json,sys,math
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).parent))
import wyckoff_status as w
from wyckoff_structural_state import PersistentStructuralWyckoff

SYMS=("BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT"); ROOT=Path("data/spot"); OUT=Path("data/validation/_unused_runner_sweep_engine.json")
_CACHE={}

def dataset(sym):
    if sym not in _CACHE:
        D=w.enrich(raw(sym,"1d")); H=w.enrich(raw(sym,"4h")); M=raw(sym,"15m")
        _CACHE[sym]=(D,H,M)
    return _CACHE[sym]
CAP=20000.0; RISK=400.0

def raw(sym,tf):
    a=json.loads((ROOT/sym/f"{tf}.json").read_text())
    return [{"t":int(x[0]),"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5])} for x in a]

def symbol_filters(sym):
    try:
        x=json.loads((ROOT/sym/"filters.json").read_text())
        return float(x.get("tick_size") or 0),float(x.get("step_size") or 0),float(x.get("min_qty") or 0)
    except Exception:
        return 0.0,0.0,0.0

def floor_step(x,step):
    return math.floor((x+1e-12)/step)*step if step else x

def ceil_step(x,step):
    return math.ceil((x-1e-12)/step)*step if step else x

def quantize_setup(direction,entry,stop,target,tick):
    if not tick:return entry,stop,target
    if direction=="LONG":
        return ceil_step(entry,tick),floor_step(stop,tick),floor_step(target,tick)
    return floor_step(entry,tick),ceil_step(stop,tick),ceil_step(target,tick)

def simulate(sym, a_params=None, b_params=None, start_ms=None, end_ms=None, fee_bps=0.0, slippage_bps=0.0, a_mode="snapshot", b_runner_mode="pivot", b_scale_mode="30_30_40", setup_filter=None, trigger_filter=None):
    D,H,M=dataset(sym); tick,qty_step,min_qty=symbol_filters(sym)
    a_cfg=w.params(w.STRUCT_DEFAULTS,a_params)
    b_cfg=w.params(w.LOCAL_DEFAULTS,b_params)
    mode_map={"persistent":"v1","persistent_v2":"v2","persistent_v3":"v3","persistent_v4":"v4"}
    a_engine=PersistentStructuralWyckoff(D,H,a_cfg,mode=mode_map[a_mode]) if a_mode in mode_map else None
    import bisect
    mt=[x["t"] for x in M]; hc=[x.get("ct",x["t"]+4*60*60*1000-1) for x in H]; dc=[x.get("ct",x["t"]+24*60*60*1000-1) for x in D]
    trades=[]; seen=set(); pending={}; phase_counts={}; setup_counts={"A":0,"B":0}; setup_audit=[]
    start_t=max(D[0]["t"],H[0]["t"])

    def finish_trade(p,trig, cutoff_ms=None):
        direction=p["direction"]; entry=p["entry"]; stop0=p["stop"]; tp2=p["target"]
        fib1618=None
        if p.get("track")=="B":
            refs=p.get("tp3_fib_refs") or []
            fib1618=next((px for ratio,px in refs if abs(float(ratio)-1.618)<1e-9),None)
            if fib1618 is not None and tick:
                fib1618=floor_step(fib1618,tick) if direction=="LONG" else ceil_step(fib1618,tick)
            # A runner target is only valid if it actually lies beyond TP2.
            if fib1618 is not None and not ((direction=="LONG" and fib1618>tp2) or (direction=="SHORT" and fib1618<tp2)):
                fib1618=None
        risk=abs(entry-stop0)
        if risk<=0:return False
        sign=1 if direction=="LONG" else -1

        # Locate the actual first 15m candle inside the triggering 4H bar that touches entry.
        # This prevents stop/TP events from being counted before the entry was actually reachable.
        trigger_4h_open=H[trig]["t"]; trigger_4h_end=H[trig].get("ct",trigger_4h_open+4*60*60*1000-1)+1
        mi=bisect.bisect_left(mt,trigger_4h_open); entry_i=None
        while mi<len(M) and M[mi]["t"]<trigger_4h_end:
            z=M[mi]
            zclose=z["t"]+15*60*1000-1
            if cutoff_ms is not None and zclose>cutoff_ms:break
            touched=(z["l"]<=entry<=z["h"])
            if touched:
                entry_i=mi; break
            mi+=1
        if entry_i is None:return False
        if trigger_filter is not None and not trigger_filter(sym,p,M[entry_i]["t"]):
            return "FILTERED"

        raw_size=RISK/risk
        size=floor_step(raw_size,qty_step) if qty_step else raw_size
        if size<=0 or (min_qty and size<min_qty):return False

        entry_cost=size*entry*(fee_bps+slippage_bps)/10000.0
        realized=-entry_cost
        midpoint=(entry+tp2)/2
        if p["track"]=="B" and p.get("tp1") is not None:
            raw_tp1=p["tp1"]
            tp1=(floor_step(raw_tp1,tick) if direction=="LONG" else ceil_step(raw_tp1,tick)) if tick else raw_tp1
        else:
            tp1=(floor_step(midpoint,tick) if direction=="LONG" else ceil_step(midpoint,tick)) if tick else midpoint
        # Track B three-stage management:
        # TP1 = liquidity/Fibonacci confluence target from the setup, take 30% and move remaining stop to break-even.
        # TP2 = structural target, take another 30% and move remaining stop to TP1.
        # Final 40% remains a 4H-pivot-trailed runner.
        # Track A keeps its previously validated management unchanged.
        if p["track"]!="B" and sign*(tp1-entry)<risk:
            tp1=None
        if p["track"]=="B" and b_scale_mode=="fixed_50_50":
            tp1_fraction=.50
            tp2_fraction=.50
        elif p["track"]=="B" and b_scale_mode=="fixed_tp2":
            tp1=None
            tp1_fraction=0.0
            tp2_fraction=1.0
        elif p["track"]=="B" and b_scale_mode=="50_50":
            tp1_fraction=.50
            tp2_fraction=.50
        elif p["track"]=="B" and b_scale_mode=="20_30_50":
            tp1_fraction=.20 if tp1 is not None else 0.0
            tp2_fraction=.30 if tp1 is not None else .50
        elif p["track"]=="B" and b_scale_mode=="25_25_50":
            tp1_fraction=.25 if tp1 is not None else 0.0
            tp2_fraction=.25 if tp1 is not None else .50
        elif p["track"]=="B" and b_scale_mode=="15_25_60":
            tp1_fraction=.15 if tp1 is not None else 0.0
            tp2_fraction=.25 if tp1 is not None else .40
        elif p["track"]=="B" and b_scale_mode=="10_30_60":
            tp1_fraction=.10 if tp1 is not None else 0.0
            tp2_fraction=.30 if tp1 is not None else .40
        else:
            tp1_fraction=.30 if tp1 is not None else 0.0
            tp2_fraction=.30 if tp1 is not None else .60
        remain=1.0; events=[]; stop=stop0; tp1_done=False; tp2_done=False; fib_partial_done=False
        entry_fill_t=M[entry_i]["t"]; mi=entry_i

        # 15m path drives stops/targets. Track B: TP1=>BE, TP2=>TP1. Track A keeps +1R-close=>BE.
        # Same-entry-candle ambiguity is resolved conservatively: after assuming entry was touched,
        # STOP is evaluated before profit targets. BE only activates from a CLOSED 15m candle.
        last_z=None
        while mi<len(M):
            z=M[mi]; zclose=z["t"]+15*60*1000-1
            if cutoff_ms is not None and zclose>cutoff_ms:break
            if z["t"]>=H[-1]["t"]+4*60*60*1000:break
            last_z=z
            hit_stop=z["l"]<=stop if direction=="LONG" else z["h"]>=stop
            if hit_stop:
                realized += remain*sign*(stop-entry)*size - remain*size*stop*(fee_bps+slippage_bps)/10000.0
                events.append({"type":"BE" if stop==entry else "STOP","t":z["t"],"price":stop,"fraction":remain})
                remain=0; break
            if not tp1_done and tp1 is not None and ((direction=="LONG" and z["h"]>=tp1) or (direction=="SHORT" and z["l"]<=tp1)):
                realized += tp1_fraction*sign*(tp1-entry)*size - tp1_fraction*size*tp1*(fee_bps+slippage_bps)/10000.0
                remain-=tp1_fraction; tp1_done=True
                events.append({"type":"TP1","t":z["t"],"price":tp1,"fraction":tp1_fraction})
                # For Track B, TP1 locks the remaining position at break-even.
                if p["track"]=="B" and b_scale_mode not in ("fixed_50_50","fixed_tp2") and ((direction=="LONG" and stop<entry) or (direction=="SHORT" and stop>entry)):
                    stop=entry
                    events.append({"type":"BE_MOVE","t":z["t"],"price":entry,"cause":"TP1"})
            if not tp2_done and ((direction=="LONG" and z["h"]>=tp2) or (direction=="SHORT" and z["l"]<=tp2)):
                realized += tp2_fraction*sign*(tp2-entry)*size - tp2_fraction*size*tp2*(fee_bps+slippage_bps)/10000.0
                remain-=tp2_fraction; tp2_done=True
                events.append({"type":"TP2","t":z["t"],"price":tp2,"fraction":tp2_fraction})
                # For Track B, TP2 locks the 40% runner at TP1 before 4H pivot trailing takes over.
                if p["track"]=="B" and b_scale_mode not in ("fixed_50_50","fixed_tp2") and tp1 is not None and ((direction=="LONG" and stop<tp1) or (direction=="SHORT" and stop>tp1)):
                    stop=tp1
                    events.append({"type":"STOP_TO_TP1","t":z["t"],"price":tp1,"cause":"TP2"})
                # If TP2 fully closes the position (e.g. 50/50 or 100%-TP2 research modes),
                # stop scanning immediately so holding time and subsequent setup availability are correct.
                if remain<=1e-12:
                    remain=0
                    break
            if p["track"]!="B":
                one_r=entry+sign*risk
                # Preserve validated Track A management: +1R on a closed 15m candle => BE.
                be_tightens=(direction=="LONG" and stop<entry and z["c"]>=one_r) or (direction=="SHORT" and stop>entry and z["c"]<=one_r)
                if be_tightens:
                    stop=entry; events.append({"type":"BE_MOVE","t":z["t"],"price":entry,"cause":"PLUS_1R_CLOSE"})
            # Optional Track-B Fib 1.618 runner exit experiment.
            # STOP is always evaluated first at the top of the bar, so same-bar
            # ambiguity remains conservative.
            if p["track"]=="B" and tp2_done and remain>0 and fib1618 is not None and b_runner_mode in ("fib1618_full","fib1618_half"):
                hit_fib=(direction=="LONG" and z["h"]>=fib1618) or (direction=="SHORT" and z["l"]<=fib1618)
                allow_fib=(b_runner_mode=="fib1618_full") or (b_runner_mode=="fib1618_half" and not fib_partial_done)
                if hit_fib and allow_fib:
                    frac=remain if b_runner_mode=="fib1618_full" else min(.20,remain)
                    realized += frac*sign*(fib1618-entry)*size - frac*size*fib1618*(fee_bps+slippage_bps)/10000.0
                    remain-=frac
                    events.append({"type":"FIB1618_FULL" if b_runner_mode=="fib1618_full" else "FIB1618_PARTIAL",
                                   "t":z["t"],"price":fib1618,"fraction":frac})
                    if b_runner_mode=="fib1618_half":
                        fib_partial_done=True
                    if remain<=1e-12:
                        remain=0
                        break

            # After TP2, update the remaining runner stop from confirmed 3-bar 4H pivots.
            if tp2_done and remain>0 and b_runner_mode in ("pivot","fib1618_half","fib1618_full"):
                hclose=zclose
                hk=bisect.bisect_right(hc,hclose)-1
                if hk>=2:
                    piv=hk-1; atr=H[piv].get("atr")
                    if atr:
                        if direction=="LONG" and H[piv]["l"]<H[piv-1]["l"] and H[piv]["l"]<H[piv+1]["l"]:
                            ns=H[piv]["l"]-.3*atr
                            if tick:ns=floor_step(ns,tick)
                            if ns>stop:stop=ns; events.append({"type":"TRAIL","t":z["t"],"price":stop})
                        if direction=="SHORT" and H[piv]["h"]>H[piv-1]["h"] and H[piv]["h"]>H[piv+1]["h"]:
                            ns=H[piv]["h"]+.3*atr
                            if tick:ns=ceil_step(ns,tick)
                            if ns<stop:stop=ns; events.append({"type":"TRAIL","t":z["t"],"price":stop})
            mi+=1

        if remain>0:
            mark=(last_z["c"] if last_z is not None else entry)
            realized += remain*sign*(mark-entry)*size - remain*size*mark*(fee_bps+slippage_bps)/10000.0
            events.append({"type":"OPEN_MARK","t":last_z["t"] if last_z is not None else entry_fill_t,"price":mark,"fraction":remain})
            reason="OPEN_MARK"
        else:
            reason=events[-1]["type"]
        exit_t=events[-1]["t"] if events else entry_fill_t
        trades.append({"track":p["track"],"direction":direction,"source":p.get("source"),"entry_t":entry_fill_t,
                       "trigger_4h_open_ms":trigger_4h_open,"exit_t":exit_t,
                       "entry":entry,"stop":stop0,"target":tp2,"tp1":tp1,"fib1618":fib1618,"runner_mode":b_runner_mode,
                       "size":size,"reason":reason,"pnl":realized,"r":realized/RISK,"events":events})
        return True

    for hi in range(12,len(H)):
        close_t=H[hi].get("ct",H[hi]["t"]+4*60*60*1000-1)
        if H[hi]["t"]<start_t: continue
        if end_ms is not None and H[hi]["t"] > end_ms: break
        di=bisect.bisect_right(dc,close_t)-1
        if di<30: continue

        # First advance setups that were already known before this bar.
        for key,p in list(pending.items()):
            if hi<=p["seen_hi"]:continue
            z=H[hi]
            touched=(z["l"]<=p["entry"]<=z["h"])
            if touched:
                ok=finish_trade(p,hi,end_ms)
                if ok=="FILTERED":
                    p["audit"]["triggered"]=False
                    p["audit"]["reason"]="TRIGGER_FILTERED"
                    p["audit"]["trigger_open_ms"]=z["t"]
                    setup_audit.append(p["audit"]); del pending[key]; continue
                if ok:
                    p["audit"]["triggered"]=True
                    p["audit"]["reason"]="TRIGGERED_EXACT_TOUCH"
                    p["audit"]["trigger_open_ms"]=z["t"]
                    setup_audit.append(p["audit"]); del pending[key]; continue
                # 4H range contained entry but no 15m candle actually traded through it.
                # Keep the setup pending until a later exact touch, invalidation, or expiry.

            # Pre-trigger invalidation. Track B invalidates on either frozen-range side.
            # Persistent Track A invalidates only on the adverse side; favorable-side
            # strength is allowed to become SOS/SOW.
            if p["track"]=="B":
                sup=p.get("support"); res=p.get("resistance"); atr=z.get("atr")
                invalid=bool(atr and sup is not None and res is not None and
                             (z["c"]<sup-.75*atr or z["c"]>res+.75*atr))
                is_out=bool(sup is not None and res is not None and (z["c"]<sup or z["c"]>res))
                p["outside_count"]=p.get("outside_count",0)+1 if is_out else 0
                if invalid or p["outside_count"]>=2:
                    p["audit"]["reason"]="PRETRIGGER_INVALIDATED"; p["audit"]["invalidated_open_ms"]=z["t"]
                    setup_audit.append(p["audit"]); del pending[key]; continue
            elif p["track"]=="A" and a_mode in ("persistent","persistent_v2","persistent_v3","persistent_v4"):
                sup=p.get("support"); res=p.get("resistance"); atr=z.get("atr")
                source=p.get("source") or ""
                # Phase-D v3 entries require the old range edge to keep acting as
                # support/resistance right up to entry. A close materially back
                # inside the range invalidates the backup before it triggers.
                if a_mode in ("persistent_v3","persistent_v4") and "CONFIRMED_LPS" in source:
                    if p["direction"]=="LONG":
                        invalid=bool(atr and res is not None and z["c"]<res-.15*atr)
                    else:
                        invalid=bool(atr and sup is not None and z["c"]>sup+.15*atr)
                    if invalid:
                        p["audit"]["reason"]="PHASE_D_REENTRY_INVALIDATED"; p["audit"]["invalidated_open_ms"]=z["t"]
                        setup_audit.append(p["audit"]); del pending[key]; continue
                if p["direction"]=="LONG":
                    hard=bool(atr and sup is not None and z["c"]<sup-.75*atr)
                    adverse=bool(sup is not None and z["c"]<sup)
                else:
                    hard=bool(atr and res is not None and z["c"]>res+.75*atr)
                    adverse=bool(res is not None and z["c"]>res)
                p["outside_count"]=p.get("outside_count",0)+1 if adverse else 0
                if hard or p["outside_count"]>=2:
                    p["audit"]["reason"]="STRUCTURE_INVALIDATED"; p["audit"]["invalidated_open_ms"]=z["t"]
                    setup_audit.append(p["audit"]); del pending[key]; continue

            if hi>=p["expiry_hi"]:
                p["audit"]["reason"]="EXPIRED"; p["audit"]["expiry_open_ms"]=z["t"]
                setup_audit.append(p["audit"]); del pending[key]

        ds=D[max(0,di-199):di+1]; hs=H[max(0,hi-799):hi+1]
        A=a_engine.update(di,hi) if a_engine is not None else w.structural(ds,hs,a_params)
        B=w.local(hs,ds,b_params)
        phase_counts[A.get("phase","NONE")]=phase_counts.get(A.get("phase","NONE"),0)+1
        candidates=[]
        if A.get("actionable") and A.get("entry") is not None:candidates.append(("A",A))
        if B.get("actionable") and B.get("entry") is not None:candidates.append(("B",B))
        if len(candidates)>1:
            ad="LONG" if A["bias"]=="ACCUMULATION" else "SHORT"
            if B["direction"]==ad:candidates=[candidates[0]]

        for track,s in candidates:
            direction=("LONG" if A["bias"]=="ACCUMULATION" else "SHORT") if track=="A" else B["direction"]
            # Structural setups may carry their own objective (e.g. Phase-D
            # measured-move target). Fall back to the opposite range boundary
            # only for legacy/snapshot setups that do not expose one.
            target=s.get("target")
            if target is None:
                target=s.get("resistance") if direction=="LONG" else s.get("support")
            if target is None:continue
            entry,stop,target=quantize_setup(direction,s["entry"],s["stop"],target,tick)
            key=(track,direction,s.get("test_open_ms"),round(entry,8),round(stop,8))
            if key in seen:continue
            seen.add(key); setup_counts[track]+=1
            audit={"track":track,"direction":direction,"source":s.get("source"),"test_open_ms":s.get("test_open_ms"),
                   "entry":entry,"stop":stop,"target":target,"tp1":s.get("tp1") if track=="B" else None,
                   "tp1_meta":s.get("tp1_meta") if track=="B" else None,
                   "tp3_fib_refs":s.get("tp3_fib_refs") if track=="B" else None,
                   "seen_at_4h_open_ms":H[hi]["t"],"triggered":False,"reason":None}
            test_t=s.get("test_open_ms"); ti=next((k for k,x in enumerate(H) if x["t"]==test_t),None)
            if ti is None:
                audit["reason"]="TEST_NOT_FOUND"; setup_audit.append(audit); continue
            window=12 if track=="A" else int(b_cfg["trigger_window"])
            expiry_hi=min(ti+window,len(H)-1)
            # If discovered after part of the formal trigger window elapsed, only remaining bars are eligible.
            if hi>=expiry_hi:
                audit["reason"]="EXPIRED_WHEN_DISCOVERED"; audit["expiry_open_ms"]=H[expiry_hi]["t"]; setup_audit.append(audit); continue
            probe={"track":track,"direction":direction,"source":s.get("source"),"entry":entry,"stop":stop,"target":target,
                   "tp1":s.get("tp1") if track=="B" else None,"support":s.get("support"),"resistance":s.get("resistance"),
                   "seen_hi":hi,"seen_at_4h_open_ms":H[hi]["t"]}
            if setup_filter is not None and not setup_filter(sym,probe,H[hi]["t"]):
                audit["reason"]="SETUP_FILTERED"; setup_audit.append(audit); continue
            pending[key]={"track":track,"direction":direction,"source":s.get("source"),"entry":entry,"stop":stop,"target":target,
                          "tp1":s.get("tp1") if track=="B" else None,"tp1_meta":s.get("tp1_meta") if track=="B" else None,
                          "tp3_fib_refs":s.get("tp3_fib_refs") if track=="B" else None,
                          "support":s.get("support"),"resistance":s.get("resistance"),"outside_count":0,
                          "seen_hi":hi,"expiry_hi":expiry_hi,"audit":audit}

    # Resolve setups whose trigger window extends beyond the dataset.
    for p in pending.values():
        p["audit"]["reason"]="DATA_END"; setup_audit.append(p["audit"])

    uniq={}
    for t in trades:
        k=(t["track"],t["direction"],t["entry_t"],round(t["entry"],8),round(t["stop"],8)); uniq[k]=t
    raw_trades=sorted(uniq.values(),key=lambda x:x["entry_t"])
    suppression={"ab_12h":0,"same_symbol_overlap":0}

    # Hybrid rule: if A and B trigger in the same direction within 12h, keep A.
    twelve_h=12*60*60*1000
    a_triggers=[t for t in raw_trades if t["track"]=="A"]
    deduped=[]
    for t in raw_trades:
        if t["track"]=="B" and any(a["direction"]==t["direction"] and abs(a["entry_t"]-t["entry_t"])<=twelve_h for a in a_triggers):
            suppression["ab_12h"]+=1; continue
        deduped.append(t)

    # One-way invariant: one symbol can have only one open position at a time,
    # regardless of direction. A new same-symbol signal is skipped until the
    # existing position has fully closed.
    active_until=-1; trades=[]
    for t in sorted(deduped,key=lambda x:x["entry_t"]):
        if t["entry_t"]<=active_until:
            suppression["same_symbol_overlap"]+=1; continue
        trades.append(t); active_until=t["exit_t"]

    if start_ms is not None:
        trades=[t for t in trades if t["entry_t"] >= start_ms]
    if end_ms is not None:
        trades=[t for t in trades if t["entry_t"] <= end_ms]
    closed=[t for t in trades if t["reason"]!="OPEN_MARK"]; eq=CAP; peak=CAP; mdd=0
    for t in sorted(closed,key=lambda x:x["exit_t"]):
        eq+=t["pnl"]; peak=max(peak,eq); mdd=max(mdd,(peak-eq)/peak if peak else 0)
    eval_start=start_ms if start_ms is not None else start_t
    eval_end=end_ms if end_ms is not None else H[-1]["t"]
    replay_name=("persistent_structural_state_v4" if a_mode=="persistent_v4" else ("persistent_structural_state_v3" if a_mode=="persistent_v3" else ("persistent_structural_state_v2" if a_mode=="persistent_v2" else ("persistent_structural_state_v1" if a_mode=="persistent" else "persistent_pending_4h_v2"))))
    return {"period":{"start_ms":eval_start,"end_ms":eval_end},"replay":replay_name,"phase_snapshots":phase_counts,
            "setups":setup_counts,"triggered":len(trades),"closed":len(closed),"wins":sum(t["pnl"]>0 for t in closed),
            "losses":sum(t["pnl"]<0 for t in closed),"win_rate":sum(t["pnl"]>0 for t in closed)/len(closed) if closed else None,
            "net_pnl":sum(t["pnl"] for t in closed),"return_on_20k":sum(t["pnl"] for t in closed)/CAP,
            "avg_r":sum(t["r"] for t in closed)/len(closed) if closed else None,"max_drawdown":mdd,
            "by_track":{q:{"closed":sum(t["track"]==q and t["reason"]!="OPEN_MARK" for t in trades),
                           "wins":sum(t["track"]==q and t["reason"]!="OPEN_MARK" and t["pnl"]>0 for t in trades),
                           "net_pnl":sum(t["pnl"] for t in trades if t["track"]==q and t["reason"]!="OPEN_MARK")} for q in ("A","B")},
            "hybrid_suppression":suppression,"setup_audit":setup_audit,
            "untriggered_reasons":{r:sum(1 for a in setup_audit if not a["triggered"] and a["reason"]==r)
                                   for r in sorted(set(a["reason"] for a in setup_audit if not a["triggered"]))},
            "trades":trades}

def run_all(a_params=None,b_params=None,start_ms=None,end_ms=None,fee_bps=0.0,slippage_bps=0.0,a_mode="snapshot"):
    return {s:simulate(s,a_params,b_params,start_ms,end_ms,fee_bps,slippage_bps,a_mode) for s in SYMS}

out={"version":9,"strategy":"Wyckoff v1.5 corrected execution/backtest","assumptions":["Spot OHLCV","fixed $20,000 reference capital","fixed $400 risk/trade","default main run has no fees/slippage; optimizer may inject costs","Binance tick/step precision when filters.json is available","entry timing resolved to first touching closed 15m candle inside trigger 4H","same-entry-candle ambiguity resolves STOP first","Track B: TP1 midpoint takes 30% then moves stop to break-even; TP2 takes 30% then moves stop to TP1; final 40% is a 4H-pivot runner","Track B pretrigger invalidation enforced","Track A priority within 12h and one open position per symbol regardless of direction","Track B TP1-triggered break-even and TP2-triggered TP1 stop; Track A closed-15m +1R break-even; confirmed 3-bar 4H pivot trailing after TP2"],"symbols":{}}
if __name__=="__main__":
 for s in SYMS:
    print("backtesting",s,flush=True); out["symbols"][s]=simulate(s)
 OUT.write_text(json.dumps(out,separators=(",",":")))
 print(json.dumps({s:{k:v for k,v in x.items() if k!="trades"} for s,x in out["symbols"].items()},indent=2))
