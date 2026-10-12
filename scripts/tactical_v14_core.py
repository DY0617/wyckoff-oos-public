"""V14 strategic adaptive gross budget on V12 cash-only allocation engine with exposure defense and cash yield scenarios (cash / no margin / no shorts).

The strategy differs FUNDAMENTALLY from Stacker and Entry First v1-v10:
rank long-term assets, control gross portfolio risk, and explicitly hold
cash during weak regimes. All decisions use LAST COMPLETED DAILY close,
trades are made only at the NEXT monthly rebalance day OPEN.

Run equally on Binance USDT-M underlyings as SPOT-LIKE unlevered
price histories and on selected US RTH stocks. This does NOT
simulate shorting or actual futures margin/funding; use consistent
spot-like cost assumptions with CASH benchmark and BUY-HOLD.
"""
from bisect import bisect_left
from collections import Counter
from datetime import datetime,timezone
from math import log,sqrt
import statistics

INITIAL=20000.0
MODES=("benchmark_hold","equal_hold","equal_monthly",
       "absolute_trend","momentum_top","risk_managed","risk_managed_gate",
       "gate_weekly","gate_cap","gate_crashguard",
       "v14_momentum_55","v14_invvol_55","v14_breadth","v14_dual_horizon",
       "v14_strength","v14_core_satellite")
PARAMS={
    "ema_window":200,
    "momentum_days":63,
    "volatility_days":60,
    "slots_crypto":3,
    "slots_stock":6,
    "target_vol_crypto":0.18,
    "target_vol_stock":0.12,
    "annual_days_crypto":365,
    "annual_days_stock":252,
    "risk_cap_crypto":0.35,
    "risk_cap_stock":0.20,
    "rebalance_band_pct_equity":0.01,
    "gate_cap_total":0.50,
    "gate_cap_single_asset":0.20,
    "crashguard_trailing_daily":30,
    "crashguard_drawdown":0.15,
    "v14_base_gross":0.55,
    "v14_high_gross":0.65,
    "v14_low_gross":0.30,
    "v14_max_single":0.30,
    "v14_dual_lookback_days":126,
    "v14_breadth_majority":0.60,
    "v14_strength_z":0.75,
    "v14_core_weight":0.15,
    "v14_satellite_weight":0.45,
}
EPS=1e-8


def prior_bar_index(days,day):
    return bisect_left(days,day)-1


def trailing_vol(rows,end_idx,window,annual_days):
    """Daily close-close realised vol, from observations strictly before day."""
    if end_idx<window or window<3:return None
    x=rows[end_idx-window:end_idx+1]
    if any(z["c"]<=0 for z in x):return None
    returns=[log(x[i]["c"]/x[i-1]["c"]) for i in range(1,len(x))]
    return statistics.stdev(returns)*sqrt(annual_days)


def regime_ok(bar):
    return bool(bar and bar.get("ema200") is not None and
                bar.get("ret60") is not None and
                bar["c"]>bar["ema200"] and bar["ret60"]>0)


def make_context(packs,market,day,symbols,benchmark):
    """Construct state using YESTERDAY or EARLIER daily data ONLY."""
    ctx={}
    for s in sorted(set(symbols+[benchmark])):
        pack=packs[s];rows=pack["daily"];idx=prior_bar_index(pack["day_keys"],day)
        if idx<0:continue
        d=rows[idx]
        if d.get("ret60") is None or d.get("ema200") is None:continue
        vol=trailing_vol(rows,idx,PARAMS["volatility_days"],
                         PARAMS["annual_days_"+market])
        if vol is None:continue
        ctx[s]={"close":d["c"],"prev_day":d["day"],
                "ema200":d["ema200"],"return63":d["c"]/rows[idx-63]["c"]-1 if idx>=63 and rows[idx-63]["c"]>0 else None,
                "vol":vol,"eligible":bool(d["c"]>d["ema200"] and idx>=63 and
                  rows[idx-63]["c"]>0 and d["c"]>rows[idx-63]["c"])}
    return ctx



V14_MODES=("v14_momentum_55","v14_invvol_55","v14_breadth",
           "v14_dual_horizon","v14_strength","v14_core_satellite")


def _allocate_budget(names,contexts,budget,max_name,method):
    """Fixed gross-risk budget with ex-ante per-name cap and cash remainder."""
    if not names or budget<=0:return {}
    if method=="equal":
        raw={s:1.0/len(names) for s in names}
    elif method=="inverse_vol":
        inv={s:1/max(.05,contexts[s]["vol"]) for s in names}
        total=sum(inv.values())
        raw={s:z/total for s,z in inv.items()}
    else:raise ValueError("invalid allocation method")
    return {s:min(max_name,budget*w) for s,w in raw.items() if w>0}


def tactical_v14_weights(mode,market,day,packs,symbols,benchmark,opened_today):
    if mode not in V14_MODES:raise ValueError(mode)
    ctx=make_context(packs,market,day,symbols,benchmark)
    ref=ctx.get(benchmark)
    if not ref or not ref["eligible"]:return {}
    eligible=[s for s in sorted(symbols) if s in opened_today and
              s in ctx and ctx[s]["eligible"]]
    eligible.sort(key=lambda s:(-ctx[s]["return63"],s))
    slots=PARAMS["slots_"+market]
    if mode=="v14_core_satellite":
        sat=[s for s in eligible if s!=benchmark][:slots]
        w=_allocate_budget(sat,ctx,PARAMS["v14_satellite_weight"],
                           PARAMS["v14_max_single"],"inverse_vol")
        if benchmark in opened_today:
            w[benchmark]=min(PARAMS["v14_max_single"],
                             w.get(benchmark,0)+PARAMS["v14_core_weight"])
        return w
    selected=eligible[:slots]
    if mode=="v14_dual_horizon":
        selected=[]
        for s in eligible:
            pack=packs[s]
            ix=prior_bar_index(pack["day_keys"],day)
            n=PARAMS["v14_dual_lookback_days"]
            if ix>=n and pack["daily"][ix-n]["c"]>0 and (
                    pack["daily"][ix]["c"]>pack["daily"][ix-n]["c"]):
                selected.append(s)
            if len(selected)>=slots:break
    budget=PARAMS["v14_base_gross"]
    if mode=="v14_breadth":
        valid=sum(s in ctx and ctx[s]["eligible"] for s in symbols)
        fraction=valid/max(len(symbols),1)
        budget=(PARAMS["v14_high_gross"] if
                fraction>=PARAMS["v14_breadth_majority"] else
                PARAMS["v14_low_gross"])
    if mode=="v14_strength":
        score=ref["return63"]/(max(.05,ref["vol"])*
                    sqrt(63/PARAMS["annual_days_"+market]))
        budget=(PARAMS["v14_high_gross"] if
                score>=PARAMS["v14_strength_z"] else
                PARAMS["v14_low_gross"])
    method=("equal" if mode=="v14_momentum_55" else "inverse_vol")
    return _allocate_budget(selected,ctx,budget,PARAMS["v14_max_single"],method)


def weights(mode,market,day,packs,symbols,benchmark,opened_today):
    """Target weights sum<=1. No use of current-day OHLC."""
    if mode not in MODES:raise ValueError(mode)
    if mode in V14_MODES:
        return tactical_v14_weights(mode,market,day,packs,symbols,
                                    benchmark,opened_today)
    if mode in ("gate_weekly","gate_cap","gate_crashguard"):
        base=weights("risk_managed_gate",market,day,packs,symbols,
                     benchmark,opened_today)
        if not base:return {}
        if mode=="gate_weekly":return base
        if mode=="gate_cap":
            capped={s:min(w,PARAMS["gate_cap_single_asset"]) for s,w in base.items()}
            total=sum(capped.values())
            shrink=min(1.0,PARAMS["gate_cap_total"]/total) if total>0 else 1.0
            return {s:w*shrink for s,w in capped.items()}
        # A trailing crash kill switch uses only fully completed
        # benchmark daily bars prior to the current execution OPEN.
        b=packs[benchmark]
        idx=prior_bar_index(b["day_keys"],day)
        window=PARAMS["crashguard_trailing_daily"]
        if idx<window-1:return {}
        last=b["daily"][idx]["c"]
        high=max(z["c"] for z in b["daily"][idx-window+1:idx+1])
        return {} if last/high<1-PARAMS["crashguard_drawdown"] else base
    tradable=sorted(s for s in symbols if s in opened_today)
    if mode=="benchmark_hold":
        return {benchmark:1.0} if benchmark in opened_today else {}
    if mode in ("equal_hold","equal_monthly"):
        return {s:1/len(tradable) for s in tradable} if tradable else {}
    ctx=make_context(packs,market,day,symbols,benchmark)
    eligible=[s for s in tradable if s in ctx and ctx[s]["eligible"]]
    if mode=="absolute_trend":
        # keep original universe denominator rather than concentrating
        # all available equity into the one surviving momentum name.
        return {s:1/max(len(symbols),1) for s in eligible}
    slots=PARAMS["slots_"+market]
    eligible.sort(key=lambda s:(-ctx[s]["return63"],s))
    leaders=eligible[:slots]
    if mode=="momentum_top":
        return {s:1/slots for s in leaders}
    if mode=="risk_managed_gate":
        b=ctx.get(benchmark)
        if b is None or not b["eligible"]:
            return {}
    # Annual portfolio vol budget spread across up to N positions;
    # each asset's estimated vol may be smaller in future.
    # Asset cap and 100% gross portfolio cap take priority.
    target=PARAMS["target_vol_"+market]
    cap=PARAMS["risk_cap_"+market]
    selected={}
    for s in leaders:
        vol=ctx[s]["vol"]
        if vol<=0:continue
        selected[s]=min(cap,target/(vol*sqrt(slots)))
    total=sum(selected.values())
    if total>1:
        selected={s:w/total for s,w in selected.items()}
    return selected


def diagnostics(marked,cash,holdings,prices):
    gross=sum(q*prices[s] for s,q in holdings.items())
    equity=cash+gross
    if cash< -1e-6:
        raise AssertionError("negative cash indicates implicit borrowing")
    if gross>equity+1e-6:
        raise AssertionError("cash-only gross notional > equity")
    return equity,gross/equity if equity>0 else 0.0


def simulate(packs,market,mode,start_day,end_day,symbols=None,
             benchmark=None,cost=0.0006,cash_annual_yield=0.0):
    if mode not in MODES:raise ValueError(mode)
    if cash_annual_yield<0 or cash_annual_yield>0.30:
        raise ValueError("cash scenario annual yield outside allowable research range")
    if market not in ("crypto","stock"):raise ValueError(market)
    benchmark=benchmark or ("BTCUSDT" if market=="crypto" else "SPY")
    symbols=sorted(symbols or ([s for s in packs if s!="SPY"] if market=="stock"
                                else ["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT"]))
    available=set(symbols+[benchmark])
    if any(s not in packs for s in available):
        raise ValueError("missing symbol price dataset")
    daily={s:{r["day"]:r for r in packs[s]["daily"]} for s in available}
    reference=[r["day"] for r in packs[benchmark]["daily"]
               if start_day<=r["day"]<end_day]
    cash=INITIAL;qty={};prices={}
    ledger=[];curve=[];last_month=None;last_week=None;first_trade=False
    last_day=None
    counts=Counter()
    for day in reference:
        if last_day is not None and cash_annual_yield:
            days=(datetime.fromisoformat(day)-datetime.fromisoformat(last_day)).days
            cash*=(1+cash_annual_yield)**(days/365.25)
        last_day=day
        opened={s:r[day] for s,r in daily.items() if day in r}
        if benchmark not in opened:raise AssertionError("benchmark date missing")
        for s,b in opened.items():
            if not b["o"]>0 or not b["c"]>0:raise ValueError("bad daily price")
        opens={s:opened[s]["o"] for s in opened}
        # When no trading in a stock, mark its last completed close;
        # NEVER assume an unobserved executable OPEN.
        current_open_marks={s:(opens[s] if s in opened else prices.get(s))
                            for s in qty}
        if any(p is None for p in current_open_marks.values()):
            raise AssertionError("unmarked open position")
        at_open_equity=cash+sum(qty[s]*px for s,px in current_open_marks.items())
        month=day[:7]
        iso=datetime.fromisoformat(day).isocalendar()
        week=(iso.year,iso.week)
        rebalance=(week!=last_week if mode=="gate_weekly" else month!=last_month)
        if mode in ("benchmark_hold","equal_hold") and first_trade:
            rebalance=False
        if rebalance:
            target=weights(mode,market,day,packs,symbols,benchmark,opened)
            if sum(target.values())>1+EPS or any(w<0 for w in target.values()):
                raise AssertionError("unsafe target weights")
            before_qty=qty.copy()
            # Sell positions BEFORE making any new buys. On missing
            # stock trading days, cannot sell without a fill quote.
            for s in sorted(before_qty):
                if s not in opened:
                    counts["not_tradeable_sell"]+=1
                    continue
                desired=target.get(s,0)*at_open_equity/opens[s]
                size=max(0,qty[s]-desired)
                if mode not in ("equal_hold","benchmark_hold") and (
                    size*opens[s]<PARAMS["rebalance_band_pct_equity"]*at_open_equity):
                    continue
                if size>EPS:
                    notional=size*opens[s]
                    fee=cost*notional
                    cash+=notional-fee;qty[s]-=size
                    ledger.append({"date":day,"symbol":s,"action":"SELL",
                                   "quantity":size,"price":opens[s],
                                   "fee":fee,"notional":notional})
                    counts["sells"]+=1
                    if qty[s]<=EPS:qty.pop(s,None)
            # Target value from PRE-TRADE observed equity. Buys can
            # never exceed now-reserved available cash incl fees.
            desires=[]
            for s,w in target.items():
                if s not in opened:continue
                desired_qty=w*at_open_equity/opens[s]
                deficit=desired_qty-qty.get(s,0)
                if deficit<=EPS:continue
                value=deficit*opens[s]
                if mode not in ("equal_hold","benchmark_hold") and (
                    value<PARAMS["rebalance_band_pct_equity"]*at_open_equity):
                    continue
                desires.append((-value,s,deficit))
            for _,s,deficit in sorted(desires):
                px=opens[s]
                size=min(deficit,max(0.,cash)/(px*(1+cost)))
                if size<=EPS:
                    counts["no_cash"]+=1
                    continue
                notional=size*px;fee=cost*notional
                cash-=notional+fee;qty[s]=qty.get(s,0)+size
                ledger.append({"date":day,"symbol":s,"action":"BUY",
                               "quantity":size,"price":px,
                               "fee":fee,"notional":notional})
                counts["buys"]+=1
            if not first_trade and ledger:
                first_trade=True
            last_month=month
            last_week=week
        for s,b in opened.items():prices[s]=b["c"]
        final_prices={s:prices.get(s) for s in qty}
        if any(p is None for p in final_prices.values()):raise AssertionError("missing close")
        equity,exposure=diagnostics(day,cash,qty,final_prices)
        curve.append({"day":day,"equity":equity,"cash":cash,
                      "gross":equity-cash,"exposure":exposure,
                      "n_assets":len(qty)})
    if not curve:raise ValueError("empty evaluation window")
    peak=INITIAL;mdd=0.
    for x in curve:
        peak=max(peak,x["equity"])
        mdd=max(mdd,(peak-x["equity"])/peak)
    ann={}
    for x in curve:
        yr=x["day"][:4]
        if yr not in ann:ann[yr]={"open_equity":INITIAL if not ann else
                                        list(ann.values())[-1]["end_equity"]}
        ann[yr]["end_equity"]=x["equity"]
    for yr,d in ann.items():
        d["return_pct"]=100*(d["end_equity"]/d["open_equity"]-1)
    total_return=100*(curve[-1]["equity"]/INITIAL-1)
    years=(datetime.fromisoformat(end_day)-datetime.fromisoformat(start_day)).days/365.25
    cagr=((curve[-1]["equity"]/INITIAL)**(1/years)-1)*100 if years>0 and curve[-1]["equity"]>0 else None
    notionals=sum(x["notional"] for x in ledger)
    metric={
       "total_return_pct":total_return,"cagr_pct":cagr,"mdd_pct":100*mdd,
       "calmar":cagr/(100*mdd) if mdd>0 else None,
       "final_equity":curve[-1]["equity"],
       "avg_exposure":statistics.fmean(x["exposure"] for x in curve),
       "max_exposure":max(x["exposure"] for x in curve),
       "days":len(curve),"execution_count":len(ledger),
       "turnover_gross_over_initial":notionals/INITIAL,
       "paid_fees":sum(x["fee"] for x in ledger),
       "assumed_cash_annual_yield":cash_annual_yield,
       "by_year":ann,"events":dict(counts)
    }
    return {"mode":mode,"market":market,"metrics":metric,
            "ledger":ledger,"curve":curve}
