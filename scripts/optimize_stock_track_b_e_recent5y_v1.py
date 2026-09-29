import json, math, statistics, sys
from itertools import product
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).parent))
import evaluate_stock70_e_vs_53_e_5y as src

UTC=timezone.utc
BASE50=Path("data/validation/stock50_track_b_hf_5y_exact_touch.json")
ADD20=Path("data/validation/stock20_added_track_b_hf_5y_exact_touch.json")
OUT=Path("data/validation/stock_track_b_e_recent5y_param_opt_v1.json")

START_MS=int(datetime(2021,4,1,tzinfo=UTC).timestamp()*1000)
MID_MS=int(datetime(2023,10,1,tzinfo=UTC).timestamp()*1000)
END_MS=int(datetime(2026,4,1,tzinfo=UTC).timestamp()*1000)
COST=.0006
RISK=400.0

VOTES=(2,3)
LOOKBACKS=(10,20,30,40)
BREADTHS=(.40,.50,.60)
MODES={
 "30_30_40":(.30,.30,.40),
 "20_30_50":(.20,.30,.50),
 "15_25_60":(.15,.25,.60),
 "10_30_60":(.10,.30,.60),
}

def idx(D,t):
    import bisect
    return bisect.bisect_left([x["ct"] for x in D],t)-1

def ret(D,i,n):
    return D[i]["c"]/D[i-n]["c"]-1 if i>=n and D[i-n]["c"]>0 else None

def context(t,dailies,universe,lookback):
    if t["direction"]!="LONG":return None
    spy=dailies.get("SPY"); D=dailies.get(t["symbol"])
    if not spy or not D:return None
    si=idx(spy,t["entry_t"]);i=idx(D,t["entry_t"])
    if si<50 or i<50:return None
    sr=ret(spy,si,lookback);rr=ret(D,i,lookback)
    if sr is None or rr is None:return None
    s=spy[si]
    votes=int(s["c"]>s["ema50"])+int(s["ema20"]>s["ema50"])+int(sr>0)
    above=eligible=0
    for sym in universe:
        U=dailies.get(sym)
        if not U:continue
        ui=idx(U,t["entry_t"])
        if ui>=50 and U[ui].get("ema50") is not None:
            eligible+=1;above+=int(U[ui]["c"]>U[ui]["ema50"])
    breadth=above/eligible if eligible else None
    return {"votes":votes,"rr":rr,"sr":sr,"breadth":breadth,"breadth_n":eligible}

def recalc(t,mode):
    f1,f2,fr=MODES[mode]
    size=float(t["size"]);entry=float(t["entry"]);sign=1.0 if t["direction"]=="LONG" else -1.0
    evs=t.get("events") or []
    pnl=-size*entry*COST
    e1=next((e for e in evs if e.get("type")=="TP1"),None)
    e2=next((e for e in evs if e.get("type")=="TP2"),None)
    final=next((e for e in reversed(evs) if e.get("type") in ("STOP","BE")),None)
    if e1 is None:
        if final is None:return None
        px=float(final["price"])
        pnl+=size*sign*(px-entry)-size*px*COST
    elif e2 is None:
        p1=float(e1["price"])
        pnl+=f1*size*sign*(p1-entry)-f1*size*p1*COST
        if final is None:return None
        px=float(final["price"]);rem=1-f1
        pnl+=rem*size*sign*(px-entry)-rem*size*px*COST
    else:
        p1=float(e1["price"]);p2=float(e2["price"])
        pnl+=f1*size*sign*(p1-entry)-f1*size*p1*COST
        pnl+=f2*size*sign*(p2-entry)-f2*size*p2*COST
        if final is None:return None
        px=float(final["price"])
        pnl+=fr*size*sign*(px-entry)-fr*size*px*COST
    z={"symbol":t["symbol"],"entry_t":t["entry_t"],"exit_t":t["exit_t"],"r":pnl/RISK,"pnl":pnl}
    return z

def stats(ts):
    ts=sorted(ts,key=lambda x:(x["exit_t"],x["symbol"]))
    n=len(ts);rs=[x["r"] for x in ts]
    gp=sum(x for x in rs if x>0);gl=-sum(x for x in rs if x<0)
    cr=peak=mdd=0.0;st=mx=0
    for x in ts:
        cr+=x["r"];peak=max(peak,cr);mdd=max(mdd,peak-cr)
        if x["r"]<0:st+=1;mx=max(mx,st)
        else:st=0
    return {
      "trades":n,"wins":sum(x>0 for x in rs),"losses":sum(x<0 for x in rs),
      "win_rate":sum(x>0 for x in rs)/n if n else None,
      "net_r":sum(rs),"avg_r":statistics.fmean(rs) if rs else None,
      "profit_factor":gp/gl if gl>0 else None,
      "max_drawdown_r":mdd,"max_consecutive_losses":mx
    }

def yearly(ts):
    d={}
    for y in range(2021,2027):
        xs=[x for x in ts if datetime.fromtimestamp(x["entry_t"]/1000,UTC).year==y]
        if xs:d[str(y)]=stats(xs)
    return d

def score(full,early,late,yrs):
    avgs=[v["avg_r"] for v in yrs.values() if v["avg_r"] is not None]
    disp=statistics.pstdev(avgs) if len(avgs)>1 else 0.0
    gap=abs((early["avg_r"] or 0)-(late["avg_r"] or 0))
    instability=disp+gap
    val=(.35*(full["avg_r"] or 0)+
         .20*min(early["avg_r"] or 0,late["avg_r"] or 0)+
         .15*min(early["profit_factor"] or 0,late["profit_factor"] or 0)+
         .10*(full["profit_factor"] or 0)-
         .10*full["max_drawdown_r"]-
         .10*instability)
    return val,instability

def surviving(full,early,late):
    return (full["trades"]>=40 and
            (early["profit_factor"] or 0)>=1.20 and (late["profit_factor"] or 0)>=1.20 and
            early["net_r"]>0 and late["net_r"]>0 and
            full["max_consecutive_losses"]<=7 and full["max_drawdown_r"]<=10)

def neighbor(a,b):
    # One grid step in exactly one dimension, or identical in three and adjacent in one.
    vals=[VOTES,LOOKBACKS,BREADTHS,tuple(MODES)]
    aa=(a["params"]["spy_votes_min"],a["params"]["rs_lookback"],a["params"]["breadth_min"],a["params"]["management"])
    bb=(b["params"]["spy_votes_min"],b["params"]["rs_lookback"],b["params"]["breadth_min"],b["params"]["management"])
    diff=0
    for x,y,grid in zip(aa,bb,vals):
        if x==y:continue
        ix=grid.index(x);iy=grid.index(y)
        if abs(ix-iy)!=1:return False
        diff+=1
    return diff==1

def main():
    b50=json.loads(BASE50.read_text());a20=json.loads(ADD20.read_text())
    set53=set(src.SYMS53)
    trades=[x for x in (b50["trades"]+a20["trades"]) if x["symbol"] in set53 and START_MS<=x["entry_t"]<END_MS]
    trades=sorted(trades,key=lambda x:(x["entry_t"],x["symbol"]))
    print("BASE_TRADES",len(trades),flush=True)
    dailies=src.collect()
    # Precompute contexts for each lookback.
    ctx={}
    for lb in LOOKBACKS:
        for t in trades:
            ctx[(t["symbol"],t["entry_t"],lb)]=context(t,dailies,src.SYMS53,lb)
    # Precompute management R for every base trade.
    managed={}
    for mode in MODES:
        for t in trades:
            managed[(t["symbol"],t["entry_t"],mode)]=recalc(t,mode)

    rows=[]
    for votes,lb,br,mode in product(VOTES,LOOKBACKS,BREADTHS,MODES):
        kept=[]
        for t in trades:
            c=ctx[(t["symbol"],t["entry_t"],lb)]
            if c is None:continue
            if c["votes"]>=votes and c["rr"]>=c["sr"] and c["breadth"] is not None and c["breadth"]>=br:
                z=managed[(t["symbol"],t["entry_t"],mode)]
                if z is not None:kept.append(z)
        full=stats(kept)
        early=stats([x for x in kept if x["entry_t"]<MID_MS])
        late=stats([x for x in kept if x["entry_t"]>=MID_MS])
        yrs=yearly(kept)
        sc,inst=score(full,early,late,yrs)
        ok=surviving(full,early,late)
        rows.append({
          "params":{"spy_votes_min":votes,"rs_lookback":lb,"breadth_min":br,"management":mode},
          "full":full,"early":early,"late":late,"years":yrs,
          "score":sc,"instability_penalty":inst,"survives":ok
        })

    # Plateau diagnostics: adjacent-grid survival and score.
    for a in rows:
        ns=[b for b in rows if neighbor(a,b)]
        a["plateau"]={
          "neighbors":len(ns),
          "surviving_neighbors":sum(x["survives"] for x in ns),
          "survival_rate":sum(x["survives"] for x in ns)/len(ns) if ns else None,
          "neighbor_mean_score":statistics.fmean(x["score"] for x in ns) if ns else None,
          "neighbor_min_full_pf":min((x["full"]["profit_factor"] or 0) for x in ns) if ns else None,
          "neighbor_min_full_net_r":min(x["full"]["net_r"] for x in ns) if ns else None
        }

    ranked=sorted(rows,key=lambda x:(x["survives"],x["score"]),reverse=True)
    survivors=[x for x in ranked if x["survives"]]
    # Robust plateau pick: among survivors with >=60% adjacent survival, choose best score.
    plateau_pool=[x for x in survivors if (x["plateau"]["survival_rate"] or 0)>=.60]
    plateau_pick=max(plateau_pool,key=lambda x:x["score"]) if plateau_pool else (survivors[0] if survivors else None)
    baseline=next(x for x in rows if x["params"]=={"spy_votes_min":2,"rs_lookback":20,"breadth_min":.50,"management":"15_25_60"})
    out={
      "generated_at":datetime.now(UTC).isoformat(),
      "period":{"start":"2021-04-01","mid":"2023-10-01","end_exclusive":"2026-04-01"},
      "base_trades":len(trades),
      "grid":{"spy_votes_min":list(VOTES),"rs_lookback":list(LOOKBACKS),"breadth_min":list(BREADTHS),"management":list(MODES),"combinations":len(rows)},
      "constraints":{"min_trades":40,"min_pf_each_half":1.20,"positive_each_half":True,"max_losing_streak":7,"max_dd_r":10},
      "baseline":baseline,
      "best_raw_score":ranked[0],
      "best_survivor":survivors[0] if survivors else None,
      "plateau_pick":plateau_pick,
      "survivor_count":len(survivors),
      "top20":ranked[:20],
      "all_results":rows
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print("SURVIVORS",len(survivors),flush=True)
    print("BASELINE",json.dumps(baseline,ensure_ascii=False),flush=True)
    print("BEST",json.dumps(survivors[0] if survivors else ranked[0],ensure_ascii=False),flush=True)
    print("PLATEAU",json.dumps(plateau_pick,ensure_ascii=False),flush=True)

if __name__=="__main__":
    main()
