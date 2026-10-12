"""Stacker v5 — fresh 1H retest setup AFTER structural EMA profit exit.

The prior cycle is fully CLOSED at TP. Fresh reentry is an INDEPENDENT
trade with its own signal, stop, target, fee-inclusive size, and expiry.
Never widen the previous stop. No live execution or vendor code.
"""
from bisect import bisect_right
from collections import defaultdict,Counter
from datetime import datetime,timezone
import statistics

import stacker_rotation_v4_core as v4
import stacker_structure_v2_core as structure

START_EQUITY=20000.0
CHILD_RISK=0.00375
MAX_CONCURRENT=2
RETEST_ATR=1.0
WATCH_HOURS={"stock":14,"crypto":48}
CHILD_MAX_HOURS={"stock":21,"crypto":72}
CHILD_TP_R=2.0
CHILD_MIN_STOP_ATR=.75
CHILD_MAX_STOP_ATR=3.0
CHILD_GAP_ATR=.75
MODES=("control","retest","retest_htf","retest_htf_barrier")


def floating(p,price):
    if p["kind"]=="parent":
        return v4.mark_pnl(p,price)
    return p["sign"]*p["qty"]*(price-p["entry"])-p["fees"]-p["funding"]


def close_child(p,price,t,reason,cost):
    pnl=p["sign"]*p["qty"]*(price-p["entry"])-p["fees"]-p["funding"]-p["qty"]*price*cost
    return {"symbol":p["symbol"],"side":p["side"],"kind":"child",
            "entry_t":p["entry_t"],"exit_t":t,"entry":p["entry"],"exit":price,
            "reason":reason,"stop":p["stop"],"tp":p["tp"],
            "pnl":pnl,"r":pnl/p["risk_budget"],"risk_budget":p["risk_budget"],
            "fees":p["fees"]+p["qty"]*price*cost,"funding":p["funding"],
            "parent_tp_t":p["parent_tp_t"]}


def child_entry(symbol,b,previous,signal,equity,cost,mode,pack):
    """Executed only at next OPEN following a complete retest/confirmation bar."""
    sign=signal["sign"]
    atr=previous.get("atr14")
    entry=b["o"]
    if not atr or atr<=0 or entry<=0 or equity<=0:return None
    if sign*(entry-signal["close"])>CHILD_GAP_ATR*atr:return None
    x=pack["hour"]
    # Signal index is strictly PREVIOUS hour in the externally sequential runner.
    idx=signal["hour_index"]
    past=x[max(0,idx-5):idx+1]
    if len(past)<6:return None
    stop=(min(z["l"] for z in past)-.25*atr if sign>0
          else max(z["h"] for z in past)+.25*atr)
    distance=sign*(entry-stop)
    if stop<=0 or not (CHILD_MIN_STOP_ATR*atr<=distance<=CHILD_MAX_STOP_ATR*atr):
        return None
    target=entry+sign*CHILD_TP_R*distance
    if target<=0:return None
    if mode=="retest_htf_barrier":
        ss=v4.confirmed_structure_before(pack,b["t"])
        if ss is None:return None
        opposing=ss["pivot_high"] if sign>0 else ss["pivot_low"]
        # Only allow setup if nearest CONFIRMED opposing pivot is not
        # between entry and planned +1.5R target. If no pivot, skip.
        candidates=[sign*(v-entry) for v in opposing if sign*(v-entry)>0]
        if not candidates or min(candidates)<1.5*distance:
            return None
    maxbudget=CHILD_RISK*equity
    unitloss=distance + .001*(entry+stop)
    if unitloss<=0:return None
    qty=min(maxbudget/unitloss,.70*equity/entry)
    if qty<=0:return None
    return {"kind":"child","symbol":symbol,"side":signal["side"],"sign":sign,
            "entry_t":b["t"],"entry":entry,"stop":stop,"active_stop":stop,
            "tp":target,"rprice":distance,"qty":qty,
            "fees":qty*entry*cost,"funding":0.,"risk_budget":maxbudget,
            "hours":0,"parent_tp_t":signal["parent_tp_t"]}


def process_child(p,b,market,cost,entry_bar=False):
    p["hours"]+=1
    sign=p["sign"];stop=p["active_stop"]
    if not entry_bar and sign*(b["o"]-stop)<=0:
        return close_child(p,b["o"],b["t"],"GAP_STOP",cost)
    adverse=b["l"] if sign>0 else b["h"]
    if sign*(adverse-stop)<=0:
        return close_child(p,stop,b["ct"],"STOP",cost)
    favorable=b["h"] if sign>0 else b["l"]
    if not entry_bar and sign*(favorable-p["tp"])>=0:
        return close_child(p,p["tp"],b["ct"],"TP_2R",cost)
    if p["hours"]>=CHILD_MAX_HOURS[market]:
        return close_child(p,b["c"],b["ct"],"TIME",cost)
    # Confirm CLOSE beyond +1R before moving stop; effective NEXT candle.
    if sign*(b["c"]-p["entry"])>=p["rprice"]:
        p["active_stop"]=p["entry"]
    return None


def test_retest_signal(pack,i,watch,mode):
    """At fully CLOSED 1H candle i, propose a reentry no earlier than i+1."""
    h=pack["hour"]
    if i<21 or i+1>=len(h):return None
    b=h[i]
    if b["ct"]<=watch["tp_time"]:return None
    atr=b.get("atr14")
    if not atr or atr<=0:return None
    sign=watch["sign"]
    # Price must actually revisit frozen TP minus/plus original 1ATR.
    retest=watch["tp"]-sign*watch["atr"]*RETEST_ATR
    touch=(b["l"]<=retest) if sign>0 else (b["h"]>=retest)
    if not touch:return None
    spread=b["h"]-b["l"]
    if spread<=0:return None
    clv=((b["c"]-b["l"])/spread if sign>0 else
         (b["h"]-b["c"])/spread)
    ema=b.get("ema20")
    if ema is None or not (sign*(b["c"]-ema)>0 and
                           sign*(b["c"]-retest)>=.25*atr and clv>=.65):
        return None
    if mode in ("retest_htf","retest_htf_barrier") and not v4.trend_reentry_ok(
            pack,b["ct"]+1,sign):
        return None
    return {"side":watch["side"],"sign":sign,"close":b["c"],
            "hour_index":i,"parent_tp_t":watch["tp_time"],
            "signal_t":b["ct"],"valid_entry_t":h[i+1]["t"]}


def results_metrics(trades,curve,signals,missed):
    gains=[t["pnl"] for t in trades if t["pnl"]>0]
    losses=[t["pnl"] for t in trades if t["pnl"]<0]
    peak=START_EQUITY;dd=0.
    for c in curve:
        peak=max(peak,c["equity"])
        dd=max(dd,(peak-c["equity"])/peak)
    years=defaultdict(list)
    for t in trades:
        years[str(datetime.fromtimestamp(t["entry_t"]/1000,timezone.utc).year)].append(t)
    child=[t for t in trades if t["kind"]=="child"]
    parent=[t for t in trades if t["kind"]=="parent"]
    return {
      "trades":len(trades),"parents":len(parent),"children":len(child),
      "win_rate":len(gains)/len(trades) if trades else None,
      "net_pnl":sum(t["pnl"] for t in trades),
      "return_pct":(curve[-1]["equity"]/START_EQUITY-1)*100 if curve else 0,
      "pf":sum(gains)/-sum(losses) if losses else None,
      "max_mtm_dd_pct":dd*100,
      "total_fees":sum(t["fees"] for t in trades),
      "funding_total":sum(t["funding"] for t in trades),
      "parent_pnl":sum(t["pnl"] for t in parent),
      "child_pnl":sum(t["pnl"] for t in child),
      "child_pf":(sum(t["pnl"] for t in child if t["pnl"]>0) /
                  -sum(t["pnl"] for t in child if t["pnl"]<0)
                  if any(t["pnl"]<0 for t in child) else None),
      "confirmed_retests":signals,"failed_reentries":missed,
      "by_year":{year:{"trades":len(v),"pnl":sum(t["pnl"] for t in v),
                       "child_pnl":sum(t["pnl"] for t in v if t["kind"]=="child")}
                 for year,v in sorted(years.items())},
      "by_symbol":{s:{"n":sum(t["symbol"]==s for t in trades),
                        "pnl":sum(t["pnl"] for t in trades if t["symbol"]==s)}
                   for s in sorted(set(t["symbol"] for t in trades))},
      "exit_reason":dict(Counter(t["reason"] for t in trades))
    }


def simulate(packs,market,mode,start_ms,end_ms,cost=.0006,funding=None):
    if mode not in MODES:raise ValueError(mode)
    bench=packs["SPY" if market=="stock" else "BTCUSDT"]
    syms=sorted(s for s in packs if s!="SPY") if market=="stock" else ["BTCUSDT","ETHUSDT"]
    orig={s:structure.build_signals(packs[s],bench,market,s,"sr_ema",start_ms,end_ms)
          for s in syms}
    events=defaultdict(list)
    indexes={}
    for s in syms:
        indexes[s]={b["t"]:i for i,b in enumerate(packs[s]["hour"])}
        for b in packs[s]["hour"]:
            if start_ms<=b["t"]<end_ms:events[b["t"]].append((s,b))
    rates=funding or {}
    ftimes={s:[z[0] for z in rates.get(s,[])] for s in syms}
    positions={};watch={};pending={};last_close={s:start_ms-1 for s in syms}
    marks={};curve=[];trades=[];balance=START_EQUITY
    sigcount=missed=0
    for t in sorted(events):
        bars=sorted(events[t],key=lambda pair:pair[0])
        # Genuine stop GAPS are settled at OPEN, never retrospectively.
        gapclosed=set()
        for sym,b in bars:
            p=positions.get(sym)
            if p is not None and p["sign"]*(b["o"]-p.get("active_stop",p["stop"]))<=0:
                closed=(close_child(p,b["o"],b["t"],"GAP_STOP",cost)
                        if p["kind"]=="child" else
                        v4.finish(p,b["o"],b["t"],"GAP_STOP",cost))
                closed["kind"]=p["kind"]
                trades.append(closed);balance+=closed["pnl"]
                del positions[sym];gapclosed.add(sym)
        entered=set()
        for sym,b in bars:
            if sym in positions or sym in gapclosed or len(positions)>=MAX_CONCURRENT:
                continue
            eq=balance+sum(floating(p,marks.get(k,p.get("avg",p.get("entry"))))
                           for k,p in positions.items())
            if eq<=0:continue
            # Retest confirmation is a COMPLETED PREVIOUS 1H candle.
            is_child=(mode!="control" and sym in pending and
                      t==pending[sym]["valid_entry_t"])
            if is_child:
                signal=pending.pop(sym)
                new=child_entry(sym,b,packs[sym]["hour"][signal["hour_index"]],
                                signal,eq,cost,mode,packs[sym])
                if new is None:
                    missed+=1
                    continue
                positions[sym]=new;entered.add(sym);watch.pop(sym,None)
                continue
            sig=orig[sym].get(t)
            if sig is None:continue
            p=v4.position_from_signal(sym,market,sig,b["o"],t,eq,cost,mode="static")
            if p is None:continue
            p["kind"]="parent";p["mode"]="static"
            positions[sym]=p;entered.add(sym)
            # Each new independent parent supersedes stale retest watches.
            watch.pop(sym,None);pending.pop(sym,None)
        for sym,b in bars:
            p=positions.get(sym)
            if p is not None:
                closed=(process_child(p,b,market,cost,entry_bar=sym in entered)
                        if p["kind"]=="child" else
                        v4.process_bar(p,b,market,"static",cost,packs[sym],
                                       entry_bar=sym in entered))
                if market=="crypto":
                    after=(t-1 if sym in entered else max(last_close[sym],p["entry_t"]))
                    lo=bisect_right(ftimes[sym],after)
                    hi=bisect_right(ftimes[sym],b["ct"])
                    for _,rate in rates.get(sym,[])[lo:hi]:
                        p["funding"]+=p["sign"]*p.get("qty",0)*b["c"]*rate
                    if closed is not None:
                        closed["funding"]=p["funding"]
                        if p["kind"]=="parent":
                            closed["pnl"]=p["gross_realized"]-p["fees"]-p["funding"]
                        else:
                            closed["pnl"]=(p["sign"]*p["qty"]*(closed["exit"]-p["entry"])
                                           -closed["fees"]-p["funding"])
                        closed["r"]=closed["pnl"]/(
                            p["max_risk_budget"] if p["kind"]=="parent" else p["risk_budget"])
                if closed is not None:
                    closed["kind"]=p["kind"]
                    trades.append(closed);balance+=closed["pnl"]
                    del positions[sym]
                    if (mode!="control" and p["kind"]=="parent" and
                            closed["reason"]=="TP_FULL"):
                        watch[sym]={"side":p["side"],"sign":p["sign"],
                                    "tp":p["cycle_tp"],"atr":p["atr"],
                                    "tp_time":b["ct"],"bars_remaining":WATCH_HOURS[market]}
            marks[sym]=b["c"];last_close[sym]=b["ct"]
            # Any pending signal not executed at its one designated next
            # 1H bar OPEN is cancelled (e.g. concurrency / capital cap).
            if sym in pending and t>=pending[sym]["valid_entry_t"]:
                pending.pop(sym,None)
                missed+=1
            if mode=="control" or sym in positions or sym not in watch or sym in pending:
                continue
            w=watch[sym]
            if b["ct"]<=w["tp_time"]:continue
            w["bars_remaining"]-=1
            if w["bars_remaining"]<0:
                del watch[sym];continue
            sig=test_retest_signal(packs[sym],indexes[sym][t],w,mode)
            if sig is not None:
                sigcount+=1;pending[sym]=sig
                del watch[sym]
        float_pnl=sum(floating(p,marks.get(s,p.get("avg",p.get("entry"))))
                        for s,p in positions.items())
        curve.append({"t":max(x["ct"] for _,x in bars),"equity":balance+float_pnl,
                      "balance":balance,"floating":float_pnl,"open":len(positions)})
    if curve:
        last=curve[-1]["t"]
        for sym,p in list(positions.items()):
            px=marks.get(sym,p.get("avg",p.get("entry")))
            closed=(close_child(p,px,last,"END_OF_DATA",cost) if p["kind"]=="child"
                    else v4.finish(p,px,last,"END_OF_DATA",cost))
            closed["kind"]=p["kind"]
            trades.append(closed);balance+=closed["pnl"]
        curve[-1].update({"equity":balance,"balance":balance,"floating":0.,"open":0})
    trades.sort(key=lambda x:(x["exit_t"],x["symbol"]))
    return {"mode":mode,"market":market,"trades":trades,"curve":curve,
            "metrics":results_metrics(trades,curve,sigcount,missed)}
