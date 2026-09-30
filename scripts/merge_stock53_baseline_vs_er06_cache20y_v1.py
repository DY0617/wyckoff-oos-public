import json,statistics
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path("data/validation/stock53_baseline_er06_20y_cache_shards")
OUT=Path("data/validation/stock53_track_b_baseline_vs_er06_20y_v1.json")
UTC=timezone.utc
FEE_BPS=4.0; SLIPPAGE_BPS=2.0; RISK=400.0
TP1_FRAC=.15; TP2_FRAC=.15

def ms(s): return int(datetime.fromisoformat(s).replace(tzinfo=UTC).timestamp()*1000)
CUT=ms("2021-04-01")

def recalc(t):
    sign=1 if t["direction"]=="LONG" else -1
    entry=float(t["entry"]); size=float(t["size"])
    cost=(FEE_BPS+SLIPPAGE_BPS)/10000.0
    realized=-size*entry*cost; remain=1.0
    for e in t.get("events",[]):
        typ=e.get("type")
        if typ=="TP1":
            frac=min(TP1_FRAC,remain); px=float(e["price"])
            realized += frac*sign*(px-entry)*size - frac*size*px*cost; remain-=frac
        elif typ=="TP2":
            frac=min(TP2_FRAC,remain); px=float(e["price"])
            realized += frac*sign*(px-entry)*size - frac*size*px*cost; remain-=frac
        elif typ in ("STOP","BE","OPEN_MARK","FIB1618_FULL","FIB1618_PARTIAL"):
            if remain<=1e-12: break
            px=float(e["price"])
            realized += remain*sign*(px-entry)*size - remain*size*px*cost
            remain=0.0; break
    if remain>1e-8: raise RuntimeError(f"open remainder {remain} {t.get('symbol')}")
    q=dict(t); q["pnl"]=realized; q["r"]=realized/RISK
    return q

def stats(ts):
    ts=sorted(ts,key=lambda x:(x["exit_t"],x["symbol"]))
    rs=[float(x["r"]) for x in ts]
    gp=sum(x for x in rs if x>0); gl=-sum(x for x in rs if x<0)
    cr=peak=mdd=0.0; st=mx=0
    for r in rs:
        cr+=r; peak=max(peak,cr); mdd=max(mdd,peak-cr)
        if r<0: st+=1; mx=max(mx,st)
        else: st=0
    return {"trades":len(rs),"wins":sum(x>0 for x in rs),"losses":sum(x<0 for x in rs),
            "win_rate":sum(x>0 for x in rs)/len(rs) if rs else None,
            "net_r":sum(rs),"avg_r":statistics.fmean(rs) if rs else None,
            "profit_factor":gp/gl if gl>0 else None,"max_drawdown_r":mdd,
            "max_consecutive_losses":mx,
            "net_r_over_mdd":sum(rs)/mdd if mdd>0 else None}

def yearly(ts):
    d=defaultdict(list)
    for t in ts:d[str(datetime.fromtimestamp(t["entry_t"]/1000,UTC).year)].append(t)
    return {y:stats(v) for y,v in sorted(d.items())}

def loso(ts):
    syms=sorted(set(t["symbol"] for t in ts)); rows=[]
    for s in syms:
        q=stats([t for t in ts if t["symbol"]!=s]); q["removed_symbol"]=s; rows.append(q)
    return {
      "cases":len(rows),
      "min_net_r":min((x["net_r"] for x in rows),default=None),
      "min_pf":min((x["profit_factor"] for x in rows if x["profit_factor"] is not None),default=None),
      "max_mdd_r":max((x["max_drawdown_r"] for x in rows),default=None),
      "max_loss_streak":max((x["max_consecutive_losses"] for x in rows),default=None),
      "worst_net_case":min(rows,key=lambda x:x["net_r"]) if rows else None
    }

def main():
    files=sorted(ROOT.glob("shard_*.json"))
    if len(files)!=5: raise RuntimeError(f"expected 5 shards, got {len(files)}")
    combined=defaultdict(list); errors={}; configs=None
    for p in files:
        o=json.loads(p.read_text())
        configs=configs or o.get("configs")
        errors[p.name]=o.get("errors",{})
        for name,ts in o["trades"].items(): combined[name].extend(recalc(t) for t in ts)

    out={"generated_at":datetime.now(UTC).isoformat(),
         "period":{"start":"2006-04-01","end_exclusive":"2026-04-01","oos_cut":"2021-04-01"},
         "configs":configs,"ratio":[.15,.15,.70],
         "execution":"exact 15m touch; actual-entry E filter; conservative same-bar TP1=>BE/TP2=>TP1; confirmed RTH 4H pivot runner",
         "results":{},"errors":errors}
    for name,ts in combined.items():
        ts=sorted(ts,key=lambda x:(x["entry_t"],x["symbol"]))
        old=[t for t in ts if t["entry_t"]<CUT]; recent=[t for t in ts if t["entry_t"]>=CUT]
        out["results"][name]={
          "full20y":stats(ts),"oos15y":stats(old),"recent5y":stats(recent),
          "years":yearly(ts),"oos_leave_one_symbol_out":loso(old)
        }
    a=out["results"]["baseline"]; b=out["results"]["er06"]
    out["delta_er06_minus_baseline"]={}
    for scope in ("full20y","oos15y","recent5y"):
        out["delta_er06_minus_baseline"][scope]={}
        for k in ("trades","win_rate","net_r","avg_r","profit_factor","max_drawdown_r","max_consecutive_losses","net_r_over_mdd"):
            av=a[scope].get(k); bv=b[scope].get(k)
            out["delta_er06_minus_baseline"][scope][k]=(bv-av) if isinstance(av,(int,float)) and isinstance(bv,(int,float)) else None

    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:{s:v[s] for s in ("full20y","oos15y","recent5y")} for k,v in out["results"].items()},ensure_ascii=False,indent=2))
    print("DELTA",json.dumps(out["delta_er06_minus_baseline"],ensure_ascii=False,indent=2))

if __name__=="__main__":main()
