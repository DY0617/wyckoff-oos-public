import json,math,statistics
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
UTC=timezone.utc
ROOT=Path("data/validation/stock53_wf_single")
OUT=Path("data/validation/stock53_track_b_single_axis_invariance_v1.json")
FOLDS={
 "f01":("2006-04-01","2012-04-01","2015-04-01"),
 "f02":("2009-04-01","2015-04-01","2018-04-01"),
 "f03":("2012-04-01","2018-04-01","2021-04-01"),
 "f04":("2015-04-01","2021-04-01","2024-04-01"),
 "f05":("2018-04-01","2024-04-01","2026-04-01"),
}
FEE_BPS=4.;SLIPPAGE_BPS=2.;RISK=400.

def ms(s):return int(datetime.fromisoformat(s).replace(tzinfo=UTC).timestamp()*1000)
def recalc(t,f1=.15,f2=.15):
    sign=1 if t["direction"]=="LONG" else -1
    entry=float(t["entry"]);size=float(t["size"]);cost=(FEE_BPS+SLIPPAGE_BPS)/10000.
    realized=-size*entry*cost;remain=1.
    for e in t.get("events",[]):
        typ=e.get("type")
        if typ=="TP1":
            frac=min(f1,remain);px=float(e["price"]);realized+=frac*sign*(px-entry)*size-frac*size*px*cost;remain-=frac
        elif typ=="TP2":
            frac=min(f2,remain);px=float(e["price"]);realized+=frac*sign*(px-entry)*size-frac*size*px*cost;remain-=frac
        elif typ in ("STOP","BE","OPEN_MARK","FIB1618_FULL","FIB1618_PARTIAL"):
            if remain<=1e-12:break
            px=float(e["price"]);realized+=remain*sign*(px-entry)*size-remain*size*px*cost;remain=0.;break
    if remain>1e-8:raise RuntimeError(f"open remainder {remain}")
    q=dict(t);q["r"]=realized/RISK;return q

def stats(ts):
    ts=sorted(ts,key=lambda x:(x["exit_t"],x["symbol"]));rs=[float(x["r"]) for x in ts]
    gp=sum(x for x in rs if x>0);gl=-sum(x for x in rs if x<0);cr=peak=mdd=0.;st=mx=0
    for r in rs:
        cr+=r;peak=max(peak,cr);mdd=max(mdd,peak-cr)
        if r<0:st+=1;mx=max(mx,st)
        else:st=0
    return {"trades":len(rs),"wins":sum(x>0 for x in rs),"losses":sum(x<0 for x in rs),
            "win_rate":sum(x>0 for x in rs)/len(rs) if rs else None,"net_r":sum(rs),
            "avg_r":statistics.fmean(rs) if rs else None,"profit_factor":gp/gl if gl>0 else None,
            "max_drawdown_r":mdd,"max_consecutive_losses":mx,
            "net_r_over_mdd":sum(rs)/mdd if mdd>0 else None}

def yearly(ts):
    d=defaultdict(list)
    for t in ts:d[str(datetime.fromtimestamp(t["entry_t"]/1000,UTC).year)].append(t)
    return {y:stats(v) for y,v in d.items()}

def score(full,early,late,yrs):
    av=[q["avg_r"] for q in yrs.values() if q["avg_r"] is not None];disp=statistics.pstdev(av) if len(av)>1 else 0
    return (.30*(full["avg_r"] or 0)+.15*min(early["avg_r"] or 0,late["avg_r"] or 0)+
            .15*(full["profit_factor"] or 0)+.15*min(early["profit_factor"] or 0,late["profit_factor"] or 0)+
            .10*math.log1p(full["trades"])-.10*full["max_drawdown_r"]-.05*full["max_consecutive_losses"]-
            .10*abs((early["avg_r"] or 0)-(late["avg_r"] or 0))-.05*disp)

def main():
    foldout={};static=defaultdict(list);wf=[];train_winners=[]
    configs={}
    for fold,(a0,b0,c0) in FOLDS.items():
        p=ROOT/f"{fold}.json";o=json.loads(p.read_text());configs.update(o["configs"])
        a,b,c=ms(a0),ms(b0),ms(c0);mid=(a+b)//2
        rows={}
        for name,raw in o["trades"].items():
            ts=[recalc(t) for t in raw]
            tr=[t for t in ts if a<=t["entry_t"]<b];te=[t for t in ts if b<=t["entry_t"]<c]
            e=[t for t in tr if t["entry_t"]<mid];l=[t for t in tr if t["entry_t"]>=mid]
            fs,es,ls=stats(tr),stats(e),stats(l)
            rows[name]={"overrides":configs[name],"train":fs,"train_score":score(fs,es,ls,yearly(tr)),
                        "test":stats(te),"test_trades":te}
            static[name]+=te
        winner=max(rows.items(),key=lambda z:z[1]["train_score"])
        train_winners.append(winner[0]);wf+=winner[1]["test_trades"]
        foldout[fold]={"train":[a0,b0],"test":[b0,c0],"winner":{"name":winner[0],**{k:v for k,v in winner[1].items() if k!="test_trades"}},
                       "all":{n:{k:v for k,v in x.items() if k!="test_trades"} for n,x in rows.items()}}
    static_stats={n:stats(ts) for n,ts in static.items()}
    out={"generated_at":datetime.now(UTC).isoformat(),
         "method":"6y train -> next 3y OOS (last 2y), baseline + 5 single-axis preferences; exact touch; actual-entry E; conservative same-bar ratchet; TP15/15/70",
         "folds":foldout,"train_winners":train_winners,"walk_forward_selected_oos":stats(wf),
         "static_oos":{n:{"overrides":configs[n],**x} for n,x in static_stats.items()},
         "static_rank_by_net_r":[{"name":n,"overrides":configs[n],**x} for n,x in sorted(static_stats.items(),key=lambda z:z[1]["net_r"],reverse=True)]}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,indent=2),encoding="utf-8")
    print(json.dumps({"winners":train_winners,"wf":out["walk_forward_selected_oos"],"static":out["static_rank_by_net_r"]},indent=2))
if __name__=="__main__":main()
