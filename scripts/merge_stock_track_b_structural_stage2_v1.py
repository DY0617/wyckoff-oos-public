import json,math,statistics
from datetime import datetime,timezone
from pathlib import Path

UTC=timezone.utc
ROOT=Path("data/validation/stock_structural_stage2_shards")
STAGE1=Path("data/validation/stock_track_b_e_recent5y_structural_stage1_v1.json")
OUT=Path("data/validation/stock_track_b_e_recent5y_structural_opt_v1.json")
MID=int(datetime(2023,10,1,tzinfo=UTC).timestamp()*1000)

def stats(ts):
    ts=sorted(ts,key=lambda x:(x["exit_t"],x["symbol"]))
    rs=[float(x["r"]) for x in ts]
    gp=sum(x for x in rs if x>0);gl=-sum(x for x in rs if x<0)
    cr=peak=mdd=0.;st=mx=0
    for x in rs:
        cr+=x;peak=max(peak,cr);mdd=max(mdd,peak-cr)
        if x<0:st+=1;mx=max(mx,st)
        else:st=0
    return {"trades":len(ts),"wins":sum(x>0 for x in rs),"losses":sum(x<0 for x in rs),
            "win_rate":sum(x>0 for x in rs)/len(rs) if rs else None,
            "net_r":sum(rs),"avg_r":statistics.fmean(rs) if rs else None,
            "profit_factor":gp/gl if gl>0 else None,
            "max_drawdown_r":mdd,"max_consecutive_losses":mx}

def yearly(ts):
    out={}
    for y in range(2021,2027):
        xs=[x for x in ts if datetime.fromtimestamp(x["entry_t"]/1000,UTC).year==y]
        if xs:out[str(y)]=stats(xs)
    return out

def survives(full,early,late):
    return (full["trades"]>=40 and early["net_r"]>0 and late["net_r"]>0 and
            (early["profit_factor"] or 0)>=1.20 and (late["profit_factor"] or 0)>=1.20 and
            full["max_drawdown_r"]<=10 and full["max_consecutive_losses"]<=7)

def score(full,early,late,yrs):
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

def vector(ov,selected):
    return tuple(1 if a["parameter"] in ov else 0 for a in selected)

def main():
    st1=json.loads(STAGE1.read_text())
    selected=st1["selected_axes"]
    files=sorted(ROOT.glob("shard_*.json"))
    if not files:raise RuntimeError("no stage2 shard files")
    combined={};configs={};errors={}
    for p in files:
        o=json.loads(p.read_text())
        configs.update(o["configs"]);errors.update(o.get("errors",{}))
        for name,ts in o["trades"].items():combined.setdefault(name,[]).extend(ts)

    results={}
    for name,ts in combined.items():
        full=stats(ts);early=stats([x for x in ts if x["entry_t"]<MID]);late=stats([x for x in ts if x["entry_t"]>=MID]);yrs=yearly(ts)
        results[name]={"overrides":configs[name],"full":full,"early":early,"late":late,"years":yrs,
                       "survives":survives(full,early,late)}
        results[name]["score"]=score(full,early,late,yrs)

    names=list(results)
    for name,x in results.items():
        v=vector(x["overrides"],selected)
        neigh=[]
        for n2,y in results.items():
            if n2==name:continue
            v2=vector(y["overrides"],selected)
            if sum(a!=b for a,b in zip(v,v2))==1:neigh.append(y)
        x["plateau"]={
          "neighbors":len(neigh),
          "surviving_neighbors":sum(y["survives"] for y in neigh),
          "survival_rate":sum(y["survives"] for y in neigh)/len(neigh) if neigh else None,
          "neighbor_mean_score":statistics.fmean(y["score"] for y in neigh) if neigh else None
        }
        en=x["early"]["net_r"];ln=x["late"]["net_r"]
        x["half_balance"]=min(en,ln)/max(en,ln) if en>0 and ln>0 else 0

    baseline=results["baseline"]
    survivors=[(n,x) for n,x in results.items() if x["survives"] and x["score"]>baseline["score"]]
    survivors.sort(key=lambda z:z[1]["score"],reverse=True)
    plateau=[z for z in survivors if (z[1]["plateau"]["survival_rate"] or 0)>=.60 and z[1]["half_balance"]>=.15]
    robust=max(plateau,key=lambda z:z[1]["score"]) if plateau else (survivors[0] if survivors else ("baseline",baseline))
    max_net=max(results.items(),key=lambda z:z[1]["full"]["net_r"])
    max_score=max(results.items(),key=lambda z:z[1]["score"])

    out={
      "generated_at":datetime.now(UTC).isoformat(),
      "period":{"start":"2021-04-01","mid":"2023-10-01","end_exclusive":"2026-04-01"},
      "selected_axes":selected,
      "stage1_baseline":st1["baseline_result"],
      "stage2_baseline":baseline,
      "baseline_parity":{
        "trades_diff":baseline["full"]["trades"]-st1["baseline_result"]["full"]["trades"],
        "net_r_diff":baseline["full"]["net_r"]-st1["baseline_result"]["full"]["net_r"]
      },
      "result_count":len(results),
      "survivor_improvements":len(survivors),
      "max_score":{"name":max_score[0],"result":max_score[1]},
      "max_net_r":{"name":max_net[0],"result":max_net[1]},
      "robust_pick":{"name":robust[0],"result":robust[1]},
      "top10":[{"name":n,**x} for n,x in sorted(results.items(),key=lambda z:z[1]["score"],reverse=True)[:10]],
      "results":results,
      "errors":errors,
      "note":"Research optimization only. Any structural change requires independent validation before production."
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print("PARITY",json.dumps(out["baseline_parity"]),flush=True)
    print("ROBUST",json.dumps(out["robust_pick"],ensure_ascii=False),flush=True)
    print("MAX_NET",json.dumps(out["max_net_r"],ensure_ascii=False),flush=True)

if __name__=="__main__":main()
