"""Original Stacker v3: structural TP -> partial realization -> rebuy -> bounded SL roll.

No proprietary AGOS code. Causal at 1H candle open; stress tested in independent
research branch, no exchange orders / Supabase / Telegram. All PnL incl OPEN
cycle realised parts + floating exposures; net liquidation cash at each hour.
"""
from bisect import bisect_right
from collections import defaultdict, Counter
from datetime import datetime,timezone
import statistics

import stacker_structure_v2_core as base

INITIAL=20000.0
MAX_REBUYS=2
PARTIAL=0.50
REBUY_DIST_ATR=1.0
RUNNER_TP_DIST_ATR=1.50
REBUY_WAIT_HOURS={"crypto":48,"stock":14}
STOP_EXTEND_ATR=0.25
STOP_MAX_DIST_ATR=8.0
MODES=("static","rotate_fixed","rotate_lower","rotate_support")


def mark_pnl(p, mark):
    return (p["gross_realized"] + p["sign"]*(p["qty"]*mark-p["cost_basis"])
            -p["fees"]-p["funding"])


def projected_floor(p,newstop,newqty=None,newbasis=None,newfees=None,newgross=None,fee=.001):
    qty=p["qty"] if newqty is None else newqty
    cb=p["cost_basis"] if newbasis is None else newbasis
    fees=p["fees"] if newfees is None else newfees
    gross=p["gross_realized"] if newgross is None else newgross
    return gross + p["sign"]*(qty*newstop-cb) - fees - p["funding"] - qty*newstop*fee


def position_from_signal(sym, market, sig, px, t, equity, fee):
    # All modes start with SAME structure-based SL, EMA TP and ladder.
    p=base.entry_cycle(sym,market,sig["side"],px,sig["atr"],t,equity,
                       "sr_ema",structure=sig.get("structure"))
    if p is None:
        return None
    # Budget gross stop + estimate all 4-fill costs at STRESSED 10bp/side.
    # Risk at entry includes all intended future add fills; funding/gaps extra.
    worst=.0; nominal=.0
    for q,lv in zip(p["quantities"],p["levels"]):
        worst+=q*(p["sign"]*(lv-p["stop"]) + .001*(lv+p["stop"]))
        nominal+=q*lv
    cap=p["max_risk_budget"]
    scale=min(1.0,cap/worst) if worst>0 else 0.0
    if nominal>0:
        scale=min(scale, .70*equity/nominal)
    if scale<=0:
        return None
    p["quantities"]=[q*scale for q in p["quantities"]]
    p["qty"]=p["quantities"][0]
    p["cost_basis"]=px*p["qty"]
    p["avg"]=px
    p["fills"]=[{"price":px,"qty":p["qty"],"t":t}]
    p["fees"]=p["qty"]*px*fee
    p["gross_realized"]=0.0
    p["rotation_count"]=0
    p["sl_moves"]=0
    p["cycle_phase"]="LADDER"
    p["cycle_tp"]=p["tp"]
    p["remaining_rebuy"]=0.0
    p["rebuy_level"]=None
    p["wait_bar_count"]=0
    p["last_rebuy_t"]=None
    p["final_tp_exit"]=False
    p["entry_atr"]=p["atr"]
    p["initial_stop"]=p["stop"]
    return p


def realize(p, q, price, fee):
    """Partial exit: split basis PROPORTIONALLY, no double counted exit PnL."""
    if q<=0:
        return
    q=min(q,p["qty"])
    basis=q*p["avg"]
    p["gross_realized"] += p["sign"]*(q*price-basis)
    p["fees"]+=q*price*fee
    p["cost_basis"]-=basis
    p["qty"]-=q
    if p["qty"]<1e-11:
        p["qty"]=0.0
        p["cost_basis"]=0.0


def add_initial(p,price,t,fee):
    j=p["next_add"]
    q=p["quantities"][j]
    p["qty"]+=q
    p["cost_basis"]+=q*price
    p["avg"]=p["cost_basis"]/p["qty"]
    p["fees"]+=q*price*fee
    p["fills"].append({"price":price,"qty":q,"t":t,"kind":"LADDER"})
    p["next_add"]+=1


def planned_rebuy(p,mode,price,fee,confirmed=None):
    """Read-only proposal. Widen SL only if worst total cycle PnL >= -budget.

    Old stop is enforced through the rebuy candle; any new stop takes effect
    only from NEXT candle. No future bar is used in risk approval.
    """
    sign=p["sign"]
    qty=p["remaining_rebuy"]
    if qty<=0 or price<=0:
        return None
    newstop=p["stop"]
    if mode=="rotate_lower":
        newstop=p["stop"]-sign*STOP_EXTEND_ATR*p["atr"]
    elif mode=="rotate_support":
        if confirmed is None:
            return None
        pivots=confirmed["pivot_low"] if sign>0 else confirmed["pivot_high"]
        candidates=[x-sign*base.PARAMS["stop_buffer_atr"]*p["atr"] for x in pivots]
        farther=[x for x in candidates if sign*(p["stop"]-x)>=STOP_EXTEND_ATR*p["atr"]]
        if not farther:
            return None
        newstop=min(farther,key=lambda x:sign*(p["stop"]-x))
    if newstop<=0 or sign*(price-newstop)<=0:
        return None
    if sign*(p["entry_price"]-newstop)>STOP_MAX_DIST_ATR*p["atr"]:
        return None
    newqty=p["qty"]+qty
    newbasis=p["cost_basis"]+qty*price
    newfees=p["fees"]+qty*price*fee
    # Prevent extreme total exposure even if partial TP has built reserves.
    notional=newqty*price
    if notional>p["entry_equity"]*base.PARAMS["gross_notional_limit_per_cycle"]+1e-6:
        return None
    floor=projected_floor(p,newstop,newqty,newbasis,newfees,fee=.001)
    if floor < -p["max_risk_budget"]-1e-8:
        return None
    return newstop


def finish(p,price,t,reason,fee):
    realize(p,p["qty"],price,fee)
    return {"symbol":p["symbol"],"side":p["side"],"mode":p["mode"],
            "entry_t":p["entry_t"],"exit_t":t,"reason":reason,"entry":p["entry_price"],
            "exit":price,"initial_stop":p["initial_stop"],"last_stop":p["stop"],
            "stop_source":p["stop_source"],"tp_source":p["tp_source"],
            "pnl":p["gross_realized"]-p["fees"]-p["funding"],
            "r":(p["gross_realized"]-p["fees"]-p["funding"])/p["max_risk_budget"],
            "rotations":p["rotation_count"],"sl_moves":p["sl_moves"],
            "fills":len(p["fills"]),"fees":p["fees"],"funding":p["funding"],
            "gross_realized":p["gross_realized"]}


def process_bar(p,b,market,mode,fee,pack,entry_bar=False):
    """STOP before TP, no same-bar reentry+profit; old stop until candle close.

    When TP and rebuy both touch in the same bar, the order already open
    at the start of the bar has precedence, and rebuy cannot occur until
    a subsequent bar. At new rebuy, new SL applies NEXT hour only.
    """
    sign=p["sign"]
    p["bar_count"]+=1
    oldstop=p["stop"]
    if not entry_bar and sign*(b["o"]-oldstop)<=0:
        return finish(p,b["o"],b["t"],"GAP_STOP",fee)
    adverse=b["l"] if sign>0 else b["h"]
    favorable=b["h"] if sign>0 else b["l"]
    if p["cycle_phase"]=="LADDER":
        added=entry_bar
        while p["next_add"]<len(p["levels"]):
            lv=p["levels"][p["next_add"]]
            if sign*(adverse-lv)>0:
                break
            # Resting limit may fill better at open if stop gap didn't occur.
            px=min(b["o"],lv) if sign>0 else max(b["o"],lv)
            if entry_bar and sign*(b["o"]-oldstop)<=0:
                px=lv
            add_initial(p,px,b["t"],fee)
            added=True
    else:
        added=False
    if sign*(adverse-oldstop)<=0:
        return finish(p,oldstop,b["ct"],"STOP",fee)
    if (p["cycle_phase"]=="LADDER" and p["rotation_count"]==0 and
            not added and sign*(favorable-p["cycle_tp"])>=0):
        if mode=="static":
            return finish(p,p["cycle_tp"],b["ct"],"TP_FULL",fee)
        # Realise 50%, keep rest as core, prepare a rebuy at a known level.
        sold=p["qty"]*PARTIAL
        realize(p,sold,p["cycle_tp"],fee)
        p["remaining_rebuy"]=sold
        p["rebuy_level"]=p["cycle_tp"]-sign*REBUY_DIST_ATR*p["atr"]
        p["cycle_phase"]="WAIT_REBUY"
        p["wait_bar_count"]=0
        p["next_add"]=len(p["levels"])  # cancel old ladder upon partial TP
    elif p["cycle_phase"]=="WAIT_REBUY":
        p["wait_bar_count"]+=1
        if sign*(adverse-p["rebuy_level"])<=0:
            px=min(b["o"],p["rebuy_level"]) if sign>0 else max(b["o"],p["rebuy_level"])
            from arm_v1_swing_core import confirmed_h4
            # No future HTF candle: strictly BEFORE candidate fill bar OPEN.
            recent=confirmed_h4(pack,b["t"]-1)
            structure=None
            if recent is not None and mode=="rotate_support":
                ii=bisect_right(pack["h4_closes"],b["t"]-1)-1
                structure=base.confirmed_structure(pack["h4"],ii)
            proposed=planned_rebuy(p,mode,px,fee,confirmed=structure)
            if proposed is not None:
                q=p["remaining_rebuy"]
                p["qty"]+=q
                p["cost_basis"]+=q*px
                p["avg"]=p["cost_basis"]/p["qty"]
                p["fees"]+=q*px*fee
                p["fills"].append({"price":px,"qty":q,"t":b["t"],"kind":"REBUY"})
                p["rotation_count"]+=1
                if abs(proposed-oldstop)>1e-12:
                    p["sl_moves"]+=1
                # Safe: this candle's OLD stop already checked above.
                p["stop"]=proposed
                p["last_rebuy_t"]=b["t"]
                p["cycle_phase"]="LADDER"
                p["next_add"]=len(p["levels"])
                p["remaining_rebuy"]=0.0
                # no TP on rebuy candle
                added=True
        if p["cycle_phase"]=="WAIT_REBUY":
            # Opportunity cost of not re-buying: take +1.5 ATR runner profit.
            runner_tp=p["cycle_tp"]+sign*RUNNER_TP_DIST_ATR*p["atr"]
            if sign*(favorable-runner_tp)>=0:
                return finish(p,runner_tp,b["ct"],"RUNNER_TP",fee)
            if p["wait_bar_count"]>=REBUY_WAIT_HOURS[market]:
                return finish(p,b["c"],b["ct"],"REBUY_EXPIRED",fee)
    # Second/third structural TP after a rebuy.
    elif p["cycle_phase"]=="LADDER" and not added and p["rotation_count"]>0:
        if sign*(favorable-p["cycle_tp"])>=0:
            if p["rotation_count"]>=MAX_REBUYS:
                return finish(p,p["cycle_tp"],b["ct"],"ROTATION_FINAL_TP",fee)
            sold=p["qty"]*PARTIAL
            realize(p,sold,p["cycle_tp"],fee)
            p["remaining_rebuy"]=sold
            p["rebuy_level"]=p["cycle_tp"]-sign*REBUY_DIST_ATR*p["atr"]
            p["cycle_phase"]="WAIT_REBUY"
            p["wait_bar_count"]=0
    maxbars=base.PARAMS["max_bars"][market]
    if p["bar_count"]>=maxbars:
        return finish(p,b["c"],b["ct"],"TIME",fee)
    return None


def evaluate_metrics(trades,curve):
    profits=[x["pnl"] for x in trades if x["pnl"]>0]
    losses=[x["pnl"] for x in trades if x["pnl"]<0]
    peak=INITIAL;maxdd=0.;current_loss=max_loss=0
    for event in curve:
        peak=max(peak,event["equity"])
        maxdd=max(maxdd,(peak-event["equity"])/peak)
    for tr in sorted(trades,key=lambda x:(x["exit_t"],x["symbol"])):
        if tr["pnl"]<0:
            current_loss+=1;max_loss=max(max_loss,current_loss)
        else:current_loss=0
    years=defaultdict(list)
    for tr in trades:
        year=str(datetime.fromtimestamp(tr["entry_t"]/1000,timezone.utc).year)
        years[year].append(tr)
    return {
        "trades":len(trades),"win_rate":len(profits)/len(trades) if trades else None,
        "net_return_pct":((curve[-1]["equity"]/INITIAL-1)*100 if curve else 0.),
        "net_pnl":sum(x["pnl"] for x in trades),
        "profit_factor":sum(profits)/-sum(losses) if losses else None,
        "max_mtm_drawdown_pct":maxdd*100,
        "avg_r":statistics.fmean(x["r"] for x in trades) if trades else None,
        "max_losing_streak":max_loss,
        "total_fees":sum(x["fees"] for x in trades),
        "funding_total":sum(x["funding"] for x in trades),
        "rotation_rebuys":sum(x["rotations"] for x in trades),
        "stop_moves":sum(x["sl_moves"] for x in trades),
        "stops":sum("STOP" in x["reason"] for x in trades),
        "by_year":{k:{"trades":len(v),"pnl":sum(x["pnl"] for x in v)}
                   for k,v in sorted(years.items())},
        "by_symbol":{s:{"trades":sum(x["symbol"]==s for x in trades),
                         "pnl":sum(x["pnl"] for x in trades if x["symbol"]==s)}
                     for s in sorted(set(x["symbol"] for x in trades))},
        "exit_reasons":dict(Counter(x["reason"] for x in trades)),
        "max_cycles":max((x["open_cycles"] for x in curve),default=0),
    }


def simulate(packs,market,mode,start_ms,end_ms,fee=.0006,funding=None):
    if mode not in MODES:raise ValueError(mode)
    benchmark=packs["SPY" if market=="stock" else "BTCUSDT"]
    syms=(sorted(s for s in packs if s!="SPY") if market=="stock"
          else ["BTCUSDT","ETHUSDT"])
    signals={s:base.build_signals(packs[s],benchmark,market,s,"sr_ema",start_ms,end_ms)
             for s in syms}
    events=defaultdict(list)
    for sym in syms:
        for b in packs[sym]["hour"]:
            if start_ms<=b["t"]<end_ms:events[b["t"]].append((sym,b))
    positions={};trades=[];curve=[];marks={};balance=INITIAL
    funding=funding or {}
    ftime={s:[t for t,_ in funding.get(s,[])] for s in syms}
    last_close={s:start_ms-1 for s in syms}
    for t in sorted(events):
        bars=sorted(events[t],key=lambda row:row[0])
        entered=set()
        # Real opening stop gaps first; no reentry in this same candle.
        gapped=set()
        for sym,b in bars:
            p=positions.get(sym)
            if p is not None and p["sign"]*(b["o"]-p["stop"])<=0:
                closed=finish(p,b["o"],b["t"],"GAP_STOP",fee)
                balance+=closed["pnl"];trades.append(closed)
                del positions[sym];gapped.add(sym)
        # Causal simultaneous portfolio risk at OPEN, prior candle marks only.
        for sym,b in bars:
            if sym in positions or sym in gapped or t not in signals[sym]:
                continue
            if len(positions)>=base.PARAMS["max_open_cycles"]:continue
            floating=sum(mark_pnl(p,marks.get(k,p["avg"])) for k,p in positions.items())
            equity=balance+floating
            if equity<=0:continue
            sig=signals[sym][t]
            pos=position_from_signal(sym,market,sig,b["o"],t,equity,fee)
            if pos is None:continue
            pos["mode"]=mode
            positions[sym]=pos
            entered.add(sym)
        for sym,b in bars:
            p=positions.get(sym)
            if p is None:
                marks[sym]=b["c"];last_close[sym]=b["ct"];continue
            # Fee/funding treated in floating equity, cycle closed PnL ledger.
            result=process_bar(p,b,market,mode,fee,packs[sym],entry_bar=sym in entered)
            if market=="crypto":
                ft=funding.get(sym,[])
                after=(t-1 if sym in entered else max(last_close[sym],p["entry_t"]))
                left=bisect_right(ftime[sym],after)
                right=bisect_right(ftime[sym],b["ct"])
                for _,rate in ft[left:right]:
                    p["funding"]+=p["sign"]*p["qty"]*b["c"]*rate
                # Update realised cycle result if closed inside a funding hour.
                if result is not None:
                    result["funding"]=p["funding"]
                    result["pnl"]=p["gross_realized"]-p["fees"]-p["funding"]
                    result["r"]=result["pnl"]/p["max_risk_budget"]
            if result is not None:
                balance+=result["pnl"];trades.append(result)
                del positions[sym]
            marks[sym]=b["c"];last_close[sym]=b["ct"]
        fpnl=sum(mark_pnl(p,marks.get(s,p["avg"])) for s,p in positions.items())
        curve.append({"t":max(b["ct"] for _,b in bars),"equity":balance+fpnl,
                      "realized":balance,"floating":fpnl,"open_cycles":len(positions)})
    if curve:
        end=curve[-1]["t"]
        for sym,p in list(positions.items()):
            result=finish(p,marks.get(sym,p["avg"]),end,"END_OF_DATA",fee)
            balance+=result["pnl"];trades.append(result)
        curve[-1].update({"equity":balance,"realized":balance,"floating":0,"open_cycles":0})
    trades.sort(key=lambda x:(x["exit_t"],x["symbol"]))
    return {"mode":mode,"market":market,"metrics":evaluate_metrics(trades,curve),
            "trades":trades,"equity_curve":curve,"parameters":{
            "max_rebuys":MAX_REBUYS,"partial_take_profit_fraction":PARTIAL,
            "rebuy_spacing_atr":REBUY_DIST_ATR,"stop_extension_atr":STOP_EXTEND_ATR,
            "runner_tp_atr":RUNNER_TP_DIST_ATR,
            "rebuy_wait_hours":REBUY_WAIT_HOURS[market],
            "cost_each_side":fee}}
