import json, os, sys
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).parent))
import backtest_us_30x2_track_b_25y as base
import backtest_wyckoff_stock_filter_engine as bt
import wyckoff_status as w

UTC=timezone.utc
DOW=base.DOW2000
ALL=tuple(list(DOW)+["SPY"])
TRADE_SYMS=tuple(x for x in os.environ.get("TRADE_SYMS","").split(",") if x) or DOW
OUT=Path(os.environ["OUT"])
CAP=base.CAP;RISK=base.RISK

def ret20(D,i):
    if i<20 or D[i-20]["c"]<=0:return None
    return D[i]["c"]/D[i-20]["c"]-1

def latest_idx(D,ts):
    cts=[x["ct"] for x in D]
    return bisect_left(cts,ts)-1

def state_for(sym,dailies,ts):
    D=dailies.get(sym); S=dailies.get("SPY")
    if not D or not S:return None
    i=latest_idx(D,ts);si=latest_idx(S,ts)
    if i<50 or si<50:return None
    rr=ret20(D,i);sr=ret20(S,si)
    if rr is None or sr is None:return None
    s=S[si]
    votes=int(s["c"]>s["ema50"])+int(s["ema20"]>s["ema50"])+int(sr>0)
    eligible=above=0
    for u in DOW:
        U=dailies.get(u)
        if not U:continue
        ui=latest_idx(U,ts)
        if ui>=50 and U[ui].get("ema50") is not None:
            eligible+=1;above+=int(U[ui]["c"]>U[ui]["ema50"])
    breadth=above/eligible if eligible else None
    return {
      "spy_regime":votes>=2,
      "rs_ok":rr>=sr,
      "breadth_ok":breadth is not None and breadth>=.50
    }

def eligible(sym,dailies,ts,direction):
    if direction!="LONG":return False
    st=state_for(sym,dailies,ts)
    return bool(st and st["spy_regime"] and st["rs_ok"] and st["breadth_ok"])

def trade_key(t):
    return (t["symbol"],t["entry_t"],round(float(t["entry"]),8),round(float(t["stop"]),8),
            round(float(t["target"]),8),round(float(t.get("tp1") or 0),8))

def slim(t):
    return {"symbol":t["symbol"],"entry_t":t["entry_t"],"exit_t":t["exit_t"],
            "entry":t["entry"],"stop":t["stop"],"target":t["target"],"tp1":t.get("tp1"),
            "pnl":t["pnl"],"r":t["r"],"reason":t["reason"]}

def main():
    bysym,files=base.load_all(ALL)
    cache={};dailies={};errors={}
    for sym in ALL:
        try:
            bars=bysym[sym]
            if len(bars)<1000:raise RuntimeError(f"insufficient bars {len(bars)}")
            bars=base.apply_splits(bars,base.detect_splits(bars))
            H=w.enrich(base.aggregate_4h(bars))
            daily=base.aggregate_daily(bars)
            for z in daily:z["ct"]=z["t"]+390*60_000-1
            D=w.enrich(daily);M=bars
            cache[sym]=(D,H,M);dailies[sym]=D
        except Exception as e:
            errors[sym]=repr(e)

    modes={"POST":[],"PRE_TRIGGER":[],"PRE_SETUP":[]}
    audits={"PRE_TRIGGER":{"filtered":0},"PRE_SETUP":{"filtered":0}}
    old_dataset,old_filters=bt.dataset,bt.symbol_filters
    old_cap,old_risk=bt.CAP,bt.RISK
    bt.CAP=CAP;bt.RISK=RISK
    try:
        for sym in TRADE_SYMS:
            if sym not in cache:continue
            D,H,M=cache[sym]
            bt._CACHE.clear();bt.dataset=lambda _s,D=D,H=H,M=M:(D,H,M);bt.symbol_filters=lambda _s:(0.01,0.0,0.0)

            # A: original research semantics, then filter completed trades by entry time.
            r=bt.simulate(sym,base.A_OFF,{},int(base.GLOBAL_EVAL_START.timestamp()*1000),
                          int(base.EVAL_END.timestamp()*1000)-1,base.FEE_BPS,base.SLIPPAGE_BPS,
                          a_mode="snapshot",b_runner_mode="pivot",b_scale_mode="15_25_60")
            for t in r["trades"]:
                if t["track"]=="B" and t["reason"]!="OPEN_MARK" and eligible(sym,dailies,t["entry_t"],t["direction"]):
                    modes["POST"].append({"symbol":sym,**t})

            def trig_filter(_sym,p,trigger_open_ms):
                return eligible(sym,dailies,trigger_open_ms,p["direction"])
            r=bt.simulate(sym,base.A_OFF,{},int(base.GLOBAL_EVAL_START.timestamp()*1000),
                          int(base.EVAL_END.timestamp()*1000)-1,base.FEE_BPS,base.SLIPPAGE_BPS,
                          a_mode="snapshot",b_runner_mode="pivot",b_scale_mode="15_25_60",
                          trigger_filter=trig_filter)
            modes["PRE_TRIGGER"] += [{"symbol":sym,**t} for t in r["trades"] if t["track"]=="B" and t["reason"]!="OPEN_MARK"]
            audits["PRE_TRIGGER"]["filtered"] += sum(1 for a in r.get("setup_audit",[]) if a.get("reason")=="TRIGGER_FILTERED")

            def setup_filter(_sym,p,setup_open_ms):
                return eligible(sym,dailies,setup_open_ms,p["direction"])
            r=bt.simulate(sym,base.A_OFF,{},int(base.GLOBAL_EVAL_START.timestamp()*1000),
                          int(base.EVAL_END.timestamp()*1000)-1,base.FEE_BPS,base.SLIPPAGE_BPS,
                          a_mode="snapshot",b_runner_mode="pivot",b_scale_mode="15_25_60",
                          setup_filter=setup_filter)
            modes["PRE_SETUP"] += [{"symbol":sym,**t} for t in r["trades"] if t["track"]=="B" and t["reason"]!="OPEN_MARK"]
            audits["PRE_SETUP"]["filtered"] += sum(1 for a in r.get("setup_audit",[]) if a.get("reason")=="SETUP_FILTERED")
            print("DONE",sym,{k:sum(t["symbol"]==sym for t in v) for k,v in modes.items()},flush=True)
    finally:
        bt.dataset,bt.symbol_filters=old_dataset,old_filters;bt.CAP,bt.RISK=old_cap,old_risk

    summaries={k:base.trade_summary(v) for k,v in modes.items()}
    sets={k:{trade_key(t) for t in v} for k,v in modes.items()}
    parity={}
    for k in ("PRE_TRIGGER","PRE_SETUP"):
        common=sets["POST"]&sets[k]
        only_post=sets["POST"]-sets[k];only_pre=sets[k]-sets["POST"]
        common_post={trade_key(t):t for t in modes["POST"]}
        common_pre={trade_key(t):t for t in modes[k]}
        pnl_diff=max([abs(common_post[x]["pnl"]-common_pre[x]["pnl"]) for x in common] or [0.0])
        parity[k]={
          "exact_trade_set_match":sets["POST"]==sets[k],
          "common_trades":len(common),"only_post":len(only_post),"only_pre":len(only_pre),
          "max_abs_pnl_diff_common":pnl_diff,
          "only_post_keys":[list(x) for x in sorted(only_post)[:100]],
          "only_pre_keys":[list(x) for x in sorted(only_pre)[:100]]
        }

    OUT.parent.mkdir(parents=True,exist_ok=True)
    out={
      "purpose":"Stock Track-B E live-ordering parity: post-filter vs pre-trigger vs pre-setup",
      "symbols":list(TRADE_SYMS),"breadth_universe":list(DOW),
      "period":{"start":base.GLOBAL_EVAL_START.isoformat(),"end_exclusive":base.EVAL_END.isoformat()},
      "management":"15/25/60 + confirmed RTH 4H pivot runner",
      "summaries":summaries,"parity":parity,"filter_audit":audits,"errors":errors,
      "trades":{k:[slim(t) for t in sorted(v,key=lambda z:(z["entry_t"],z["symbol"]))] for k,v in modes.items()}
    }
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print("FINAL",json.dumps({k:v for k,v in out.items() if k!="trades"},ensure_ascii=False,indent=2),flush=True)

if __name__=="__main__":main()
