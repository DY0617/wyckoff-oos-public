import json, os, sys
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).parent))
import backtest_us_30x2_track_b_25y as base
import backtest_wyckoff_runner_sweep_engine as bt
import wyckoff_status as w

UTC=timezone.utc
DOW=base.DOW2000
ALL=tuple(list(DOW)+["SPY"])
OUT=Path(os.environ.get("OUT","data/validation/us_dow2000_track_b_e_15_25_60_oos_v1.json"))
TRADE_SYMS=tuple(x for x in os.environ.get("TRADE_SYMS","").split(",") if x) or DOW

def ret20(D,i):
    if i<20 or D[i-20]["c"]<=0:return None
    return D[i]["c"]/D[i-20]["c"]-1

def latest_idx(D,entry_t):
    cts=[x["ct"] for x in D]
    return bisect_left(cts,entry_t)-1

def state_for(sym,dailies,entry_t):
    D=dailies.get(sym); S=dailies.get("SPY")
    if not D or not S:return None
    i=latest_idx(D,entry_t); si=latest_idx(S,entry_t)
    if i<50 or si<50:return None
    rr=ret20(D,i); sr=ret20(S,si)
    if rr is None or sr is None:return None
    s=S[si]
    votes=int(s["c"]>s["ema50"])+int(s["ema20"]>s["ema50"])+int(sr>0)
    eligible=above=0
    for u in DOW:
        U=dailies.get(u)
        if not U:continue
        ui=latest_idx(U,entry_t)
        if ui>=50 and U[ui].get("ema50") is not None:
            eligible+=1
            above+=int(U[ui]["c"]>U[ui]["ema50"])
    breadth=above/eligible if eligible else None
    return {
      "spy_regime":votes>=2,
      "rs_ok":rr>=sr,
      "breadth":breadth,
      "breadth_ok":breadth is not None and breadth>=0.50,
      "eligible_breadth_symbols":eligible
    }

def block_for(t):
    y=datetime.fromtimestamp(t["entry_t"]/1000,UTC).year
    if y<2005:return "2000_2005"
    if y<2010:return "2005_2010"
    if y<2015:return "2010_2015"
    if y<2020:return "2015_2020"
    if y<2024:return "2020_2024"
    return "2024_2026"

def main():
    bysym,files=base.load_all(ALL)
    cache={};dailies={};errors={};all_candidates=[]
    old_dataset,old_filters=bt.dataset,bt.symbol_filters
    old_cap,old_risk=bt.CAP,bt.RISK
    bt.CAP=base.CAP;bt.RISK=base.RISK
    try:
        for sym in ALL:
            try:
                bars=bysym[sym]
                if len(bars)<1000:raise RuntimeError(f"insufficient 15m bars: {len(bars)}")
                splits=base.detect_splits(bars)
                bars=base.apply_splits(bars,splits)
                H=w.enrich(base.aggregate_4h(bars))
                daily=base.aggregate_daily(bars)
                for z in daily:
                    z["ct"]=z["t"]+390*60_000-1
                D=w.enrich(daily)
                M=bars
                cache[sym]=(D,H,M)
                dailies[sym]=D
            except Exception as e:
                errors[sym]=repr(e)
                print("PREP_ERROR",sym,repr(e),flush=True)

        for sym in TRADE_SYMS:
            if sym not in cache:continue
            D,H,M=cache[sym]
            first=datetime.fromtimestamp(M[0]["t"]/1000,UTC)
            eval_start=base.GLOBAL_EVAL_START
            if eval_start>=base.EVAL_END:continue
            bt._CACHE.clear()
            bt.dataset=lambda _s,D=D,H=H,M=M:(D,H,M)
            bt.symbol_filters=lambda _s:(0.01,0.0,0.0)
            r=bt.simulate(
                sym,base.A_OFF,{},
                int(eval_start.timestamp()*1000),int(base.EVAL_END.timestamp()*1000)-1,
                base.FEE_BPS,base.SLIPPAGE_BPS,
                a_mode="snapshot",b_runner_mode="pivot",b_scale_mode="15_25_60"
            )
            ts=[{"symbol":sym,**t} for t in r["trades"]
                if t["track"]=="B" and t["reason"]!="OPEN_MARK" and t["direction"]=="LONG"]
            all_candidates+=ts
            print("RAW",sym,len(ts),flush=True)
    finally:
        bt.dataset,bt.symbol_filters=old_dataset,old_filters
        bt.CAP,bt.RISK=old_cap,old_risk

    eligible=[];state_missing=0
    for t in all_candidates:
        st=state_for(t["symbol"],dailies,t["entry_t"])
        if not st:
            state_missing+=1;continue
        if st["spy_regime"] and st["rs_ok"] and st["breadth_ok"]:
            eligible.append(t)

    summary=base.trade_summary(eligible)
    by_symbol=base.grouped_stats(eligible,lambda t:t["symbol"])
    by_year=base.grouped_stats(eligible,lambda t:datetime.fromtimestamp(t["entry_t"]/1000,UTC).year)
    blocks={}
    for b in ("2000_2005","2005_2010","2010_2015","2015_2020","2020_2024","2024_2026"):
        blocks[b]=base.trade_summary([t for t in eligible if block_for(t)==b])

    positive_blocks=sum(v["net_r"]>0 for v in blocks.values())
    pass_flags={
      "net_r_positive":summary["net_r"]>0,
      "profit_factor_gt_1_30":(summary["profit_factor_r"] or 0)>1.30,
      "max_drawdown_lt_25r":summary["max_drawdown_fixed_20k"]*base.CAP/base.RISK<25,
      "at_least_4_of_6_blocks_positive":positive_blocks>=4
    }
    out={
      "purpose":"Independent-universe OOS validation of stock Track-B E + 15/25/60",
      "universe":"DJIA constituents frozen at 2000-01",
      "symbols":list(TRADE_SYMS),
      "breadth_universe":list(DOW),
      "period":{"start":base.GLOBAL_EVAL_START.isoformat(),"end_exclusive":base.EVAL_END.isoformat()},
      "data":{"chunks":[p.name for p in files],"session":"US RTH","provider":"Hugging Face mito0o852/OHLCV-1m"},
      "strategy":{
        "signal":"TRACK_B_V1_0_FROZEN exact-touch, LONG only",
        "filter":"SPY bull 2/3 + stock ret20>=SPY ret20 + breadth>=50% of available Dow2000",
        "management":"15% TP1=>BE; 25% TP2=>TP1; 60% confirmed RTH 4H pivot runner"
      },
      "costs":{"fee_bps":base.FEE_BPS,"slippage_bps":base.SLIPPAGE_BPS,"risk_usd":base.RISK},
      "raw_long_candidates":len(all_candidates),
      "eligible_trades":len(eligible),
      "state_missing":state_missing,
      "summary":summary,
      "by_symbol":by_symbol,
      "by_year":by_year,
      "blocks":blocks,
      "pass_criteria":{
        "required":{"net_r":">0","profit_factor":">1.30","max_drawdown_r":"<25","positive_blocks":">=4/6"},
        "positive_blocks":positive_blocks,
        "flags":pass_flags,
        "passed_all":all(pass_flags.values())
      },
      "trades":[{"symbol":t["symbol"],"entry_t":t["entry_t"],"exit_t":t["exit_t"],
                 "pnl":t["pnl"],"r":t["r"],"direction":t["direction"]} for t in eligible],
      "errors":errors,
      "limitations":[
        "Dow2000 membership is frozen at 2000-01; later constituent replacements are not added.",
        "Ticker continuity around mergers/delistings/reorganizations can be imperfect in raw historical data.",
        "Filter E is applied to completed Track-B trade candidates, matching the prior 53-stock filter study; filtered-out candidates may have occupied a one-position-per-symbol slot."
      ]
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print("FINAL",json.dumps(out,ensure_ascii=False,indent=2),flush=True)

if __name__=="__main__":main()
