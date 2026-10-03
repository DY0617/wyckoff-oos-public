import json, math, statistics, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).parent))
import backtest_us_30x2_track_b_25y as base
import backtest_us_dow2000_track_b_e_15_25_60_oos_v1 as tb
import backtest_wyckoff_runner_sweep_engine as bt
import wyckoff_status as w

UTC=timezone.utc
ROOT=Path(__file__).resolve().parents[1]
ELL=ROOT/"data/validation/elliott_wave3_v4_dow2000_1h_long_25y.json"
OUT=ROOT/"data/validation/portfolio_track_b_e_plus_elliott_v4_dow2000_25y.json"

CAP=20000.0
ONE_R_USD=400.0

def portfolio_metrics(trades, weights):
    xs=[]
    for t in trades:
        wt=weights.get(t["strategy"],0.0)
        if wt<=0:continue
        q=dict(t);q["weighted_r"]=t["r"]*wt;xs.append(q)
    xs.sort(key=lambda z:(z["exit_t"],z["strategy"],z["symbol"]))
    rs=[x["weighted_r"] for x in xs]
    pos=[r for r in rs if r>0];neg=[r for r in rs if r<0]
    eq=peak=0.0;dd=0.0;cur=mx=0
    for r in rs:
        eq+=r;peak=max(peak,eq);dd=min(dd,eq-peak)
        if r<0:cur+=1;mx=max(mx,cur)
        else:cur=0
    return {
      "trades":len(xs),"total_r":sum(rs),"avg_weighted_r":statistics.fmean(rs) if rs else None,
      "profit_factor":sum(pos)/abs(sum(neg)) if neg else None,
      "win_rate":len(pos)/len(xs) if xs else None,
      "max_drawdown_r":dd,
      "max_drawdown_pct_on_20k_400R":abs(dd)*ONE_R_USD/CAP,
      "max_losing_streak":mx,
      "ending_equity_fixed_risk":CAP+sum(rs)*ONE_R_USD,
    }

def monthly_series(trades,strategy):
    vals=defaultdict(float)
    for t in trades:
        if t["strategy"]!=strategy:continue
        dt=datetime.fromtimestamp(t["exit_t"]/1000,UTC)
        vals[f"{dt.year:04d}-{dt.month:02d}"]+=t["r"]
    return vals

def annual_series(trades,strategy):
    vals=defaultdict(float)
    for t in trades:
        if t["strategy"]!=strategy:continue
        dt=datetime.fromtimestamp(t["exit_t"]/1000,UTC)
        vals[str(dt.year)]+=t["r"]
    return vals

def corr(a,b,keys):
    x=[a.get(k,0.0) for k in keys];y=[b.get(k,0.0) for k in keys]
    if len(x)<2:return None
    mx=statistics.fmean(x);my=statistics.fmean(y)
    sx=sum((v-mx)**2 for v in x);sy=sum((v-my)**2 for v in y)
    if sx<=0 or sy<=0:return None
    return sum((i-mx)*(j-my) for i,j in zip(x,y))/math.sqrt(sx*sy)

def concurrency(trades):
    events=[]
    for t in trades:
        events.append((t["entry_t"],1,t["strategy"],t["symbol"]))
        events.append((t["exit_t"],-1,t["strategy"],t["symbol"]))
    # exits before entries at same timestamp
    events.sort(key=lambda e:(e[0],e[1]))
    active=0;mx=0;by=defaultdict(int);mxby=defaultdict(int)
    for _,d,s,_ in events:
        active+=d;by[s]+=d;mx=max(mx,active);mxby[s]=max(mxby[s],by[s])
    return {"max_total":mx,"max_by_strategy":dict(mxby)}

def overlap_stats(tb_trades,ell_trades):
    def ov(a,b):return max(a["entry_t"],b["entry_t"])<min(a["exit_t"],b["exit_t"])
    any_overlap=0;same_symbol=0
    for e in ell_trades:
        hits=[t for t in tb_trades if ov(e,t)]
        if hits:any_overlap+=1
        if any(t["symbol"]==e["symbol"] for t in hits):same_symbol+=1
    return {
      "elliott_trades":len(ell_trades),
      "elliott_overlapping_any_track_b":any_overlap,
      "elliott_overlap_any_rate":any_overlap/len(ell_trades) if ell_trades else None,
      "elliott_overlapping_same_symbol_track_b":same_symbol,
      "elliott_overlap_same_symbol_rate":same_symbol/len(ell_trades) if ell_trades else None,
    }

def cap_positions(trades,cap=5):
    accepted=[];skipped=[]
    for t in sorted(trades,key=lambda z:(z["entry_t"],0 if z["strategy"]=="TRACK_B_E" else 1,z["symbol"])):
        active=sum(1 for a in accepted if a["entry_t"]<=t["entry_t"]<a["exit_t"])
        if active>=cap:skipped.append(t)
        else:accepted.append(t)
    return accepted,skipped

def track_b_trades():
    bysym,files=base.load_all(tb.ALL)
    cache={};dailies={};errors={}
    old_dataset,old_filters=bt.dataset,bt.symbol_filters
    old_cap,old_risk=bt.CAP,bt.RISK
    bt.CAP=base.CAP;bt.RISK=base.RISK
    candidates=[]
    try:
        for sym in tb.ALL:
            try:
                bars=bysym[sym]
                if len(bars)<1000:raise RuntimeError(f"insufficient 15m bars {len(bars)}")
                bars=base.apply_splits(bars,base.detect_splits(bars))
                H=w.enrich(base.aggregate_4h(bars))
                daily=base.aggregate_daily(bars)
                for z in daily:z["ct"]=z["t"]+390*60_000-1
                D=w.enrich(daily);M=bars
                cache[sym]=(D,H,M);dailies[sym]=D
            except Exception as e:errors[sym]=repr(e)
        for sym in tb.DOW:
            if sym not in cache:continue
            D,H,M=cache[sym]
            bt._CACHE.clear();bt.dataset=lambda _s,D=D,H=H,M=M:(D,H,M);bt.symbol_filters=lambda _s:(0.01,0.0,0.0)
            r=bt.simulate(sym,base.A_OFF,{},int(base.GLOBAL_EVAL_START.timestamp()*1000),
                          int(base.EVAL_END.timestamp()*1000)-1,base.FEE_BPS,base.SLIPPAGE_BPS,
                          a_mode="snapshot",b_runner_mode="pivot",b_scale_mode="15_25_60")
            candidates += [{"symbol":sym,**t} for t in r["trades"]
                           if t["track"]=="B" and t["reason"]!="OPEN_MARK" and t["direction"]=="LONG"]
    finally:
        bt.dataset,bt.symbol_filters=old_dataset,old_filters;bt.CAP,bt.RISK=old_cap,old_risk
    elig=[]
    for t in candidates:
        st=tb.state_for(t["symbol"],dailies,t["entry_t"])
        if st and st["spy_regime"] and st["rs_ok"] and st["breadth_ok"]:
            elig.append({"strategy":"TRACK_B_E","symbol":t["symbol"],"entry_t":t["entry_t"],
                         "exit_t":t["exit_t"],"r":t["r"]})
    return elig,errors,[p.name for p in files]

def main():
    ell_obj=json.loads(ELL.read_text())
    ell=[{"strategy":"ELLIOTT_V4","symbol":t["symbol"],"entry_t":t["entry_t"],
          "exit_t":t["exit_t"],"r":t["r"]} for t in ell_obj["trades"]]
    track,errors,files=track_b_trades()
    if len(track)!=303:
        raise RuntimeError(f"Track B parity failure expected 303 got {len(track)}")

    alltr=track+ell
    months=[f"{y:04d}-{m:02d}" for y in range(2000,2026) for m in range(1,13)]
    years=[str(y) for y in range(2000,2026)]
    tm=monthly_series(alltr,"TRACK_B_E");em=monthly_series(alltr,"ELLIOTT_V4")
    ty=annual_series(alltr,"TRACK_B_E");ey=annual_series(alltr,"ELLIOTT_V4")

    capped,skipped=cap_positions(alltr,5)
    recent=[t for t in alltr if datetime.fromtimestamp(t["entry_t"]/1000,UTC).year>=2014]
    capped_recent,_=cap_positions(recent,5)

    report={
      "purpose":"Portfolio interaction test: frozen Stock Track B-E v1.0 + Elliott v4 on same DJIA2000 universe and 2000-2025 period.",
      "period":{"start":"2000-01-01","end_exclusive":"2026-01-01"},
      "universe":"DJIA constituents frozen at 2000-01",
      "source_chunks":files,
      "trade_counts":{"track_b_e":len(track),"elliott_v4":len(ell)},
      "standalone":{
        "track_b_e_1R":portfolio_metrics(track,{"TRACK_B_E":1.0}),
        "elliott_v4_1R":portfolio_metrics(ell,{"ELLIOTT_V4":1.0}),
      },
      "combined":{
        "raw_each_1R":portfolio_metrics(alltr,{"TRACK_B_E":1.0,"ELLIOTT_V4":1.0}),
        "equal_strategy_halfR_each":portfolio_metrics(alltr,{"TRACK_B_E":0.5,"ELLIOTT_V4":0.5}),
        "max5_open_initial_R_each1R":{
          "metrics":portfolio_metrics(capped,{"TRACK_B_E":1.0,"ELLIOTT_V4":1.0}),
          "accepted":len(capped),"skipped":len(skipped),
          "skipped_by_strategy":dict((s,sum(t["strategy"]==s for t in skipped)) for s in ("TRACK_B_E","ELLIOTT_V4"))
        }
      },
      "recent_2014plus":{
        "track_b_e":portfolio_metrics([t for t in recent if t["strategy"]=="TRACK_B_E"],{"TRACK_B_E":1.0}),
        "elliott_v4":portfolio_metrics([t for t in recent if t["strategy"]=="ELLIOTT_V4"],{"ELLIOTT_V4":1.0}),
        "combined_each1R":portfolio_metrics(recent,{"TRACK_B_E":1.0,"ELLIOTT_V4":1.0}),
        "combined_halfR_each":portfolio_metrics(recent,{"TRACK_B_E":0.5,"ELLIOTT_V4":0.5}),
        "max5_open_each1R":portfolio_metrics(capped_recent,{"TRACK_B_E":1.0,"ELLIOTT_V4":1.0}),
      },
      "correlation":{
        "monthly_realized_R_zero_filled":corr(tm,em,months),
        "annual_realized_R_zero_filled":corr(ty,ey,years),
        "monthly_track_b":dict(tm),"monthly_elliott":dict(em),
        "annual_track_b":dict(ty),"annual_elliott":dict(ey)
      },
      "concurrency":concurrency(alltr),
      "overlap":overlap_stats(track,ell),
      "errors":errors,
      "notes":[
        "All equity curves use realized trade R booked at exit, matching the existing fixed-risk research convention; no intratrade mark-to-market drawdown is modeled.",
        "Raw each-1R combined portfolio can carry more gross concurrent risk than either standalone strategy.",
        "Half-R each is a simple equal strategy-risk normalization, not volatility targeting.",
        "The 5R cap accepts entries first-come; exact ties prioritize Track B-E, then Elliott, because Track B-E is the independently validated production candidate.",
        "2014+ is descriptive/post-hoc because Elliott's recent-era strength was observed before this portfolio test."
      ],
      "trades":{"track_b_e":track,"elliott_v4":ell}
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print("FINAL",json.dumps({k:v for k,v in report.items() if k!="trades"},indent=2))

if __name__=="__main__":main()
