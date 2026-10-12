"""Chaser-inspired v1: independent breakout-continuation research, NOT AGOS internals.

Self-contained chronological simulator. Reuses existing ARM bars and completed
HTF indicators. Three preregistered variants share exact order/risk/exit rules.
No live orders, credentials or Supabase interaction.
"""
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timezone

import arm_v1_swing_core as arm

PARAMS = {
    "breakout_lookback": 20,
    "signal_breakout_atr": 0.05,
    "minimum_clv": 0.65,
    "max_entry_gap_atr": 0.75,
    "initial_stop_atr": 2.0,
    "tp1_r": 1.5,
    "tp2_r": 3.0,
    "tp1_fraction": 0.5,
    "crypto_max_hours": 120,
    "stock_max_rth_hours": 35,
    "risk_fraction": 0.005,
    "max_parallel": 3,
    "max_symbol_notional_fraction": 0.75,
    "compression_lookback": 10,
    "compression_max_range_atr": 5.0,
    "expansion_min_range_atr": 1.0,
    "expansion_min_body_fraction": 0.5,
    "expansion_volume_multiple": 1.2,
}
INITIAL_CAPITAL = 20000.0
VARIANTS = ("breakout", "trend", "trend_compression")


def trend_filter(pack, benchmark, signal_bar, side, market):
    # "Prior daily" never includes the signal day's incomplete daily candle.
    s = arm.prev_daily(pack, signal_bar["day"])
    b = arm.prev_daily(benchmark, signal_bar["day"])
    h = arm.confirmed_h4(pack, signal_bar["ct"])
    if not s or not b or not h:
        return False
    needed = (s.get("ema50"), s.get("ema200"), b.get("ema200"),
              h.get("ema20"), h.get("ema50"))
    if any(x is None for x in needed):
        return False
    sign = 1 if side == "LONG" else -1
    return (sign * (b["c"]-b["ema200"]) > 0
            and sign * (s["c"]-s["ema50"]) > 0
            and sign * (s["ema50"]-s["ema200"]) > 0
            and sign * (h["c"]-h["ema20"]) > 0
            and sign * (h["ema20"]-h["ema50"]) > 0)


def compression_filter(bars, i, side, atr):
    prev = bars[i-10:i]
    if len(prev) < 10 or atr <= 0:
        return False
    range10 = max(x["h"] for x in prev) - min(x["l"] for x in prev)
    if range10 > PARAMS["compression_max_range_atr"] * atr:
        return False
    x = bars[i]
    r = x["h"] - x["l"]
    if r < PARAMS["expansion_min_range_atr"]*atr or r <= 0:
        return False
    if abs(x["c"]-x["o"]) < PARAMS["expansion_min_body_fraction"]*r:
        return False
    mean_vol = sum(max(z["v"],0) for z in bars[i-20:i])/20.0
    return mean_vol > 0 and x["v"] >= PARAMS["expansion_volume_multiple"]*mean_vol


def signal_at_close(pack, benchmark, market, variant, i):
    bars=pack["hour"]
    if i < 210 or i+1 >= len(bars):
        return None
    x=bars[i]
    atr=x.get("atr14")
    if not atr or atr<=0:
        return None
    prev=bars[i-20:i]
    if len(prev)<20:
        return None
    spread=x["h"]-x["l"]
    if spread<=0:
        return None
    upper=max(z["h"] for z in prev)
    lower=min(z["l"] for z in prev)
    options=["LONG"] if market=="stock" else ["LONG","SHORT"]
    for side in options:
        sign=1 if side=="LONG" else -1
        if sign>0:
            breakout=x["c"]>upper+PARAMS["signal_breakout_atr"]*atr
            clv=(x["c"]-x["l"])/spread
        else:
            breakout=x["c"]<lower-PARAMS["signal_breakout_atr"]*atr
            clv=(x["h"]-x["c"])/spread
        if not breakout or clv<PARAMS["minimum_clv"]:
            continue
        if variant!="breakout" and not trend_filter(pack,benchmark,x,side,market):
            continue
        if variant=="trend_compression" and not compression_filter(bars,i,side,atr):
            continue
        return {"symbol":None,"side":side,"sign":sign,"signal_t":x["ct"],
                "signal_close":x["c"],"atr":atr}
    return None


def build_signals(pack,bench,market,variant,start_ms,end_ms):
    """Timestamp of next bar's OPEN is the earliest actionable signal."""
    bars=pack["hour"]; out={}
    for i in range(210,len(bars)-1):
        t=bars[i+1]["t"]
        if t<start_ms or t>=end_ms:
            continue
        sig=signal_at_close(pack,bench,market,variant,i)
        if sig:
            out[t]=sig
    return out


def open_position(symbol,bar,signal,equity,market,cost):
    price=bar["o"];sign=signal["sign"];atr=signal["atr"]
    if sign*(price-signal["signal_close"])>PARAMS["max_entry_gap_atr"]*atr:
        return None
    stop=price-sign*PARAMS["initial_stop_atr"]*atr
    if price<=0 or stop<=0 or equity<=0:
        return None
    risk_per_unit=abs(price-stop)
    budget=equity*PARAMS["risk_fraction"]
    qty=min(budget/risk_per_unit, equity*PARAMS["max_symbol_notional_fraction"]/price)
    if qty<=0:
        return None
    entry_fee=qty*price*cost
    return {
        "symbol":symbol,"side":signal["side"],"sign":sign,"market":market,
        "entry":price,"entry_t":bar["t"],"signal_t":signal["signal_t"],
        "initial_qty":qty,"remaining_qty":qty,"stop":stop,"active_stop":stop,
        "rprice":risk_per_unit,"tp1":price+sign*1.5*risk_per_unit,
        "tp2":price+sign*3.0*risk_per_unit,"stage":0,"hours":0,
        "entry_fee":entry_fee,"exit_fees":0.0,"funding":0.0,
        "net_pnl":-entry_fee,"actual_planned_risk":qty*risk_per_unit,
        "max_initial_budget":budget,"legs":[],"min_float":-entry_fee,
    }


def settle_leg(pos, qty, px, t, reason, cost):
    if qty<=0:
        return 0.0
    fee=qty*px*cost
    delta=pos["sign"]*qty*(px-pos["entry"])-fee
    pos["remaining_qty"]=max(0.0,pos["remaining_qty"]-qty)
    pos["net_pnl"]+=delta
    pos["exit_fees"]+=fee
    pos["legs"].append({"qty":qty,"px":px,"t":t,"reason":reason})
    return delta


def process_candle(pos,bar,market,cost,entry_bar=False):
    """Return cash delta and whether cycle is closed.
    
    Once in a position: genuine gap stop filled at open, otherwise the stop
    wins all same-1H-candle stop/target ambiguities. BE ratchet only AFTER
    candle close, to avoid using unknown within-candle execution order.
    """
    cash_delta=0.0
    sign=pos["sign"]
    pos["hours"]+=1
    stop=pos["active_stop"]
    if not entry_bar and sign*(bar["o"]-stop)<=0:
        cash_delta+=settle_leg(pos,pos["remaining_qty"],bar["o"],bar["ct"],"GAP_STOP",cost)
        return cash_delta,True
    adverse=bar["l"] if sign>0 else bar["h"]
    if sign*(adverse-stop)<=0:
        cash_delta+=settle_leg(pos,pos["remaining_qty"],stop,bar["ct"],"STOP",cost)
        return cash_delta,True
    favorable=bar["h"] if sign>0 else bar["l"]
    if pos["stage"]==0 and sign*(favorable-pos["tp1"])>=0:
        qty=pos["initial_qty"]*PARAMS["tp1_fraction"]
        cash_delta+=settle_leg(pos,min(qty,pos["remaining_qty"]),pos["tp1"],bar["ct"],"TP1",cost)
        pos["stage"]=1
    if pos["remaining_qty"]>1e-12 and sign*(favorable-pos["tp2"])>=0:
        cash_delta+=settle_leg(pos,pos["remaining_qty"],pos["tp2"],bar["ct"],"TP2",cost)
    if pos["remaining_qty"]<=1e-12:
        return cash_delta,True
    max_hours=PARAMS["crypto_max_hours"] if market=="crypto" else PARAMS["stock_max_rth_hours"]
    if pos["hours"]>=max_hours:
        cash_delta+=settle_leg(pos,pos["remaining_qty"],bar["c"],bar["ct"],"TIME",cost)
        return cash_delta,True
    if pos["stage"]>=1:
        pos["active_stop"]=pos["entry"]
    return cash_delta,False


def finalize(pos,t):
    return {
        "symbol":pos["symbol"],"market":pos["market"],"side":pos["side"],
        "entry_t":pos["entry_t"],"exit_t":t,"entry":pos["entry"],
        "r":pos["net_pnl"]/pos["actual_planned_risk"],
        "pnl":pos["net_pnl"],"risk_budget":pos["actual_planned_risk"],
        "entry_fee":pos["entry_fee"],"exit_fees":pos["exit_fees"],
        "funding":pos["funding"],"min_float":pos["min_float"],
        "legs":pos["legs"],"exit_reason":pos["legs"][-1]["reason"] if pos["legs"] else None
    }


def compute_metrics(trades, curve):
    pnl=[t["pnl"] for t in trades]
    win=[p for p in pnl if p>0];los=[p for p in pnl if p<0]
    peak=INITIAL_CAPITAL;dd=0.0
    for pt in curve:
        peak=max(peak,pt["equity"])
        dd=max(dd,(peak-pt["equity"])/peak)
    st=mx=0
    for tr in sorted(trades,key=lambda x:(x["exit_t"],x["symbol"])):
        if tr["pnl"]<0:
            st+=1;mx=max(mx,st)
        else:
            st=0
    end_eq=curve[-1]["equity"] if curve else INITIAL_CAPITAL
    return {
        "trades":len(trades),"win_rate":len(win)/len(pnl) if pnl else None,
        "net_pnl":sum(pnl),"net_return_pct":(end_eq/INITIAL_CAPITAL-1)*100,
        "profit_factor":sum(win)/abs(sum(los)) if los else None,
        "avg_r":sum(t["r"] for t in trades)/len(trades) if trades else None,
        "max_mtm_dd_pct":dd*100,"max_loss_streak":mx,
        "total_fees":sum(t["entry_fee"]+t["exit_fees"] for t in trades),
        "total_funding":sum(t["funding"] for t in trades),
        "worst_hourly_open_pnl":min((c["floating"] for c in curve),default=0),
        "long":sum(t["side"]=="LONG" for t in trades),
        "short":sum(t["side"]=="SHORT" for t in trades),
        "years":by_year(trades),
        "by_symbol":{sym:{"trades":len([x for x in trades if x["symbol"]==sym]),
                           "net_pnl":sum(x["pnl"] for x in trades if x["symbol"]==sym)}
                     for sym in sorted(set(t["symbol"] for t in trades))},
    }


def by_year(trades):
    out=defaultdict(list)
    for t in trades:
        out[str(datetime.fromtimestamp(t["entry_t"]/1000,timezone.utc).year)].append(t)
    return {k:{"trades":len(v),"net_pnl":sum(x["pnl"] for x in v)}
            for k,v in sorted(out.items())}


def simulate(packs,market,variant,start_ms,end_ms,cost=0.0006,funding=None):
    if variant not in VARIANTS:
        raise ValueError("unknown variant")
    benchmark=packs["SPY" if market=="stock" else "BTCUSDT"]
    syms=sorted(x for x in packs if x!="SPY") if market=="stock" else ["BTCUSDT","ETHUSDT"]
    signals={s:build_signals(packs[s],benchmark,market,variant,start_ms,end_ms) for s in syms}
    events=defaultdict(list)
    for sym in syms:
        for b in packs[sym]["hour"]:
            if start_ms<=b["t"]<end_ms:
                events[b["t"]].append((sym,b))
    funding=funding or {}
    ftimes={s:[t for t,_ in funding.get(s,[])] for s in syms}
    funding_cursors={s:0 for s in syms}
    positions={};marks={};trades=[];curve=[]
    balance=INITIAL_CAPITAL
    for timestamp in sorted(events):
        candles=sorted(events[timestamp],key=lambda q:q[0])
        # First resolve GAPS at bar OPEN (known before any intrabar future).
        gap_exits=set()
        for sym,b in candles:
            p=positions.get(sym)
            if p is not None and p["sign"]*(b["o"]-p["active_stop"])<=0:
                delta=settle_leg(p,p["remaining_qty"],b["o"],b["t"],"GAP_STOP",cost)
                balance+=delta;trades.append(finalize(p,b["t"]))
                del positions[sym];gap_exits.add(sym)
        # Next evaluate simultaneous new entries at actual bar OPEN, before H/L.
        entered=set()
        for sym,b in candles:
            if sym in positions or sym in gap_exits:
                continue
            sig=signals[sym].get(timestamp)
            if not sig or len(positions)>=PARAMS["max_parallel"]:
                continue
            floating=sum(p["sign"]*p["remaining_qty"]*(marks.get(k,p["entry"])-p["entry"])
                         for k,p in positions.items())
            equity=balance+floating
            new=open_position(sym,b,sig,equity,market,cost)
            if new is None:
                continue
            positions[sym]=new;entered.add(sym)
            balance-=new["entry_fee"]
        # Only AFTER all new entries: intrabar conservative fills and closing marks.
        for sym,b in candles:
            p=positions.get(sym)
            if p is not None:
                delta,closed=process_candle(p,b,market,cost,entry_bar=sym in entered)
                balance+=delta
                if not closed and market=="crypto":
                    rows=funding.get(sym,())
                    times=ftimes[sym]
                    # settlement at open or within bar; when held past bar close
                    a=bisect_right(times,max(p["entry_t"],b["t"]-1))
                    z=bisect_right(times,b["ct"])
                    for _,rate in rows[a:z]:
                        charge=p["sign"]*p["remaining_qty"]*b["c"]*rate
                        p["funding"]+=charge
                        p["net_pnl"]-=charge
                        balance-=charge
                p["min_float"]=min(p["min_float"],
                    p["sign"]*p["remaining_qty"]*(b["c"]-p["entry"]))
                if closed:
                    trades.append(finalize(p,b["ct"]))
                    del positions[sym]
            marks[sym]=b["c"]
        floating=sum(p["sign"]*p["remaining_qty"]*(marks.get(s,p["entry"])-p["entry"])
                    for s,p in positions.items())
        curve.append({"t":max(b["ct"] for _,b in candles),"equity":balance+floating,
                      "balance":balance,"floating":floating,"open_count":len(positions)})
    # Force-end marks at observed last close only; no extra phantom cash.
    if curve:
        end_t=curve[-1]["t"]
        for sym,p in list(positions.items()):
            px=marks.get(sym,p["entry"])
            balance+=settle_leg(p,p["remaining_qty"],px,end_t,"END_OF_DATA",cost)
            trades.append(finalize(p,end_t))
        curve[-1].update({"equity":balance,"balance":balance,"floating":0,"open_count":0})
    trades.sort(key=lambda t:(t["exit_t"],t["symbol"]))
    return {"market":market,"variant":variant,"cost":cost,
            "metrics":compute_metrics(trades,curve),
            "params":PARAMS,"trades":trades,"curve":curve,
            "limitations":[
               "Unmodified stock research universe suffers survivorship and sample-selection bias",
               "Last signal data is completed 1H; daily filter uses previous completed session",
               "Partial-fill high/low ambiguity uses adverse-stop-first model; no order book",
               "MTM MDD based on hourly close, not within-hour extrema",
               "Funding uses historical settlements with hourly close not exact mark; no liquidation or basis",
               "Portfolio max concurrency integrated at next-open entry before intrabar exits",
               "Long stock cash underlying is not a stock-futures execution model",
               "Cost stress is deterministic not real transaction-level order-flow slippage"
            ]}
