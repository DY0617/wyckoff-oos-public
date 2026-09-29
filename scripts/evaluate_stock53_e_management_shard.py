import json, os, statistics, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).parent))
import evaluate_stock53_filter_factorial_shard as f
import wyckoff_status as w

BASE=Path("data/validation/stock53_track_b_hf_20y_exact_touch.json")
OUT=Path(os.environ["OUT"])
FEE_BPS=4.0
SLIP_BPS=2.0
COST_BPS=FEE_BPS+SLIP_BPS
RISK=400.0
CAP=20000.0

MODES={
    "30_30_40":(0.30,0.30,0.40),
    "20_30_50":(0.20,0.30,0.50),
    "15_25_60":(0.15,0.25,0.60),
}

def recalc_trade(t, fracs):
    tp1f,tp2f,runf=fracs
    size=float(t["size"]); entry=float(t["entry"])
    sign=1.0 if t["direction"]=="LONG" else -1.0
    events=t.get("events") or []
    pnl=-size*entry*COST_BPS/10000.0

    tp1=next((e for e in events if e.get("type")=="TP1"),None)
    tp2=next((e for e in events if e.get("type")=="TP2"),None)
    final=next((e for e in reversed(events) if e.get("type") in ("STOP","BE")),None)

    if tp1 is None:
        if final is None: return None
        px=float(final["price"])
        pnl += size*sign*(px-entry) - size*px*COST_BPS/10000.0
    elif tp2 is None:
        p1=float(tp1["price"])
        pnl += tp1f*size*sign*(p1-entry) - tp1f*size*p1*COST_BPS/10000.0
        if final is None: return None
        px=float(final["price"]); rem=1.0-tp1f
        pnl += rem*size*sign*(px-entry) - rem*size*px*COST_BPS/10000.0
    else:
        p1=float(tp1["price"]); p2=float(tp2["price"])
        pnl += tp1f*size*sign*(p1-entry) - tp1f*size*p1*COST_BPS/10000.0
        pnl += tp2f*size*sign*(p2-entry) - tp2f*size*p2*COST_BPS/10000.0
        if final is None: return None
        px=float(final["price"])
        pnl += runf*size*sign*(px-entry) - runf*size*px*COST_BPS/10000.0
    z=dict(t);z["pnl_recalc"]=pnl;z["r_recalc"]=pnl/RISK
    return z

def summarize(ts):
    ordered=sorted(ts,key=lambda t:(t["exit_t"],t["symbol"]))
    rs=[t["r_recalc"] for t in ordered]
    pos=[x for x in rs if x>0];neg=[x for x in rs if x<0]
    eq=CAP;peak=CAP;mdd=0;cur=mx=0
    for t in ordered:
        eq+=t["pnl_recalc"];peak=max(peak,eq);mdd=max(mdd,(peak-eq)/peak if peak else 0)
        if t["pnl_recalc"]<0:cur+=1;mx=max(mx,cur)
        else:cur=0
    return {
      "trades":len(ordered),
      "wins":sum(t["pnl_recalc"]>0 for t in ordered),
      "losses":sum(t["pnl_recalc"]<0 for t in ordered),
      "win_rate":sum(t["pnl_recalc"]>0 for t in ordered)/len(ordered) if ordered else None,
      "net_r":sum(rs),
      "avg_r":statistics.fmean(rs) if rs else None,
      "profit_factor":sum(pos)/abs(sum(neg)) if neg else None,
      "max_drawdown_fixed_20k":mdd,
      "max_drawdown_r":mdd*CAP/RISK,
      "max_consecutive_losses":mx
    }

def main():
    base=json.loads(BASE.read_text())
    lo=int(f.EVAL_START.timestamp()*1000);hi=int(f.EVAL_END.timestamp()*1000)
    trades=[t for t in base["trades"] if lo<=t["entry_t"]<hi and t["direction"]=="LONG"]

    by,months=f.collect()
    dailies={}
    for s in f.SYMS:
        bars=f.apply_splits(by[s],f.detect_splits(by[s]))
        if bars:dailies[s]=w.enrich(bars)

    eligible=[]
    for t in trades:
        st=f.state_for(t["symbol"],dailies,t["entry_t"])
        if not st:continue
        if st["spy_regime"] and st["rs_ok"] and st["breadth_ok"]:
            eligible.append(t)

    modes={}
    for name,fracs in MODES.items():
        xs=[]
        for t in eligible:
            z=recalc_trade(t,fracs)
            if z is not None:xs.append(z)
        yrs=defaultdict(list)
        for t in xs:
            yrs[str(datetime.fromtimestamp(t["entry_t"]/1000,timezone.utc).year)].append(t)
        modes[name]={
          "summary":summarize(xs),
          "years":{k:summarize(v) for k,v in sorted(yrs.items())},
          "trades":[{"symbol":t["symbol"],"entry_t":t["entry_t"],"exit_t":t["exit_t"],
                     "pnl_recalc":t["pnl_recalc"],"r_recalc":t["r_recalc"]} for t in xs]
        }

    out={
      "period":{"start":f.EVAL_START.isoformat(),"end_exclusive":f.EVAL_END.isoformat()},
      "months_loaded":months,
      "filter":"LONG + SPY bull regime + stock ret20>=SPY ret20 + breadth>=50%",
      "eligible_trades":len(eligible),
      "modes":modes
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print("FINAL",json.dumps(out,ensure_ascii=False,indent=2),flush=True)

if __name__=="__main__":main()
