"""Stacker v6: isolate ENTRY quality and risk policy, not more averaging.

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

MODES=("control","daily_trend","vol_skip","reward_floor",
       "vol_scale","loss_cooldown","quality_combo")
INITIAL=20000.
MAX_CONCURRENT=2
VOL_OBS=80
VOL_UPPER_QUANTILE=.80
MIN_REWARD_TO_FIRST_STOP=.65
COOLDOWN_AFTER_LOSSES=3
COOLDOWN_MARKET_BARS={"crypto":72,"stock":35}
VOL_HIGH_RISK_FRACTION=.50


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


def daily_trend_ok(pack,benchmark,bar,sign):
    """Prior completed day only, plus slope of asset EMA50 over five days."""
    d=arm.prev_daily(pack,bar["day"])
    b=arm.prev_daily(benchmark,bar["day"])
    if not d or not b:return False
    idx=pack["day_keys"].index(d["day"])
    if idx<5:return False
    old=pack["daily"][idx-5]
    values=(d.get("ema50"),d.get("ema200"),old.get("ema50"),
            b.get("ema50"),b.get("ema200"))
    if any(x is None for x in values):return False
    return (sign*(d["ema50"]-d["ema200"])>0 and
            sign*(d["ema50"]-old["ema50"])>0 and
            sign*(b["ema50"]-b["ema200"])>0)


def first_r_at_target(p):
    return p["sign"]*(p["tp"]-p["entry_price"])/(
        p["sign"]*(p["entry_price"]-p["stop"]))


def entry_decision(mode,pack,bench,bar,sig,p):
    """Return (admit, qty-scale, failure-label), no current OHLC high/low."""
    if mode not in MODES:raise ValueError(mode)
    need_daily=mode in ("daily_trend","quality_combo")
    need_vol=mode in ("vol_skip","vol_scale","quality_combo")
    need_rr=mode in ("reward_floor","quality_combo")
    if need_daily and not daily_trend_ok(pack,bench,bar,p["sign"]):
        return False,0.,"daily_trend"
    high=False
    if need_vol:
        vol=vol_state(pack,bar["t"])
        if vol is None:return False,0.,"vol_not_ready"
        high=vol["high"]
    if mode in ("vol_skip","quality_combo") and high:
        return False,0.,"high_vol"
    if need_rr and first_r_at_target(p)<MIN_REWARD_TO_FIRST_STOP:
        return False,0.,"target_too_close"
    scale=(VOL_HIGH_RISK_FRACTION if mode=="vol_scale" and high else 1.)
    return True,scale,"accepted"


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


def report_metrics(trades,curve,checks,skip_counts,high_vol_scaled,cooldowns):
    d=execution.evaluate_metrics(trades,curve)
    d.update({
        "checked_signals":checks,
        "skips":dict(skip_counts),
        "high_vol_scaled_entries":high_vol_scaled,
        "cooldown_events":cooldowns,
        "win_loss_by_calendar_year":d["by_year"],
        "closed_trade_count":len(trades),
        "best10_pnl":sum(sorted((x["pnl"] for x in trades),reverse=True)[:10]),
        "worst10_pnl":sum(sorted((x["pnl"] for x in trades))[:10]),
    })
    return d


def simulate(packs,market,mode,start_ms,end_ms,fee=.0006,funding=None):
    if mode not in MODES:raise ValueError(mode)
    benchmark=packs["SPY" if market=="stock" else "BTCUSDT"]
    syms=sorted(x for x in packs if x!="SPY") if market=="stock" else ["BTCUSDT","ETHUSDT"]
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
    streak=0
    cooldown_until=-1
    cooldowns=0
    for event_index,t in enumerate(sorted(events)):
        bars=sorted(events[t],key=lambda pair:pair[0])
        gapped=set()
        # Existing-position STOP GAPS take priority at this OPEN.
        for sym,bar in bars:
            p=positions.get(sym)
            if p is not None and p["sign"]*(bar["o"]-p["stop"])<=0:
                z=execution.finish(p,bar["o"],bar["t"],"GAP_STOP",fee)
                balance+=z["pnl"];trades.append(z)
                del positions[sym];gapped.add(sym)
                if z["pnl"]<0:
                    streak+=1
                else:streak=0
                if mode=="loss_cooldown" and streak>=COOLDOWN_AFTER_LOSSES:
                    cooldown_until=max(cooldown_until,event_index+
                                       COOLDOWN_MARKET_BARS[market])
                    cooldowns+=1;streak=0
        entered=set()
        # Only prior-closed indicator data + CURRENT OPEN may determine orders.
        for sym,bar in bars:
            sig=signals[sym].get(t)
            if not sig or sym in positions or sym in gapped:continue
            checks+=1
            if len(positions)>=MAX_CONCURRENT:
                skips["concurrency"]+=1;continue
            if mode=="loss_cooldown" and event_index<=cooldown_until:
                skips["cooldown"]+=1;continue
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
                    if closed["pnl"]<0:
                        streak+=1
                    else:streak=0
                    if mode=="loss_cooldown" and streak>=COOLDOWN_AFTER_LOSSES:
                        cooldown_until=max(cooldown_until,event_index+
                                           COOLDOWN_MARKET_BARS[market])
                        cooldowns+=1;streak=0
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
            "metrics":report_metrics(trades,curve,checks,skips,hi_scaled,cooldowns)}
