import itertools,json,math,statistics,sys
from datetime import datetime,timezone
from pathlib import Path

UTC=timezone.utc
ROOT=Path("data/validation/stock_structural_exact_stage1_shards")
OUT=Path("data/validation/stock_track_b_e_recent5y_structural_exact_stage1_v2.json")
MID=int(datetime(2023,10,1,tzinfo=UTC).timestamp()*1000)

BASE={
  "range_max_atr":12.0,"range_er_max":0.80,"penetration_min":0.25,"penetration_max":2.50,
  "test_overlap_atr":1.50,"test_spread_max":1.25,"test_volume_max":1.05,
  "entry_buffer_atr":0.05,"stop_buffer_atr":0.25,
  "rr_long_min":1.10,"rr_long_max":2.00,
  "target_distance_atr":3.50,"return30_min":-0.05,"ema_gap_atr_max":2.0,"trigger_window":9
}

def stats(ts):
    ts=sorted(ts,key=lambda x:(x["exit_t"],x["symbol"]))
    rs=[float(x["r"]) for x in ts]
    gp=sum(x for x in rs if x>0);gl=-sum(x for x in rs if x<0)
    cr=peak=mdd=0.0;st=mx=0
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
    val=(.30*(full["avg_r"] or 0)
         +.15*min(early["avg_r"] or 0,late["avg_r"] or 0)
         +.15*(full["profit_factor"] or 0)
         +.15*min(early["profit_factor"] or 0,late["profit_factor"] or 0)
         +.10*math.log1p(full["trades"])
         -.10*full["max_drawdown_r"]
         -.05*full["max_consecutive_losses"]
         -.10*abs((early["avg_r"] or 0)-(late["avg_r"] or 0))
         -.05*disp)
    return val

def main():
    files=sorted(ROOT.glob("shard_*.json"))
    if not files:raise RuntimeError("no stage1 shard files")
    combined={};configs={};errors={};symbols=[]
    for p in files:
        o=json.loads(p.read_text())
        configs.update(o["configs"]);errors.update(o.get("errors",{}));symbols+=o.get("trade_symbols",[])
        for name,ts in o["trades"].items():combined.setdefault(name,[]).extend(ts)
    results={}
    for name,ts in combined.items():
        full=stats(ts);early=stats([x for x in ts if x["entry_t"]<MID]);late=stats([x for x in ts if x["entry_t"]>=MID]);yrs=yearly(ts)
        results[name]={"overrides":configs[name],"full":full,"early":early,"late":late,"years":yrs,
                       "survives":survives(full,early,late)}
        results[name]["score"]=score(full,early,late,yrs)
    baseline=results["baseline"]
    axes=[]
    params=sorted({k for name,x in results.items() for k in x["overrides"]})
    for p in params:
        candidates=[]
        for suffix in ("low","high"):
            name=f"{p}__{suffix}"
            if name in results:
                x=results[name]
                candidates.append((name,x))
        viable=[(n,x) for n,x in candidates if x["survives"] and x["score"]>baseline["score"]]
        if viable:
            n,x=max(viable,key=lambda z:z[1]["score"])
            axes.append({"parameter":p,"preferred_name":n,"preferred_value":x["overrides"][p],
                         "score_delta":x["score"]-baseline["score"],"result":x})
    axes.sort(key=lambda x:x["score_delta"],reverse=True)
    selected=axes[:5]

    # Stage 2: binary factorial baseline vs selected preferred values.
    stage2=[]
    for bits in itertools.product([0,1],repeat=len(selected)):
        ov={}
        labels=[]
        for bit,a in zip(bits,selected):
            if bit:
                ov[a["parameter"]]=a["preferred_value"];labels.append(a["preferred_name"])
        name="baseline" if not labels else "combo__"+"__".join(labels)
        stage2.append({"name":name,"overrides":ov})
    out={
      "generated_at":datetime.now(UTC).isoformat(),
      "files":[p.name for p in files],
      "symbols":sorted(set(symbols)),
      "baseline_params":BASE,
      "baseline_result":baseline,
      "results":results,
      "influential_axes":axes,
      "selected_axes":selected,
      "stage2_configs":stage2,
      "stage2_count":len(stage2),
      "errors":errors
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print("BASELINE",json.dumps(baseline,ensure_ascii=False),flush=True)
    print("SELECTED",json.dumps(selected,ensure_ascii=False),flush=True)
    print("STAGE2_COUNT",len(stage2),flush=True)

if __name__=="__main__":main()
