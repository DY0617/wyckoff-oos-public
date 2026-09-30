import json,math,statistics
from collections import defaultdict,Counter
from datetime import datetime,timezone
from pathlib import Path

UTC=timezone.utc
ROOT=Path("data/validation/stock53_wf_shards")
OUT=Path("data/validation/stock53_track_b_walk_forward_v1.json")
FEE_BPS=4.0;SLIPPAGE_BPS=2.0;RISK=400.0

FOLDS={
 "f01":("2006-04-01","2012-04-01","2015-04-01"),
 "f02":("2009-04-01","2015-04-01","2018-04-01"),
 "f03":("2012-04-01","2018-04-01","2021-04-01"),
 "f04":("2015-04-01","2021-04-01","2024-04-01"),
 "f05":("2018-04-01","2024-04-01","2026-04-01"),
}
AXES=[
 ("rr_long_min",1.3),
 ("ema_gap_atr_max",1.5),
 ("trigger_window",12),
 ("test_spread_max",1.0),
 ("range_er_max",0.6),
]

def ms(s):
    return int(datetime.fromisoformat(s).replace(tzinfo=UTC).timestamp()*1000)

def recalc(t,f1=.15,f2=.15):
    sign=1 if t["direction"]=="LONG" else -1
    entry=float(t["entry"]);size=float(t["size"])
    cost=(FEE_BPS+SLIPPAGE_BPS)/10000.0
    realized=-size*entry*cost;remain=1.0
    for e in t.get("events",[]):
        typ=e.get("type")
        if typ=="TP1":
            frac=min(f1,remain);px=float(e["price"])
            realized+=frac*sign*(px-entry)*size-frac*size*px*cost;remain-=frac
        elif typ=="TP2":
            frac=min(f2,remain);px=float(e["price"])
            realized+=frac*sign*(px-entry)*size-frac*size*px*cost;remain-=frac
        elif typ in ("STOP","BE","OPEN_MARK","FIB1618_FULL","FIB1618_PARTIAL"):
            if remain<=1e-12:break
            px=float(e["price"]);frac=remain
            realized+=frac*sign*(px-entry)*size-frac*size*px*cost
            remain=0.0;break
    if remain>1e-8:
        raise RuntimeError(f"open remainder {remain}")
    q=dict(t);q["pnl"]=realized;q["r"]=realized/RISK
    return q

def stats(ts):
    ordered=sorted(ts,key=lambda x:(x["exit_t"],x["symbol"]))
    rs=[float(x["r"]) for x in ordered]
    gp=sum(x for x in rs if x>0);gl=-sum(x for x in rs if x<0)
    cr=peak=mdd=0.0;st=mx=0
    for r in rs:
        cr+=r;peak=max(peak,cr);mdd=max(mdd,peak-cr)
        if r<0:st+=1;mx=max(mx,st)
        else:st=0
    return {"trades":len(rs),"wins":sum(x>0 for x in rs),"losses":sum(x<0 for x in rs),
            "win_rate":sum(x>0 for x in rs)/len(rs) if rs else None,
            "net_r":sum(rs),"avg_r":statistics.fmean(rs) if rs else None,
            "profit_factor":gp/gl if gl>0 else None,
            "max_drawdown_r":mdd,"max_consecutive_losses":mx,
            "net_r_over_mdd":sum(rs)/mdd if mdd>0 else None}

def yearly(ts):
    d=defaultdict(list)
    for t in ts:
        d[str(datetime.fromtimestamp(t["entry_t"]/1000,UTC).year)].append(t)
    return {y:stats(v) for y,v in sorted(d.items())}

def robust_score(full,early,late,yrs):
    avgs=[q["avg_r"] for q in yrs.values() if q["avg_r"] is not None]
    disp=statistics.pstdev(avgs) if len(avgs)>1 else 0
    return (.30*(full["avg_r"] or 0)+
            .15*min(early["avg_r"] or 0,late["avg_r"] or 0)+
            .15*(full["profit_factor"] or 0)+
            .15*min(early["profit_factor"] or 0,late["profit_factor"] or 0)+
            .10*math.log1p(full["trades"])-
            .10*full["max_drawdown_r"]-
            .05*full["max_consecutive_losses"]-
            .10*abs((early["avg_r"] or 0)-(late["avg_r"] or 0))-
            .05*disp)

def survives(full,early,late):
    return (full["trades"]>=25 and early["trades"]>=8 and late["trades"]>=8 and
            early["net_r"]>0 and late["net_r"]>0 and
            (early["profit_factor"] or 0)>=1.05 and (late["profit_factor"] or 0)>=1.05 and
            full["max_drawdown_r"]<=10 and full["max_consecutive_losses"]<=7)

def bits(name):
    return tuple(int(x) for x in name.split("_",1)[1])

def main():
    files=sorted(ROOT.glob("f*_shard_*.json"))
    if not files:raise RuntimeError("no walk-forward shards")
    raw=defaultdict(lambda:defaultdict(list));configs={}
    for p in files:
        fold=p.name.split("_",1)[0]
        o=json.loads(p.read_text())
        configs.update(o.get("configs",{}))
        for name,ts in o["trades"].items():
            raw[fold][name].extend(recalc(t) for t in ts)

    fold_results={};wf_test=[];static_tests=defaultdict(list);selected_names=[]
    for fold,(tr0,tr1,te1) in FOLDS.items():
        a,b,c=ms(tr0),ms(tr1),ms(te1);mid=(a+b)//2
        results={}
        for name,ts in raw[fold].items():
            train=[t for t in ts if a<=t["entry_t"]<b]
            test=[t for t in ts if b<=t["entry_t"]<c]
            early=[t for t in train if t["entry_t"]<mid]
            late=[t for t in train if t["entry_t"]>=mid]
            full=stats(train);es=stats(early);ls=stats(late);yrs=yearly(train)
            results[name]={"overrides":configs[name],"train":full,"train_early":es,"train_late":ls,
                           "train_score":robust_score(full,es,ls,yrs),"survives":survives(full,es,ls),
                           "test":stats(test),"test_trades":test}
        for name,x in results.items():
            v=bits(name);neigh=[]
            for n2,y in results.items():
                if n2==name:continue
                v2=bits(n2)
                if sum(a!=b for a,b in zip(v,v2))==1:neigh.append(y)
            x["plateau"]={"neighbors":len(neigh),
                          "surviving_neighbors":sum(y["survives"] for y in neigh),
                          "survival_rate":sum(y["survives"] for y in neigh)/len(neigh) if neigh else None,
                          "neighbor_mean_score":statistics.fmean(y["train_score"] for y in neigh) if neigh else None}
            en=x["train_early"]["net_r"];ln=x["train_late"]["net_r"]
            x["half_balance"]=min(en,ln)/max(en,ln) if en>0 and ln>0 else 0

        eligible=[(n,x) for n,x in results.items() if x["survives"] and
                  (x["plateau"]["survival_rate"] or 0)>=.60 and x["half_balance"]>=.15]
        fallback=None
        if eligible:
            chosen=max(eligible,key=lambda z:z[1]["train_score"])
            method="robust_plateau"
        else:
            surv=[(n,x) for n,x in results.items() if x["survives"]]
            if surv:
                chosen=max(surv,key=lambda z:z[1]["train_score"]);method="survivor_score"
            else:
                chosen=max(results.items(),key=lambda z:z[1]["train_score"]);method="max_score_fallback"
        name,x=chosen;selected_names.append(name);wf_test+=x["test_trades"]
        for n,y in results.items():static_tests[n]+=y["test_trades"]
        fold_results[fold]={
          "train":[tr0,tr1],"test":[tr1,te1],"selection_method":method,
          "selected":{"name":name,"overrides":x["overrides"],"train":x["train"],
                      "train_score":x["train_score"],"plateau":x["plateau"],"half_balance":x["half_balance"],
                      "test":x["test"]},
          "top5_train":[{"name":n,"overrides":y["overrides"],"score":y["train_score"],
                         "survives":y["survives"],"plateau":y["plateau"],"test":y["test"]}
                        for n,y in sorted(results.items(),key=lambda z:z[1]["train_score"],reverse=True)[:5]]
        }

    static={n:stats(ts) for n,ts in static_tests.items()}
    static_rank=sorted(static.items(),key=lambda z:(z[1]["net_r_over_mdd"] or -999,z[1]["net_r"]),reverse=True)
    axis_freq={}
    for i,(p,v) in enumerate(AXES):
        axis_freq[p]={"preferred_value":v,"selected_folds":sum(bits(n)[i] for n in selected_names),
                      "total_folds":len(selected_names)}
    out={
      "generated_at":datetime.now(UTC).isoformat(),
      "method":"rolling 6y train -> next 3y test (last test 2y); exact 15m touch; actual-entry E filter; conservative same-bar ratchet; TP 15/15/70",
      "axes":[{"parameter":p,"preferred_value":v} for p,v in AXES],
      "folds":fold_results,
      "walk_forward_oos":stats(wf_test),
      "walk_forward_years":yearly(wf_test),
      "selected_configs":selected_names,
      "selected_axis_frequency":axis_freq,
      "static_oos_top10":[{"name":n,"overrides":configs[n],**x} for n,x in static_rank[:10]],
      "static_oos_all":{n:{"overrides":configs[n],**x} for n,x in static.items()},
      "note":"The walk-forward selected result is the primary OOS metric. Static OOS rankings inspect invariance but are not an untouched selection because all 32 configs are compared on aggregate test data."
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print("WF",json.dumps(out["walk_forward_oos"],ensure_ascii=False),flush=True)
    print("SELECTED",json.dumps(out["selected_configs"]),flush=True)
    print("AXIS_FREQ",json.dumps(axis_freq),flush=True)
    print("STATIC_TOP",json.dumps(out["static_oos_top10"][:5],ensure_ascii=False),flush=True)

if __name__=="__main__":main()
