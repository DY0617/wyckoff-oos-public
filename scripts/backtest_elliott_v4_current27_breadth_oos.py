import json, statistics
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import datetime, time as dtime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd

import backtest_elliott_wave3_v0_crypto as core
import backtest_elliott_wave3_v3_bbreak as v3

ROOT=Path(__file__).resolve().parents[1]
DATA_DIR=ROOT/"data/tmp_us30x2_25y"
OUT=ROOT/"data/validation/elliott_wave3_v4_current27_breadth_oos_25y.json"
UTC=timezone.utc
NY=ZoneInfo("America/New_York")

SYMS=("AAPL","MSFT","NVDA","AMZN","META","GOOGL","TSLA","AVGO","AMD","NFLX","ORCL",
      "JPM","BAC","GS","V","MA","XOM","CVX","JNJ","UNH","LLY","MRK","WMT","COST","HD","CAT","KO")

EVAL_START=datetime(2000,1,1,tzinfo=UTC)
EVAL_END=datetime(2026,1,1,tzinfo=UTC)
ENTRY_VALID_SIGNAL_BARS=12
MAX_HOLD_SIGNAL_BARS=48
TP1_FRAC=0.50
SPLIT_FACTORS=(1.5,2,3,4,5,7,10,15,20)

def load_all():
    files=sorted(DATA_DIR.glob("us30x2_15m_*.parquet"))
    if len(files)!=6:raise RuntimeError(f"expected 6 chunks got {len(files)}")
    frames=[pd.read_parquet(p) for p in files]
    df=pd.concat(frames,ignore_index=True).drop_duplicates(["ticker","t"]).sort_values(["ticker","t"])
    out={}
    for sym in SYMS:
        g=df[df.ticker==sym]
        out[sym]=[
            {"t":int(r.t),"ct":int(r.t)+15*60_000,"o":float(r.o),"h":float(r.h),
             "l":float(r.l),"c":float(r.c),"v":float(r.v or 0)}
            for r in g.itertuples(index=False)
        ]
    return out,[p.name for p in files]

def day_key(z):
    return datetime.fromtimestamp(z["t"]/1000,UTC).astimezone(NY).date()

def detect_splits(bars):
    by=defaultdict(list)
    for z in bars:by[day_key(z)].append(z)
    ds=sorted(by);ev=[]
    for i in range(1,len(ds)):
        if (ds[i]-ds[i-1]).days>14:continue
        prev=by[ds[i-1]][-1]["c"];op=by[ds[i]][0]["o"]
        if prev<=0 or op<=0:continue
        ratio=prev/op;mag=ratio if ratio>=1 else 1/ratio
        if mag<1.35:continue
        f=min(SPLIT_FACTORS,key=lambda q:abs(mag/q-1))
        if abs(mag/f-1)<=.06:
            ev.append({"date":str(ds[i]),"factor":f,"price_mult_before":1/f if ratio>1 else f})
    return ev

def apply_splits(bars,ev):
    if not ev:return [dict(x) for x in bars]
    parsed=[(datetime.fromisoformat(e["date"]).date(),e["price_mult_before"]) for e in ev]
    out=[]
    for z in bars:
        d=day_key(z);pm=1.
        for sd,p in parsed:
            if d<sd:pm*=p
        q=dict(z)
        for k in ("o","h","l","c"):q[k]*=pm
        out.append(q)
    return out

def aggregate_daily(b15):
    by=defaultdict(list)
    for b in b15:by[day_key(b)].append(b)
    out=[]
    for d in sorted(by):
        xs=sorted(by[d],key=lambda z:z["t"])
        if len(xs)<24:continue
        out.append({"date":d,"t":xs[0]["t"],"ct":xs[-1]["ct"],"c":xs[-1]["c"]})
    return out

def aggregate_1h(b15):
    by=defaultdict(list)
    for b in b15:
        dt=datetime.fromtimestamp(b["t"]/1000,UTC).astimezone(NY)
        if dtime(9,30)<=dt.time()<dtime(16,0):by[dt.date()].append(b)
    out=[]
    for d in sorted(by):
        xs=sorted(by[d],key=lambda z:z["t"])
        for k in range(0,24,4):
            p=xs[k:k+4]
            if len(p)!=4 or p[-1]["ct"]-p[0]["t"]!=60*60_000:continue
            out.append({"t":p[0]["t"],"ct":p[-1]["ct"],"o":p[0]["o"],"h":max(x["h"] for x in p),
                        "l":min(x["l"] for x in p),"c":p[-1]["c"],"v":sum(x["v"] for x in p)})
    return out

def build_breadth(adj):
    states={}
    dates=set()
    for sym,bars in adj.items():
        d=aggregate_daily(bars)
        if not d:continue
        cs=pd.Series([x["c"] for x in d],dtype=float)
        ma=cs.rolling(200,min_periods=120).mean()
        sm={}
        for i,x in enumerate(d):
            dates.add(x["date"])
            if pd.notna(ma.iloc[i]):sm[x["date"]]=1 if x["c"]>float(ma.iloc[i]) else 0
        states[sym]=sm
    times=[];vals=[];ns=[]
    for d in sorted(dates):
        x=[states.get(s,{}).get(d) for s in SYMS]
        x=[v for v in x if v is not None]
        if not x:continue
        # 16:00 ET approximation via last completed daily state; only prior day is queried at signal time.
        t=int(pd.Timestamp(d,tz="America/New_York").tz_convert("UTC").timestamp()*1000)+21*60*60*1000
        times.append(t);vals.append(sum(x)/len(x));ns.append(len(x))
    return times,vals,ns

def breadth_at(t,times,vals,ns):
    i=bisect_right(times,t-1)-1
    return (vals[i],ns[i]) if i>=0 else (None,0)

def signal_expiry(d,ki,n):return d[min(ki+n,len(d)-1)]["ct"]
def hold_expiry(d,fill_t,n):
    closes=[x["ct"] for x in d];i=bisect_left(closes,fill_t)
    return d[min(i+n,len(d)-1)]["ct"]

def simulate(sym,b15,btimes,bvals,bns,mode):
    d=core.enrich_atr(aggregate_1h(b15));ps=core.zigzag(d);t15=[x["t"] for x in b15]
    lo=int(EVAL_START.timestamp()*1000);hi=int(EVAL_END.timestamp()*1000)
    by_known=defaultdict(list)
    for k in range(8,len(ps)):
        sig=v3.make_v3_signal(d,ps[k-8:k+1])
        if sig and sig["side"]=="LONG":
            b,n=breadth_at(d[sig["known_i"]]["ct"],btimes,bvals,bns)
            if mode=="MID_BREADTH_60_75" and not (b is not None and n>=10 and 0.60<=b<0.75):
                continue
            sig=dict(sig);sig["breadth200"]=b;sig["breadth_n"]=n
            by_known[sig["known_i"]].append(sig)
    trades=[];st=defaultdict(int);busy=-1
    for ki in sorted(by_known):
        act=d[ki]["ct"]
        if not(lo<=act<hi):continue
        if act<busy:st["signal_while_busy"]+=1;continue
        sig=by_known[ki][-1];st["patterns"]+=1
        entry,sl,tp1,tp2,risk=sig["entry"],sig["sl"],sig["tp1"],sig["tp2"],sig["risk"]
        start=bisect_left(t15,act);valid=signal_expiry(d,ki,ENTRY_VALID_SIGNAL_BARS)
        fi=None;fill=None;cancel=False
        for j in range(start,len(b15)):
            b=b15[j]
            if b["t"]>=hi or b["t"]>=valid:break
            if b["o"]>=entry:fi,fill=j,b["o"];break
            if b["l"]<=sl:cancel=True;break
            if b["h"]>=entry:fi,fill=j,entry;break
        if fi is None:
            st["cancelled_before_entry" if cancel else "entry_expired"]+=1;busy=valid;continue
        st["filled"]+=1;pnl=-core.cost(fill);rem=1.;stop=sl;h1=h2=False
        exit_t=b15[fi]["ct"];reason="TIME";last=fi;hold=hold_expiry(d,b15[fi]["t"],MAX_HOLD_SIGNAL_BARS)
        for j in range(fi,len(b15)):
            b=b15[j]
            if b["t"]>=hi or b["t"]>=hold:break
            last=j
            if b["o"]<=stop:
                pnl+=rem*(b["o"]-fill)-core.cost(b["o"],rem);rem=0;exit_t=b["ct"];reason="GAP_STOP";break
            if b["l"]<=stop:
                pnl+=rem*(stop-fill)-core.cost(stop,rem);rem=0;exit_t=b["ct"];reason="STOP";break
            if not h1:
                px=b["o"] if b["o"]>=tp1 else (tp1 if b["h"]>=tp1 else None)
                if px is not None:
                    f=min(TP1_FRAC,rem);pnl+=f*(px-fill)-core.cost(px,f);rem-=f;h1=True;stop=max(stop,fill)
                    if rem>0 and b["l"]<=stop:
                        pnl+=rem*(stop-fill)-core.cost(stop,rem);rem=0;exit_t=b["ct"];reason="BE_AFTER_TP1";break
            if rem>0 and h1 and (b["o"]>=tp2 or b["h"]>=tp2):
                px=b["o"] if b["o"]>=tp2 else tp2;pnl+=rem*(px-fill)-core.cost(px,rem);rem=0;h2=True;exit_t=b["ct"];reason="TP2";break
        if rem>0:
            b=b15[last];px=b["c"];pnl+=rem*(px-fill)-core.cost(px,rem);exit_t=b["ct"];reason="TIME"
        trades.append({"symbol":sym,"mode":mode,"entry_t":b15[fi]["t"],"exit_t":exit_t,
                       "r":pnl/risk,"tp1_hit":h1,"tp2_hit":h2,"breadth200":sig["breadth200"],
                       "breadth_n":sig["breadth_n"]})
        busy=exit_t
    return trades,dict(st)

def metrics(ts):
    o=sorted(ts,key=lambda z:(z["exit_t"],z["symbol"]));rs=[x["r"] for x in o]
    pos=[r for r in rs if r>0];neg=[r for r in rs if r<0]
    eq=peak=0.;dd=0.;cur=mx=0
    for r in rs:
        eq+=r;peak=max(peak,eq);dd=min(dd,eq-peak)
        if r<0:cur+=1;mx=max(mx,cur)
        else:cur=0
    return {"trades":len(o),"total_r":sum(rs),"avg_r":statistics.fmean(rs) if rs else None,
            "profit_factor":sum(pos)/abs(sum(neg)) if neg else None,"win_rate":len(pos)/len(o) if o else None,
            "max_drawdown_r":dd,"max_losing_streak":mx}

def main():
    raw,files=load_all();adj={};splits={}
    for s,b in raw.items():
        ev=detect_splits(b);splits[s]=ev;adj[s]=apply_splits(b,ev)
    bt,bv,bn=build_breadth(adj)

    configs={}
    for mode in ("BASELINE","MID_BREADTH_60_75"):
        alltr=[];cells={};errors={}
        for s in SYMS:
            try:
                if len(adj[s])<500:raise RuntimeError(f"insufficient bars {len(adj[s])}")
                ts,st=simulate(s,adj[s],bt,bv,bn,mode);alltr+=ts
                cells[s]={"metrics":metrics(ts),"stats":st,"bars15":len(adj[s])}
            except Exception as e:errors[s]=repr(e)
        configs[mode]={"metrics":metrics(alltr),"symbols":cells,"errors":errors,"trades":alltr}
        print("CONFIG",mode,json.dumps(configs[mode]["metrics"]),flush=True)

    out={"strategy":"Elliott v4 current27 25Y breadth-filter validation",
         "purpose":"Cross-universe validation of the post-hoc DJIA2000 breadth 60-75% candidate. No tuning on current27.",
         "period":{"start":EVAL_START.isoformat(),"end_exclusive":EVAL_END.isoformat()},
         "universe":list(SYMS),"chunk_files":files,
         "breadth_rule":"fraction of available current27 names above SMA200, prior completed RTH day; candidate requires >=10 names and 60%<=breadth<75%",
         "configs":configs,
         "limitations":["Current27 is survivorship-biased and therefore secondary validation only.",
                        "The breadth filter was discovered post-hoc on the frozen DJIA2000 universe and is evaluated here without modification."]}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,indent=2),encoding="utf-8")
    print("FINAL",json.dumps({k:v["metrics"] for k,v in configs.items()},indent=2))

if __name__=="__main__":main()
