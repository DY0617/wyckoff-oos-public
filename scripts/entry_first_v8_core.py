"""Entry First v8: 4 causal price-structure entries, fixed 2R exit, no DCA.

Original liquidity sweep / CHoCH / breakout-retest research. Does NOT
reproduce proprietary methods and does NOT place live orders.
"""
from bisect import bisect_right
from collections import defaultdict,Counter
from datetime import datetime, timezone
import statistics

MODES=("sweep","choch","breakout_retest","sweep_choch","sweep_choch_retest")
START_EQUITY=20000.
PARAMS={
    "h4_structure_lookback":60,"sweep_buffer_atr":0.10,
    "sweep_reclaim_atr":0.05,"sweep_clv":0.55,
    "choch_break_atr":0.08,"choch_clv":0.60,
    "retest_touch_atr":0.15,"retest_reclaim_atr":0.10,"retest_clv":0.60,
    "sweep_choch_expiry_1h":36,"breakout_retest_expiry_1h":16,
    "risk_fraction":0.005,"max_parallel":3,
    "notional_limit_per_position":0.70,
    "stop_atr_buffer":0.20,"stop_min_atr":0.65,"stop_max_atr":3.50,
    "entry_chase_limit_atr":0.75,
    "target_r":2.0,
    "max_hold_bars":{"crypto":120,"stock":35},
}


def pivot_at(bars,j,key):
    """j only becomes known after two bars to its right have CLOSED."""
    if j<2 or j+2>=len(bars):return False
    z=bars[j][key]
    return all((z>bars[k][key] if key=="h" else z<bars[k][key])
               for k in (j-2,j-1,j+1,j+2))


def confirmed_pivots(bars):
    """At hour i close, most recent pivot confirmed using bars <= i."""
    high=[];low=[];last_hi=last_lo=None
    for i in range(len(bars)):
        j=i-2
        if j>=2:
            if pivot_at(bars,j,"h"):last_hi=bars[j]["h"]
            if pivot_at(bars,j,"l"):last_lo=bars[j]["l"]
        high.append(last_hi);low.append(last_lo)
    return high,low


def h4_sweeps(pack,market):
    """Freeze latest PIVOT confirmed before signal candle, not a future one."""
    hh=pack["h4"];out=[]
    for i in range(25,len(hh)):
        x=hh[i]; atr=x.get("atr14")
        if not atr or atr<=0 or x["h"]<=x["l"]:
            continue
        prior_low=prior_high=None
        for j in range(i-3,max(1,i-3-PARAMS["h4_structure_lookback"]),-1):
            if prior_low is None and pivot_at(hh,j,"l"):prior_low=hh[j]["l"]
            if prior_high is None and pivot_at(hh,j,"h"):prior_high=hh[j]["h"]
            if prior_low is not None and prior_high is not None:break
        candidates=[("LONG",1)] if market=="stock" else [("LONG",1),("SHORT",-1)]
        for side,sign in candidates:
            level=prior_low if sign>0 else prior_high
            if level is None:continue
            extreme=x["l"] if sign>0 else x["h"]
            clv=(x["c"]-x["l"])/(x["h"]-x["l"]) if sign>0 else (x["h"]-x["c"])/(x["h"]-x["l"])
            if (sign*(level-extreme)>=PARAMS["sweep_buffer_atr"]*atr and
                sign*(x["c"]-level)>=PARAMS["sweep_reclaim_atr"]*atr and
                clv>=PARAMS["sweep_clv"]):
                out.append({"side":side,"sign":sign,"t":x["ct"],
                            "extreme":extreme,"level":level,"atr4":atr,"close":x["c"]})
    return out


def emit_signal(result,mode,source,bars,signal_index,anchor,kind,level=None):
    if signal_index+1>=len(bars):return
    closed=bars[signal_index]
    atr=closed.get("atr14")
    if not atr or atr<=0:return
    t_next=bars[signal_index+1]["t"]
    result[mode].setdefault(t_next,{
        "side":source["side"],"sign":source["sign"],
        "anchor":anchor,"entry_atr":atr,
        "source_close":closed["c"],"signal_t":closed["ct"],
        "kind":kind,"structure_level":level,
    })


def precompute_signals(pack,market):
    """Only completed candles may transition the per-symbol state machine.

    Sweep alone enters the immediately following 1H OPEN after 4H close.
    CHoCH detects a crossing of a PREVIOUSLY confirmed 1H pivot.
    Retest must touch and RECLAIM that same break level at a LATER 1H
    close, then executes at the next 1H OPEN. No same-bar foresight.
    """
    h=pack["hour"]
    result={mode:{} for mode in MODES}
    if len(h)<25:return result
    pivot_high,pivot_low=confirmed_pivots(h)
    opens=[b["t"] for b in h]
    sweep_events=defaultdict(list)
    for sw in h4_sweeps(pack,market):
        j=bisect_right(opens,sw["t"])
        if j>=len(h):continue
        t=opens[j]
        sweep_events[j].append(sw)
        # This sweep's 4H candle IS closed before the entry OPEN.
        # A pre-entry 1H ATR is available from the preceding 1H candle.
        atr=h[j-1].get("atr14") if j>=1 else None
        if atr and atr>0:
            result["sweep"].setdefault(t,{
                "side":sw["side"],"sign":sw["sign"],"anchor":sw["extreme"],
                "entry_atr":atr,"source_close":sw["close"],
                "signal_t":sw["t"],"kind":"sweep","structure_level":sw["level"]
            })
    watch_sweep={}
    watch_retest={}
    watch_combo_retest={}
    for i in range(25,len(h)-1):
        x=h[i];prev=h[i-1]
        # Sweep candidates become actionable only once their 4H signal
        # candle has closed; on this hour close they may seed combos.
        for sw in sweep_events.get(i,[]):
            watch_sweep[sw["sign"]]=(sw,i+PARAMS["sweep_choch_expiry_1h"])
        for sign in (-1,1):
            if market=="stock" and sign<0:continue
            if sign in watch_sweep and i>watch_sweep[sign][1]:
                watch_sweep.pop(sign,None)
            for store in (watch_retest,watch_combo_retest):
                if sign in store and i>store[sign]["expiry"]:
                    store.pop(sign,None)
            # Evaluate retests of PREVIOUS breakouts first. A breakout and
            # a retest can never be counted in the same 1H candle.
            for name,store in (("breakout_retest",watch_retest),
                               ("sweep_choch_retest",watch_combo_retest)):
                w=store.get(sign)
                if w is None or i<=w["break_i"]:continue
                atr=x.get("atr14")
                if not atr or atr<=0 or x["h"]<=x["l"]:continue
                extreme=x["l"] if sign>0 else x["h"]
                clv=((x["c"]-x["l"])/(x["h"]-x["l"]) if sign>0
                     else (x["h"]-x["c"])/(x["h"]-x["l"]))
                if (sign*(w["level"]-extreme)>=-PARAMS["retest_touch_atr"]*atr and
                    sign*(x["c"]-w["level"])>=PARAMS["retest_reclaim_atr"]*atr and
                    clv>=PARAMS["retest_clv"]):
                    anchor=(min(z["l"] for z in h[max(0,i-7):i+1]) if sign>0
                            else max(z["h"] for z in h[max(0,i-7):i+1]))
                    if name=="sweep_choch_retest":
                        anchor=(min(anchor,w["anchor"]) if sign>0
                                else max(anchor,w["anchor"]))
                    emit_signal(result,name,w,h,i,anchor,name,w["level"])
                    store.pop(sign,None)
            # New CHoCH breakout: take a PIVOT CONFIRMED BEFORE prior bar
            # so both the prior close and current close see the same level.
            atr=x.get("atr14")
            level=(pivot_high[i-1] if sign>0 else pivot_low[i-1])
            if not atr or atr<=0 or level is None or x["h"]<=x["l"]:continue
            clv=((x["c"]-x["l"])/(x["h"]-x["l"]) if sign>0
                 else (x["h"]-x["c"])/(x["h"]-x["l"]))
            broken=(sign*(x["c"]-level)>=PARAMS["choch_break_atr"]*atr and
                    sign*(prev["c"]-level)<=0 and clv>=PARAMS["choch_clv"])
            if not broken:continue
            source={"side":"LONG" if sign>0 else "SHORT","sign":sign}
            anchor=(min(z["l"] for z in h[max(0,i-7):i+1]) if sign>0
                    else max(z["h"] for z in h[max(0,i-7):i+1]))
            emit_signal(result,"choch",source,h,i,anchor,"choch",level)
            watch_retest[sign]={"side":source["side"],"sign":sign,
                 "break_i":i,"expiry":i+PARAMS["breakout_retest_expiry_1h"],
                 "level":level,"anchor":anchor}
            sw_pair=watch_sweep.get(sign)
            if sw_pair and i>bisect_right(opens,sw_pair[0]["t"])-1:
                sw=sw_pair[0]
                combo_anchor=(min(anchor,sw["extreme"]) if sign>0
                              else max(anchor,sw["extreme"]))
                emit_signal(result,"sweep_choch",source,h,i,combo_anchor,
                            "sweep_choch",level)
                watch_combo_retest[sign]={"side":source["side"],"sign":sign,
                  "break_i":i,"expiry":i+PARAMS["breakout_retest_expiry_1h"],
                  "level":level,"anchor":combo_anchor}
                watch_sweep.pop(sign,None)
    return result


def open_trade(sym,mode,sig,bar,equity,cost):
    """Entry at next OPEN; keep total ex-ante loss <=0.5% incl 10bp fees."""
    sign=sig["sign"];px=bar["o"];atr=sig["entry_atr"]
    if not atr or atr<=0 or px<=0 or equity<=0:return None,"invalid_prices"
    if sign*(px-sig["source_close"])>PARAMS["entry_chase_limit_atr"]*atr:
        return None,"too_late"
    stop=sig["anchor"]-sign*PARAMS["stop_atr_buffer"]*atr
    dist=sign*(px-stop)
    if stop<=0 or not PARAMS["stop_min_atr"]*atr<=dist<=PARAMS["stop_max_atr"]*atr:
        return None,"bad_stop_geometry"
    budget=PARAMS["risk_fraction"]*equity
    worst_per_unit=dist+.001*(px+stop)
    qty=min(budget/worst_per_unit,
            equity*PARAMS["notional_limit_per_position"]/px)
    if qty<=0:return None,"zero_qty"
    return {
        "symbol":sym,"mode":mode,"kind":sig["kind"],"side":sig["side"],
        "sign":sign,"entry":px,"entry_t":bar["t"],"signal_t":sig["signal_t"],
        "stop":stop,"target":px+sign*PARAMS["target_r"]*dist,
        "qty":qty,"risk_price":dist,"risk_budget":budget,
        "fees":qty*px*cost,"funding":0.,"age":0,
        "mae_r":0.,"mfe_r":0.,"structure_level":sig["structure_level"]
    },"accepted"


def update_excursions(p,bar,exit_reason=None,exit_price=None):
    sign=p["sign"];entry=p["entry"];r=p["risk_price"]
    if exit_reason=="GAP_STOP":
        p["mae_r"]=max(p["mae_r"],max(0.,sign*(entry-exit_price)/r))
        return
    if exit_reason=="STOP":
        # Stop-first: do not claim the favorable wick happened BEFORE stop.
        adverse=max(0.,sign*(entry-exit_price)/r)
        p["mae_r"]=max(p["mae_r"],adverse)
        return
    adverse=(bar["l"] if sign>0 else bar["h"])
    favorable=(bar["h"] if sign>0 else bar["l"])
    p["mae_r"]=max(p["mae_r"],max(0.,sign*(entry-adverse)/r))
    pfav=(exit_price if exit_reason=="TP_2R" else favorable)
    p["mfe_r"]=max(p["mfe_r"],max(0.,sign*(pfav-entry)/r))


def finish(p,price,t,reason,cost):
    pnl=p["sign"]*p["qty"]*(price-p["entry"])-p["fees"]-p["funding"]-p["qty"]*price*cost
    return {
        "symbol":p["symbol"],"mode":p["mode"],"side":p["side"],
        "entry_t":p["entry_t"],"exit_t":t,"entry":p["entry"],
        "exit":price,"stop":p["stop"],"target":p["target"],
        "reason":reason,"risk_budget":p["risk_budget"],
        "pnl":pnl,"r":pnl/(p["qty"]*p["risk_price"]),
        "net_r_budget":pnl/p["risk_budget"],
        "mae_r":p["mae_r"],"mfe_r":p["mfe_r"],
        "fees":p["fees"]+p["qty"]*price*cost,"funding":p["funding"],
        "signal_t":p["signal_t"],"kind":p["kind"]
    }


def update_position(p,b,market,cost,entry_bar=False):
    p["age"]+=1
    sign=p["sign"]
    if not entry_bar and sign*(b["o"]-p["stop"])<=0:
        update_excursions(p,b,"GAP_STOP",b["o"])
        return finish(p,b["o"],b["t"],"GAP_STOP",cost)
    adverse=(b["l"] if sign>0 else b["h"])
    if sign*(adverse-p["stop"])<=0:
        update_excursions(p,b,"STOP",p["stop"])
        return finish(p,p["stop"],b["ct"],"STOP",cost)
    favorable=(b["h"] if sign>0 else b["l"])
    if not entry_bar and sign*(favorable-p["target"])>=0:
        update_excursions(p,b,"TP_2R",p["target"])
        return finish(p,p["target"],b["ct"],"TP_2R",cost)
    if p["age"]>=PARAMS["max_hold_bars"][market]:
        update_excursions(p,b,"TIME",b["c"])
        return finish(p,b["c"],b["ct"],"TIME",cost)
    update_excursions(p,b)
    return None


def evaluate(trades,curve,rejects,candidates):
    gains=[t["pnl"] for t in trades if t["pnl"]>0]
    losses=[t["pnl"] for t in trades if t["pnl"]<0]
    peak=START_EQUITY;dd=0.
    for point in curve:
        peak=max(peak,point["equity"])
        dd=max(dd,(peak-point["equity"])/peak)
    by_year=defaultdict(list);by_sym=defaultdict(list)
    for x in trades:
        by_year[str(datetime.fromtimestamp(x["entry_t"]/1000,timezone.utc).year)].append(x)
        by_sym[x["symbol"]].append(x)
    return {
       "trade_count":len(trades),"candidates":candidates,
       "rejects":dict(rejects),
       "return_pct":((curve[-1]["equity"]/START_EQUITY-1)*100 if curve else 0.),
       "net_pnl":sum(x["pnl"] for x in trades),
       "pf":sum(gains)/(-sum(losses)) if losses else None,
       "win_rate":len(gains)/len(trades) if trades else None,
       "avg_net_r":statistics.fmean(x["r"] for x in trades) if trades else None,
       "max_mtm_dd_pct":dd*100,
       "avg_mae_r":statistics.fmean(x["mae_r"] for x in trades) if trades else None,
       "median_mae_r":statistics.median(x["mae_r"] for x in trades) if trades else None,
       "avg_mfe_r":statistics.fmean(x["mfe_r"] for x in trades) if trades else None,
       "median_mfe_r":statistics.median(x["mfe_r"] for x in trades) if trades else None,
       "pct_mae_le_half_r":sum(x["mae_r"]<=.5 for x in trades)/len(trades) if trades else None,
       "tp2_rate":sum(x["reason"]=="TP_2R" for x in trades)/len(trades) if trades else None,
       "stops":sum("STOP" in x["reason"] for x in trades),
       "fees":sum(x["fees"] for x in trades),"funding":sum(x["funding"] for x in trades),
       "by_year":{k:{"n":len(v),"pnl":sum(x["pnl"] for x in v)} for k,v in sorted(by_year.items())},
       "by_symbol":{k:{"n":len(v),"pnl":sum(x["pnl"] for x in v),
                       "avg_mae_r":statistics.fmean(x["mae_r"] for x in v)}
                    for k,v in sorted(by_sym.items())},
       "reasons":dict(Counter(x["reason"] for x in trades))
    }


def simulate(packs,market,mode,start_ms,end_ms,cost=.0006,funding=None,trade_symbols=None):
    if mode not in MODES:raise ValueError(mode)
    symbols=(sorted(s for s in packs if s!="SPY") if market=="stock" else
             sorted(trade_symbols or ["BTCUSDT","ETHUSDT"]))
    if not all(s in packs for s in symbols):raise ValueError("unavailable universe")
    sigs={s:precompute_signals(packs[s],market)[mode] for s in symbols}
    events=defaultdict(list)
    for s in symbols:
        for b in packs[s]["hour"]:
            if start_ms<=b["t"]<end_ms:
                events[b["t"]].append((s,b))
    rates=funding or {}
    ftimes={s:[t for t,_ in rates.get(s,[])] for s in symbols}
    positions={};marks={};last_end={s:start_ms-1 for s in symbols}
    curve=[];trades=[];cash=START_EQUITY;rejects=Counter();candidate_count=0
    for t in sorted(events):
        bars=sorted(events[t],key=lambda pair:pair[0])
        gapped=set()
        for s,b in bars:
            p=positions.get(s)
            if p and p["sign"]*(b["o"]-p["stop"])<=0:
                # Exit fee/funding and mark are settled at gap OPEN.
                trade=update_position(p,b,market,cost)
                if trade is None:raise AssertionError("missed gap stop")
                cash+=trade["pnl"];trades.append(trade)
                del positions[s];gapped.add(s)
        entered=set()
        for s,b in bars:
            sig=sigs[s].get(t)
            if not sig or s in positions or s in gapped:continue
            candidate_count+=1
            if len(positions)>=PARAMS["max_parallel"]:
                rejects["concurrency"]+=1;continue
            floating=sum(p["sign"]*p["qty"]*(marks.get(k,p["entry"])-p["entry"])
                         -p["fees"]-p["funding"] for k,p in positions.items())
            equity=cash+floating
            p,reason=open_trade(s,mode,sig,b,equity,cost)
            if p is None:
                rejects[reason]+=1;continue
            positions[s]=p;entered.add(s)
        for s,b in bars:
            p=positions.get(s)
            if p is not None:
                done=update_position(p,b,market,cost,entry_bar=s in entered)
                if market=="crypto":
                    after=(t-1 if s in entered else max(last_end[s],p["entry_t"]))
                    low=bisect_right(ftimes[s],after)
                    high=bisect_right(ftimes[s],b["ct"])
                    for _,rate in rates.get(s,[])[low:high]:
                        p["funding"]+=p["sign"]*p["qty"]*b["c"]*rate
                    if done is not None:
                        # Recalculate PnL after current-hour settled funding.
                        done["funding"]=p["funding"]
                        done["pnl"]=(p["sign"]*p["qty"]*(done["exit"]-p["entry"])
                                     -done["fees"]-p["funding"])
                        done["r"]=done["pnl"]/(p["qty"]*p["risk_price"])
                        done["net_r_budget"]=done["pnl"]/p["risk_budget"]
                if done is not None:
                    cash+=done["pnl"];trades.append(done)
                    del positions[s]
            marks[s]=b["c"];last_end[s]=b["ct"]
        total_float=sum(p["sign"]*p["qty"]*(marks.get(s,p["entry"])-p["entry"])
                        -p["fees"]-p["funding"] for s,p in positions.items())
        curve.append({"t":max(b["ct"] for _,b in bars),"equity":cash+total_float,
                      "realized":cash,"floating":total_float,
                      "open":len(positions)})
    if curve:
        close_t=curve[-1]["t"]
        for s,p in list(positions.items()):
            trade=finish(p,marks.get(s,p["entry"]),close_t,"END_OF_DATA",cost)
            cash+=trade["pnl"];trades.append(trade)
        curve[-1].update({"equity":cash,"realized":cash,"floating":0.,"open":0})
    trades.sort(key=lambda x:(x["exit_t"],x["symbol"]))
    return {"market":market,"mode":mode,"trades":trades,"curve":curve,
            "metrics":evaluate(trades,curve,rejects,candidate_count)}
