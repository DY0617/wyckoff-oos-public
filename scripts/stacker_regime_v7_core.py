"""Stacker v7: volatility states, market shocks and causal 4H candle rejection; OOS symbols.

Seven frozen research arms share exactly the same completed-4H BB signal,
structural SL, EMA target and conservative 1H fills. No real orders.
"""
from bisect import bisect_right
from collections import defaultdict,Counter
from datetime import datetime,timezone
import statistics

import arm_v1_swing_core as arm
import stacker_structure_v2_core as structure
import stacker_rotation_v4_core as execution

MODES=("control","asset_vol_skip","benchmark_vol_skip",
       "either_vol_skip","bb_rejection","asset_vol_rejection",
       "shock_skip","graded_size")
INITIAL=20000.
MAX_CONCURRENT=2
VOL_OBS=80
VOL_UPPER_QUANTILE=.80
MIN_REWARD_TO_FIRST_STOP=.65
REJECTION_CLV=0.35
SHOCK_RANGE_TO_ATR=2.25
REDUCED_SIZE_ON_HIGH_VOL=0.50
REDUCED_SIZE_NEAR_HIGH_VOL=0.75
VOL_NEAR_QUANTILE_RATIO=0.85


def completed_h4_index(pack,t):
    """Most recent 4H bar closed STRICTLY BEFORE entry hour opens."""
    return bisect_right(pack["h4_closes"],t-1)-1


def vol_state(pack,t):
    i=completed_h4_index(pack,t)
    if i<VOL_OBS-1:return None
    rows=pack["h4"][i-VOL_OBS+1:i+1]
    readings=[x["atr14"]/x["c"] for x in rows
              if x.get("atr14") is not None and x["c"]>0]
    if len(readings)<VOL_OBS:return None
    readings.sort()
    current=pack["h4"][i]["atr14"]/pack["h4"][i]["c"]
    return {"current":current,"p80":readings[int((len(readings)-1)*VOL_UPPER_QUANTILE)],
            "high":current>readings[int((len(readings)-1)*VOL_UPPER_QUANTILE)]}


def signal_bar_state(pack, signal_t, sign):
    """Use EXACT completed 4H bar generating the Bollinger signal."""
    i=bisect_right(pack["h4_closes"],signal_t)-1
    if i<0 or pack["h4"][i]["ct"]!=signal_t:
        return None
    x=pack["h4"][i]
    spread=x["h"]-x["l"]
    if spread<=0 or not x.get("atr14"):
        return None
    directional_clv=((x["c"]-x["l"])/spread if sign>0
                     else (x["h"]-x["c"])/spread)
    return {"clv":directional_clv,
            "range_atr":spread/x["atr14"],
            "source_t":x["ct"]}


def entry_decision(mode,pack,bench,bar,sig,p):
    """Read only state closed PRIOR to current 1H entry OPEN."""
    if mode not in MODES:raise ValueError(mode)
    asset_v=benchmark_v=None
    if mode in ("asset_vol_skip","either_vol_skip",
                "asset_vol_rejection","graded_size"):
        asset_v=vol_state(pack,bar["t"])
        if asset_v is None:return False,0.,"asset_warmup"
    if mode in ("benchmark_vol_skip","either_vol_skip"):
        benchmark_v=vol_state(bench,bar["t"])
        if benchmark_v is None:return False,0.,"benchmark_warmup"
    if mode in ("asset_vol_skip","asset_vol_rejection","either_vol_skip") and asset_v["high"]:
        return False,0.,"asset_high_vol"
    if mode in ("benchmark_vol_skip","either_vol_skip") and benchmark_v["high"]:
        return False,0.,"benchmark_high_vol"
    if mode in ("bb_rejection","asset_vol_rejection","shock_skip"):
        state=signal_bar_state(pack,sig["signal_t"],p["sign"])
        if state is None:return False,0.,"no_signal_h4"
        if mode in ("bb_rejection","asset_vol_rejection") and state["clv"]<REJECTION_CLV:
            return False,0.,"no_reversal_wick"
        if mode=="shock_skip" and state["range_atr"]>SHOCK_RANGE_TO_ATR:
            return False,0.,"extreme_signal_range"
    if mode=="graded_size":
        if asset_v["high"]:return True,REDUCED_SIZE_ON_HIGH_VOL,"high_vol_half"
        if asset_v["current"]>asset_v["p80"]*VOL_NEAR_QUANTILE_RATIO:
            return True,REDUCED_SIZE_NEAR_HIGH_VOL,"near_high_vol_three_quarters"
    return True,1.,"accepted"


def scale_position(p,scale):
    """Reduce exposure WITHOUT moving the initial structural stop/TP."""
    if scale<=0 or scale>1:raise ValueError("invalid scale")
    if scale==1:return
    p["quantities"]=[q*scale for q in p["quantities"]]
    p["qty"]*=scale
    p["cost_basis"]*=scale
    p["fees"]*=scale
    p["max_risk_budget"]*=scale
    p["fills"][0]["qty"]*=scale


def report_metrics(trades,curve,checks,skip_counts,high_vol_scaled):
    d=execution.evaluate_metrics(trades,curve)
    d.update({
        "checked_signals":checks,
        "skips":dict(skip_counts),
        "lower_size_entries":high_vol_scaled,
        "win_loss_by_calendar_year":d["by_year"],
        "closed_trade_count":len(trades),
        "best10_pnl":sum(sorted((x["pnl"] for x in trades),reverse=True)[:10]),
        "worst10_pnl":sum(sorted((x["pnl"] for x in trades))[:10]),
    })
    return d


def simulate(packs,market,mode,start_ms,end_ms,fee=.0006,funding=None,trade_symbols=None):
    if mode not in MODES:raise ValueError(mode)
    benchmark=packs["SPY" if market=="stock" else "BTCUSDT"]
    syms=(sorted(x for x in packs if x!="SPY") if market=="stock" else
          sorted(trade_symbols or ["BTCUSDT","ETHUSDT"]))
    if not all(s in packs for s in syms):
        raise ValueError("missing requested trade universe in prepared data")
    signals={s:structure.build_signals(packs[s],benchmark,market,s,
                                        "sr_ema",start_ms,end_ms) for s in syms}
    events=defaultdict(list)
    for sym in syms:
        for bar in packs[sym]["hour"]:
            if start_ms<=bar["t"]<end_ms:events[bar["t"]].append((sym,bar))
    rates=funding or {}
    ftimes={s:[t for t,_ in rates.get(s,[])] for s in syms}
    last_close={s:start_ms-1 for s in syms}
    positions={};marks={};trades=[];curve=[]
    balance=INITIAL
    checks=0
    skips=Counter()
    hi_scaled=0
    for t in sorted(events):
        bars=sorted(events[t],key=lambda pair:pair[0])
        gapped=set()
        # Existing-position STOP GAPS take priority at this OPEN.
        for sym,bar in bars:
            p=positions.get(sym)
            if p is not None and p["sign"]*(bar["o"]-p["stop"])<=0:
                z=execution.finish(p,bar["o"],bar["t"],"GAP_STOP",fee)
                balance+=z["pnl"];trades.append(z)
                del positions[sym];gapped.add(sym)
                # Genuine stop gaps settle at OPEN before new entries.
        entered=set()
        # Only prior-closed indicator data + CURRENT OPEN may determine orders.
        for sym,bar in bars:
            sig=signals[sym].get(t)
            if not sig or sym in positions or sym in gapped:continue
            checks+=1
            if len(positions)>=MAX_CONCURRENT:
                skips["concurrency"]+=1;continue
            mark_pnl=sum(execution.mark_pnl(p,marks.get(k,p["avg"]))
                          for k,p in positions.items())
            equity=balance+mark_pnl
            if equity<=0:
                skips["no_equity"]+=1;continue
            p=execution.position_from_signal(sym,market,sig,bar["o"],t,equity,fee,mode="static")
            if p is None:
                skips["invalid_structure"]+=1;continue
            allowed,scale,label=entry_decision(mode,packs[sym],benchmark,bar,sig,p)
            if not allowed:
                skips[label]+=1;continue
            scale_position(p,scale)
            if scale<1:hi_scaled+=1
            p["mode"]="static"
            p["quality_variant"]=mode
            positions[sym]=p;entered.add(sym)
        for sym,bar in bars:
            p=positions.get(sym)
            if p is not None:
                closed=execution.process_bar(p,bar,market,"static",fee,packs[sym],
                                               entry_bar=sym in entered)
                if market=="crypto":
                    left=bisect_right(ftimes[sym],(t-1 if sym in entered else
                                         max(last_close[sym],p["entry_t"])))
                    right=bisect_right(ftimes[sym],bar["ct"])
                    for _,rate in rates.get(sym,[])[left:right]:
                        p["funding"]+=p["sign"]*p["qty"]*bar["c"]*rate
                    if closed is not None:
                        closed["funding"]=p["funding"]
                        closed["pnl"]=p["gross_realized"]-p["fees"]-p["funding"]
                        closed["r"]=closed["pnl"]/p["max_risk_budget"]
                if closed is not None:
                    closed["quality_variant"]=mode
                    trades.append(closed);balance+=closed["pnl"]
                    del positions[sym]

            marks[sym]=bar["c"]
            last_close[sym]=bar["ct"]
        floatpnl=sum(execution.mark_pnl(p,marks.get(sym,p["avg"]))
                        for sym,p in positions.items())
        curve.append({"t":max(b["ct"] for _,b in bars),
                      "equity":balance+floatpnl,"balance":balance,
                      "floating":floatpnl,"open_cycles":len(positions)})
    if curve:
        t=curve[-1]["t"]
        for sym,p in list(positions.items()):
            z=execution.finish(p,marks.get(sym,p["avg"]),t,"END_OF_DATA",fee)
            z["quality_variant"]=mode
            balance+=z["pnl"];trades.append(z)
        curve[-1].update({"equity":balance,"balance":balance,
                          "floating":0.,"open_cycles":0})
    trades.sort(key=lambda x:(x["exit_t"],x["symbol"]))
    return {"mode":mode,"market":market,"trades":trades,"curve":curve,
            "metrics":report_metrics(trades,curve,checks,skips,hi_scaled)}
