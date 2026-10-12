"""Entry First v9 — causal limit-order alternatives to the v8 sweep signal.

No live orders. Limit orders are RESTING before the next 1H bar's extremes.
Same-bar entry+stop -> STOP; gap through STOP at OPEN -> cancel order.
Limit orders reserve a portfolio slot while waiting (no hidden leverage).
"""
from bisect import bisect_right
from collections import defaultdict,Counter
from datetime import datetime,timezone

import entry_first_v8_core as v8

MODES=("market","market_shock","limit_half","limit_reclaim","limit_deep",
       "limit_half_shock","limit_reclaim_shock","limit_half_2h")
SHOCK_RANGE_ATR=2.25
LIMIT_FRACTIONS={"limit_half":0.50,"limit_deep":0.0,
                 "limit_half_shock":0.50,"limit_half_2h":0.50}
RECLAIM_OFFSET_ATR=0.10
DEEP_EXTREME_BUFFER_ATR=0.70
DEFAULT_LIFE=8
SHORT_LIFE=2


def completed_signal_h4(pack, sig):
    i=bisect_right(pack["h4_closes"],sig["signal_t"])-1
    if i<0:return None
    x=pack["h4"][i]
    return x if x["ct"]==sig["signal_t"] else None


def shock_accept(pack,sig):
    x=completed_signal_h4(pack,sig)
    if x is None or not x.get("atr14") or x["atr14"]<=0:return False
    return (x["h"]-x["l"])/x["atr14"]<=SHOCK_RANGE_ATR


def proposed_limit(mode,sig):
    """All prices fixed by COMPLETED signal, before the next 1H bar opens."""
    sign=sig["sign"];atr=sig["entry_atr"]
    if mode in ("limit_half","limit_half_shock","limit_half_2h"):
        price=sig["source_close"]-sign*0.50*atr
    elif mode in ("limit_reclaim","limit_reclaim_shock"):
        price=sig["structure_level"]+sign*RECLAIM_OFFSET_ATR*atr
    elif mode=="limit_deep":
        price=sig["anchor"]+sign*DEEP_EXTREME_BUFFER_ATR*atr
    else:
        raise ValueError("not limit mode "+mode)
    # An entry limit must improve on the actual known signal close.
    if price<=0 or sign*(sig["source_close"]-price)<=0:
        return None
    return price


def make_order(symbol,mode,sig,first_bar,first_index,equity,cost):
    px=proposed_limit(mode,sig)
    if px is None:return None,"no_favorable_limit"
    sign=sig["sign"];atr=sig["entry_atr"]
    stop=sig["anchor"]-sign*v8.PARAMS["stop_atr_buffer"]*atr
    risk=sign*(px-stop)
    if stop<=0 or not (v8.PARAMS["stop_min_atr"]*atr<=risk<=
                        v8.PARAMS["stop_max_atr"]*atr):
        return None,"invalid_limit_stop_distance"
    # Reserve position quantity/capital using proposed limit price and
    # fee-STRESSED 10bps per side, not future intrabar low/high.
    budget=v8.PARAMS["risk_fraction"]*equity
    unit=risk+.001*(px+stop)
    qty=min(budget/unit,
            equity*v8.PARAMS["notional_limit_per_position"]/px)
    if qty<=0:return None,"zero_qty"
    return {"symbol":symbol,"mode":mode,"sig":sig,"limit":px,
            "stop":stop,"qty":qty,"equity_at_order":equity,
            "risk_budget":budget,
            "first_index":first_index,
            "last_index":first_index+(SHORT_LIFE if mode=="limit_half_2h" else DEFAULT_LIFE)-1,
            "created_t":first_bar["t"]},"submitted"


def fill_price(o,b):
    """Known OPEN receives price improvement. Else resting limit fills at limit.

    No same-bar TP. If bar LOW/HIGH touches both limit and stop,
    assume limit filled then stop touched (conservative).
    """
    sign=o["sig"]["sign"];lim=o["limit"]
    if sign*(b["o"]-o["stop"])<=0:
        return None,"open_through_stop"
    if sign*(b["o"]-lim)<=0:
        return b["o"],"open_improved"
    if (b["l"]<=lim if sign>0 else b["h"]>=lim):
        return lim,"resting_limit"
    return None,"not_touched"


def activate(o,b,price,cost):
    s=o["sig"];sign=s["sign"];risk=sign*(price-o["stop"])
    if risk<=0:return None
    # A better-than-limit entry decreases gross stop risk in sign direction.
    if risk>sign*(o["limit"]-o["stop"])+1e-9:
        raise AssertionError("bad limit improvement semantics")
    return {
       "symbol":o["symbol"],"mode":o["mode"],"kind":"sweep_limit",
       "side":s["side"],"sign":sign,"entry":price,
       "entry_t":b["t"],"signal_t":s["signal_t"],
       "stop":o["stop"],"target":price+sign*v8.PARAMS["target_r"]*risk,
       "qty":o["qty"],"risk_price":risk,"risk_budget":o["risk_budget"],
       "fees":o["qty"]*price*cost,"funding":0.,"age":0,
       "mae_r":0.,"mfe_r":0.,"structure_level":s["structure_level"],
       "order_t":o["created_t"],"fill_delay_bars":None
    }


def simulation_metrics(trades,curve,rejections,candidates,orders,filled,
                       cancel_reasons,delay_sum,extra):
    m=v8.evaluate(trades,curve,rejections,candidates)
    m.update({"submitted_orders":orders,"filled_orders":filled,
              "fill_rate":filled/orders if orders else None,
              "cancels":dict(cancel_reasons),
              "avg_fill_wait_hours":delay_sum/filled if filled else None,
              "skipped_shocks":extra.get("shock",0),
              "unfilled_end_of_data":extra.get("eod",0),
              "improved_open_fills":extra.get("improved",0),
              "same_hour_stops":sum(t["reason"]=="STOP" and
                                    t["entry_t"]==t["exit_t"] for t in trades)})
    return m


def simulate(packs,market,mode,start_ms,end_ms,cost=.0006,funding=None,
             trade_symbols=None,precomputed=None):
    if mode not in MODES:raise ValueError(mode)
    if market=="stock":
        symbols=sorted(s for s in packs if s!="SPY")
    else:
        symbols=sorted(trade_symbols or ["BTCUSDT","ETHUSDT"])
    if not all(s in packs for s in symbols):
        raise ValueError("one or more traded symbols missing")
    if precomputed is None:
        precomputed={s:v8.precompute_signals(packs[s],market)["sweep"]
                     for s in symbols}
    events=defaultdict(list)
    barindex={}
    for s in symbols:
        barindex[s]={b["t"]:i for i,b in enumerate(packs[s]["hour"])}
        for b in packs[s]["hour"]:
            if start_ms<=b["t"]<end_ms:events[b["t"]].append((s,b))
    rates=funding or {}
    times={s:[t for t,_ in rates.get(s,[])] for s in symbols}
    last_end={s:start_ms-1 for s in symbols}
    positions={};pending={};marks={};trades=[];curve=[]
    cash=v8.START_EQUITY
    rejects=Counter();cancels=Counter();extras=Counter()
    candidates=orders=filled=delay_sum=0

    for t in sorted(events):
        rows=sorted(events[t],key=lambda x:x[0])
        gapped=set()
        # Genuine pre-existing STOP GAP resolves at known OPEN.
        for s,b in rows:
            p=positions.get(s)
            if p and p["sign"]*(b["o"]-p["stop"])<=0:
                trade=v8.update_position(p,b,market,cost,entry_bar=False)
                if trade is None:raise AssertionError("gap ignored")
                trades.append(trade);cash+=trade["pnl"]
                del positions[s];gapped.add(s)
        entered=set()
        for s,b in rows:
            if s in positions or s in gapped:continue
            active=pending.get(s)
            if active is None:continue
            if barindex[s][t]>active["last_index"]:
                cancels["expired"]+=1;pending.pop(s)
                continue
            px,reason=fill_price(active,b)
            if reason=="open_through_stop":
                cancels[reason]+=1;pending.pop(s)
                continue
            if px is not None:
                p=activate(active,b,px,cost)
                if p is not None:
                    p["fill_delay_bars"]=barindex[s][t]-active["first_index"]
                    positions[s]=p;entered.add(s)
                    filled+=1;delay_sum+=p["fill_delay_bars"]
                    if reason=="open_improved":extras["improved"]+=1
                else:
                    cancels["bad_improved_fill"]+=1
                pending.pop(s,None)
            elif barindex[s][t]>=active["last_index"]:
                cancels["expired"]+=1;pending.pop(s,None)
        # New orders admitted at current OPEN, never using this bar's
        # intrabar high/low to SIZE or choose to place the order.
        for s,b in rows:
            if s in positions or s in pending or s in gapped:continue
            signal=precomputed[s].get(t)
            if signal is None:continue
            candidates+=1
            if (mode.endswith("_shock") or mode=="market_shock") and not shock_accept(packs[s],signal):
                rejects["shock_skip"]+=1;extras["shock"]+=1;continue
            # Pending limits conservatively RESERVE slots alongside holdings.
            if len(positions)+len(pending)>=v8.PARAMS["max_parallel"]:
                rejects["reserved_concurrency"]+=1;continue
            floating=sum(p["sign"]*p["qty"]*(marks.get(k,p["entry"])-p["entry"])
                         -p["fees"]-p["funding"] for k,p in positions.items())
            equity=cash+floating
            if equity<=0:
                rejects["no_equity"]+=1;continue
            if mode.startswith("market"):
                p,why=v8.open_trade(s,mode,signal,b,equity,cost)
                if p is None:
                    rejects[why]+=1;continue
                positions[s]=p;entered.add(s)
            else:
                order,why=make_order(s,mode,signal,b,barindex[s][t],equity,cost)
                if order is None:
                    rejects[why]+=1;continue
                pending[s]=order;orders+=1
                # Order was resting since OPEN, fill on same-hour action,
                # but sizing was computed WITHOUT current OHLC extremes.
                px,reason=fill_price(order,b)
                if reason=="open_through_stop":
                    cancels[reason]+=1;pending.pop(s)
                elif px is not None:
                    p=activate(order,b,px,cost)
                    if p is not None:
                        p["fill_delay_bars"]=0
                        positions[s]=p;entered.add(s);filled+=1
                        if reason=="open_improved":extras["improved"]+=1
                    else:
                        cancels["bad_improved_fill"]+=1
                    pending.pop(s,None)
                elif order["last_index"]==order["first_index"]:
                    cancels["expired"]+=1;pending.pop(s)
        # AFTER entry/open order placement, process current-hour candle
        # conservatively (STOP before +2R, even on entry bar).
        for s,b in rows:
            p=positions.get(s)
            if p:
                done=v8.update_position(p,b,market,cost,entry_bar=(s in entered))
                if market=="crypto":
                    after=(t-1 if s in entered else max(last_end[s],p["entry_t"]))
                    lo=bisect_right(times[s],after)
                    hi=bisect_right(times[s],b["ct"])
                    for _,rate in rates.get(s,[])[lo:hi]:
                        p["funding"]+=p["sign"]*p["qty"]*b["c"]*rate
                    if done is not None:
                        done["funding"]=p["funding"]
                        done["pnl"]=p["sign"]*p["qty"]*(done["exit"]-p["entry"])-done["fees"]-p["funding"]
                        done["r"]=done["pnl"]/(p["qty"]*p["risk_price"])
                        done["net_r_budget"]=done["pnl"]/p["risk_budget"]
                if done is not None:
                    done["fill_delay_bars"]=p.get("fill_delay_bars",0)
                    trades.append(done);cash+=done["pnl"];del positions[s]
            marks[s]=b["c"]
            last_end[s]=b["ct"]
        floating=sum(p["sign"]*p["qty"]*(marks.get(s,p["entry"])-p["entry"])
                     -p["fees"]-p["funding"] for s,p in positions.items())
        curve.append({"t":max(b["ct"] for _,b in rows),"equity":cash+floating,
                      "realized":cash,"floating":floating,
                      "open":len(positions),"pending":len(pending)})
    if curve:
        endt=curve[-1]["t"]
        for s,p in list(positions.items()):
            tr=v8.finish(p,marks.get(s,p["entry"]),endt,"END_OF_DATA",cost)
            tr["fill_delay_bars"]=p.get("fill_delay_bars",0)
            trades.append(tr);cash+=tr["pnl"]
        extras["eod"]=len(pending)
        cancels["end_of_data"]+=len(pending)
        pending.clear()
        curve[-1].update({"equity":cash,"realized":cash,"floating":0.,
                          "open":0,"pending":0})
    trades.sort(key=lambda x:(x["exit_t"],x["symbol"]))
    return {"mode":mode,"market":market,"trades":trades,"curve":curve,
            "metrics":simulation_metrics(trades,curve,rejects,candidates,orders,
                                         filled,cancels,delay_sum,extras)}
