import bisect,json,math,time
from collections import defaultdict
from datetime import datetime,timezone,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import duckdb

M1=Path("data/validation/m1_momentum_pullback_20y.json")
OUT=Path("data/validation/m1_risk_controls_20y.json")
UTC=timezone.utc; NY=ZoneInfo("America/New_York")
HF_BASE="https://huggingface.co/datasets/mito0o852/OHLCV-1m/resolve/main/data"
START=datetime(2006,4,1,tzinfo=UTC); END=datetime(2026,4,1,tzinfo=UTC)
WARMUP=START-timedelta(days=390)

SYMS=(
"AAPL","AMZN","AVGO","CRCL","DELL","MSFT","MU","SNDK","SNXX","SOXL","SPCX",
"AMD","BABA","INTC","JPM","KORU","MSTR","NFLX","SKHY","SMCI","SOXS","V",
"COST","GOOGL","LLY","META","NBIS","NVDA","QQQ","TSLA","UBER","WMT",
"AMAT","CAT","DRAM","EWY","HD","MRVL","MUU","ORCL","SPY","TSM",
"AAOI","AXTI","BE","COIN","CRM","CSCO","DIS","HOOD","IBM","LITE","TQQQ"
)
SOURCE=tuple(sorted(set(SYMS+("FB","GOOG"))))
NOT_BEFORE={"DELL":datetime(2018,12,28,tzinfo=UTC),"SNDK":datetime(2025,2,24,tzinfo=UTC)}

def month_iter(start,end):
    y,m=start.year,start.month
    while (y,m)<=(end.year,end.month):
        yield y,m
        m+=1
        if m==13:y,m=y+1,1

def canonical(ticker,d):
    if ticker=="FB":return "META" if d<datetime(2022,6,9).date() else None
    if ticker=="META":return "META" if d>=datetime(2022,6,9).date() else None
    if ticker=="GOOG":return "GOOGL" if d<datetime(2014,4,3).date() else None
    if ticker=="GOOGL":return "GOOGL" if d>=datetime(2014,4,3).date() else None
    return ticker if ticker in SYMS else None

def ema(vals,n):
    k=2/(n+1);out=[];e=None
    for x in vals:
        e=x if e is None else e+k*(x-e);out.append(e)
    return out

def detect_splits(bars):
    common=(2,3,4,5,7,10,15,20);ev=[]
    for i in range(1,len(bars)):
        prev=bars[i-1]["c"];op=bars[i]["o"]
        d0=datetime.fromtimestamp(bars[i-1]["t"]/1000,UTC).date()
        d1=datetime.fromtimestamp(bars[i]["t"]/1000,UTC).date()
        if prev<=0 or op<=0 or (d1-d0).days>14:continue
        ratio=prev/op;mag=ratio if ratio>=1 else 1/ratio
        if mag<1.7:continue
        f=min(common,key=lambda q:abs(mag/q))
        if abs(mag/f)<=.08:
            pm,vm=((1/f,f) if ratio>1 else (f,1/f));ev.append((bars[i]["t"],pm,vm))
    return ev

def apply_splits(bars,ev):
    out=[]
    for z in bars:
        pm=vm=1.0
        for ts,p,v in ev:
            if z["t"]<ts:pm*=p;vm*=v
        q=z.copy()
        for k in ("o","h","l","c"):q[k]*=pm
        q["v"]*=vm;out.append(q)
    return out

def collect_daily():
    con=duckdb.connect();con.execute("INSTALL httpfs; LOAD httpfs;")
    by={s:[] for s in SYMS};missing=[]
    ph=",".join(["?"]*len(SOURCE))
    for y,m in month_iter(WARMUP,END-timedelta(days=1)):
        url=f"{HF_BASE}/ohlcv_{y:04d}-{m:02d}.parquet"
        q=f"""
        WITH src AS (
          SELECT ticker,timezone('America/New_York',timestamp) et,open,high,low,"close",volume
          FROM read_parquet('{url}') WHERE ticker IN ({ph})
        ),rth AS (
          SELECT * FROM src WHERE cast(et as time)>=time '09:30:00' and cast(et as time)<time '16:00:00'
        )
        SELECT ticker,cast(et as date) d,min(et) first_et,max(et) last_et,
               arg_min(open,et) o,max(high) h,min(low) l,arg_max("close",et) c,sum(volume) v
        FROM rth GROUP BY ticker,cast(et as date) ORDER BY ticker,d
        """
        rows=None
        for a in range(5):
            try:
                t0=time.time();rows=con.execute(q,list(SOURCE)).fetchall()
                print("MONTH",f"{y:04d}-{m:02d}",len(rows),round(time.time()-t0,2),flush=True);break
            except Exception as e:
                print("RETRY",y,m,a+1,repr(e),flush=True);time.sleep(3*(a+1))
        if rows is None:
            missing.append(f"{y:04d}-{m:02d}");continue
        for ticker,d,first_et,last_et,o,h,l,c,v in rows:
            s=canonical(str(ticker),d)
            if not s:continue
            f=first_et.replace(tzinfo=NY) if first_et.tzinfo is None else first_et.astimezone(NY)
            z=last_et.replace(tzinfo=NY) if last_et.tzinfo is None else last_et.astimezone(NY)
            utc=f.astimezone(UTC)
            nb=NOT_BEFORE.get(s)
            if nb and utc<nb:continue
            if utc<WARMUP or utc>=END:continue
            tms=int(utc.timestamp()*1000);ct=int(z.astimezone(UTC).timestamp()*1000)+60_000-1
            by[s].append({"t":tms,"o":float(o),"h":float(h),"l":float(l),"c":float(c),
                          "v":float(v or 0),"ct":ct,"date":str(d)})
    con.close()
    if missing:raise RuntimeError("missing months="+",".join(missing))
    out={}
    for s,b in by.items():
        if not b:continue
        b=apply_splits(b,detect_splits(b))
        e50=ema([x["c"] for x in b],50)
        for i,x in enumerate(b):x["ema50"]=e50[i]
        out[s]=b
    return out

def breadth_map(dailies):
    # signal-date breadth using the just-completed RTH session; entry is next day or later.
    dates=sorted(set(x["date"] for D in dailies.values() for x in D))
    idx={s:{x["date"]:i for i,x in enumerate(D)} for s,D in dailies.items()}
    out={}
    for ds in dates:
        eligible=above=0
        for s,D in dailies.items():
            i=idx[s].get(ds)
            if i is None or i<50:continue
            eligible+=1;above+=int(D[i]["c"]>D[i]["ema50"])
        out[ds]=(above/eligible if eligible else None,above,eligible)
    return out

def et_date(ms):
    return datetime.fromtimestamp(ms/1000,UTC).astimezone(NY).date().isoformat()

def stats(ts):
    ts=sorted(ts,key=lambda x:(x["exit_t"],x["symbol"]))
    n=len(ts);w=sum(x["r"]>0 for x in ts);l=sum(x["r"]<0 for x in ts)
    net=sum(x["r"] for x in ts);gp=sum(x["r"] for x in ts if x["r"]>0);gl=sum(x["r"] for x in ts if x["r"]<0)
    cr=pr=mdd=0.0;st=best=0
    for x in ts:
        cr+=x["r"];pr=max(pr,cr);mdd=max(mdd,pr-cr)
        if x["r"]<0:st+=1;best=max(best,st)
        else:st=0
    return {"closed":n,"wins":w,"losses":l,"win_rate":w/n if n else None,
            "net_r":net,"avg_r":net/n if n else None,"profit_factor":gp/abs(gl) if gl<0 else None,
            "max_drawdown_r":mdd,"max_consecutive_losses":best}

def by_year(ts):
    d=defaultdict(list)
    for t in ts:d[str(datetime.fromtimestamp(t["entry_t"]/1000,UTC).year)].append(t)
    return {y:stats(v) for y,v in sorted(d.items())}

def pack(ts):
    yy=by_year(ts)
    return {**stats(ts),"positive_years":sum(v["net_r"]>0 for v in yy.values()),
            "negative_years":sum(v["net_r"]<0 for v in yy.values()),"by_year":yy}

def cap_concurrent(ts,cap):
    accepted=[]
    # Entries at the same instant are prioritized by stronger signal RS.
    for t in sorted(ts,key=lambda x:(x["entry_t"],-x.get("signal_ret60",0),x["symbol"])):
        active=sum(1 for a in accepted if a["entry_t"]<=t["entry_t"]<a["exit_t"])
        if active<cap:accepted.append(t)
    return accepted

def topn_same_fill_slot(ts,n):
    # No-lookahead: only resolves trades whose actual fills share the same 15m timestamp.
    groups=defaultdict(list)
    for t in ts:groups[t["entry_t"]].append(t)
    out=[]
    for _,g in sorted(groups.items()):
        g=sorted(g,key=lambda x:(-x.get("signal_ret60",0),x["symbol"]))
        out.extend(g[:n])
    return sorted(out,key=lambda x:(x["entry_t"],x["symbol"]))

def main():
    m1=json.loads(M1.read_text())
    trades=m1["trades"]
    dailies=collect_daily();bm=breadth_map(dailies)
    enriched=[]
    for t in trades:
        q=t.copy();ds=et_date(t["signal_t"])
        b,above,eligible=bm.get(ds,(None,0,0))
        q["breadth"]=b;q["breadth_above"]=above;q["breadth_eligible"]=eligible
        enriched.append(q)

    b50=[t for t in enriched if t["breadth"] is not None and t["breadth"]>=.50]
    cap3=cap_concurrent(enriched,3)
    b50_cap3=cap_concurrent(b50,3)
    b50_fill_top1=topn_same_fill_slot(b50,1)
    b50_fill_top2=topn_same_fill_slot(b50,2)
    b50_fill_top3=topn_same_fill_slot(b50,3)

    variants={
      "M1_base":enriched,
      "M1_breadth50":b50,
      "M1_cap3":cap3,
      "M1_breadth50_cap3":b50_cap3,
      "M1_breadth50_same_fill_top1":b50_fill_top1,
      "M1_breadth50_same_fill_top2":b50_fill_top2,
      "M1_breadth50_same_fill_top3":b50_fill_top3
    }
    report={
      "generated_at":datetime.now(UTC).isoformat(),
      "period":{"start":"2006-04-01","end_exclusive":"2026-04-01"},
      "definitions":{
        "breadth50":"On the M1 signal day's completed RTH close, >=50% of eligible current-53 universe closes are above EMA50.",
        "cap3":"Conservative post-filter admission: at most 3 overlapping accepted positions; simultaneous fills prioritized by higher signal_ret60.",
        "same_fill_topN":"Among trades whose exact 15m fill timestamp is identical, retain the N highest signal_ret60. This is intentionally narrower than ex-post ranking all same-day filled trades."
      },
      "results":{k:pack(v) for k,v in variants.items()},
      "recent":{k:{
        "2016_2026":pack([t for t in v if datetime.fromtimestamp(t["entry_t"]/1000,UTC).year>=2016]),
        "2022_2026":pack([t for t in v if datetime.fromtimestamp(t["entry_t"]/1000,UTC).year>=2022])
      } for k,v in variants.items()},
      "notes":[
        "These are conservative post-filters over the locked M1 trade set. A filtered/skipped trade does not create replacement later signals that the original per-symbol simulation may have suppressed.",
        "No thresholds were searched in this run: breadth is fixed at 50% and concurrency cap at 3.",
        "Same-fill topN avoids using future information about which pending signal will eventually fill."
      ]
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"results":report["results"],"recent":report["recent"]},ensure_ascii=False,indent=2))

if __name__=="__main__":main()
