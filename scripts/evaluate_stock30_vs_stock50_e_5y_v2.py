import bisect,json,time,sys
from collections import defaultdict
from datetime import datetime,timezone,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import duckdb

sys.path.insert(0,str(Path(__file__).parent))
import backtest_wyckoff_5y_exact_touch as bt
import wyckoff_status as w

STOCK50=Path("data/validation/stock50_track_b_hf_5y_exact_touch.json")
OUT=Path("data/validation/stock30_vs_stock50_e_5y_v2.json")
UTC=timezone.utc; NY=ZoneInfo("America/New_York")
START=datetime(2021,4,1,tzinfo=UTC); END=datetime(2026,4,1,tzinfo=UTC)
WARMUP=datetime(2020,10,1,tzinfo=UTC)
HF_BASE="https://huggingface.co/datasets/mito0o852/OHLCV-1m/resolve/main/data"
FEE_BPS=4.0; SLIPPAGE_BPS=2.0
A_OFF={"climax_spread_min":999.0,"climax_volume_min":999.0}

SYMS30=("SPY","QQQ","IWM","AAPL","MSFT","NVDA","AMZN","META","GOOGL","TSLA",
        "AVGO","AMD","NFLX","ORCL","JPM","BAC","GS","V","MA","XOM","CVX","JNJ",
        "UNH","LLY","MRK","WMT","COST","HD","CAT","KO")
SYMS50=(
    "AAPL","AMZN","AVGO","CRCL","MSFT","MU","SNDK","SNXX","SOXL","SPCX",
    "AMD","BABA","INTC","JPM","KORU","MSTR","NFLX","SKHY","SOXS","V",
    "COST","GOOGL","LLY","META","NBIS","NVDA","QQQ","TSLA","UBER","WMT",
    "AMAT","CAT","DRAM","EWY","HD","MRVL","MUU","ORCL","SPY","TSM",
    "AAOI","BE","COIN","CRM","CSCO","DIS","HOOD","IBM","LITE","TQQQ"
)
OVERLAP=tuple(sorted(set(SYMS30)&set(SYMS50)))
MISSING10=tuple(sorted(set(SYMS30)-set(SYMS50)))
UNION=tuple(sorted(set(SYMS30)|set(SYMS50)|{"FB","GOOG"}))

def month_iter(start,end):
    y,m=start.year,start.month
    while (y,m)<(end.year,end.month):
        yield y,m
        m+=1
        if m==13:y,m=y+1,1

def canonical(ticker,d):
    if ticker=="FB": return "META" if d<datetime(2022,6,9).date() else None
    if ticker=="META": return "META" if d>=datetime(2022,6,9).date() else None
    if ticker=="GOOG": return "GOOGL" if d<datetime(2014,4,3).date() else None
    if ticker=="GOOGL": return "GOOGL" if d>=datetime(2014,4,3).date() else None
    return ticker if ticker in set(SYMS30)|set(SYMS50) else None

def remote_15m_union(con,y,m):
    url=f"{HF_BASE}/ohlcv_{y:04d}-{m:02d}.parquet"
    ph=",".join(["?"]*len(UNION))
    q=f"""
    WITH src AS (
      SELECT ticker,timezone('America/New_York',timestamp) et,open,high,low,"close",volume
      FROM read_parquet('{url}') WHERE ticker IN ({ph})
    ),rth AS (
      SELECT * FROM src WHERE cast(et as time)>=time '09:30:00' and cast(et as time)<time '16:00:00'
    ),agg AS (
      SELECT ticker,time_bucket(interval '15 minutes',et) et_bucket,
             arg_min(open,et) o,max(high) h,min(low) l,arg_max("close",et) c,sum(volume) v
      FROM rth GROUP BY ticker,et_bucket
    )
    SELECT ticker,et_bucket,o,h,l,c,v FROM agg ORDER BY ticker,et_bucket
    """
    return con.execute(q,list(UNION)).fetchall()

def collect_all():
    con=duckdb.connect();con.execute("INSTALL httpfs; LOAD httpfs;")
    missing15={s:[] for s in MISSING10}
    daily_groups={s:{} for s in set(SYMS30)|set(SYMS50)}
    missing=[]
    daily_start=START-timedelta(days=390)
    for y,m in month_iter(daily_start,END):
        rows=None
        for a in range(5):
            try:
                t0=time.time();rows=remote_15m_union(con,y,m)
                print("PASS",f"{y:04d}-{m:02d}",len(rows),round(time.time()-t0,2),flush=True);break
            except Exception as e:
                print("PASS_RETRY",y,m,a+1,repr(e),flush=True);time.sleep(3*(a+1))
        if rows is None:missing.append(f"{y:04d}-{m:02d}");continue
        for ticker,et,o,h,l,cl,v in rows:
            if et.tzinfo is None:et=et.replace(tzinfo=NY)
            else:et=et.astimezone(NY)
            s=canonical(str(ticker),et.date())
            if not s:continue
            utc=et.astimezone(UTC); tms=int(utc.timestamp()*1000)
            bar={"t":tms,"o":float(o),"h":float(h),"l":float(l),"c":float(cl),"v":float(v or 0)}
            if s in missing15 and WARMUP<=utc<END:
                missing15[s].append(bar)
            if daily_start<=utc<END:
                day=et.date()
                g=daily_groups[s].get(day)
                if g is None:
                    daily_groups[s][day]={"t":tms,"o":bar["o"],"h":bar["h"],"l":bar["l"],"c":bar["c"],"v":bar["v"],"last_t":tms}
                else:
                    g["h"]=max(g["h"],bar["h"]);g["l"]=min(g["l"],bar["l"])
                    g["c"]=bar["c"];g["v"]+=bar["v"];g["last_t"]=tms
    con.close()
    if missing:raise RuntimeError("missing months "+",".join(missing))
    for s in missing15:missing15[s].sort(key=lambda z:z["t"])
    dailies={}
    for s,gm in daily_groups.items():
        bars=[]
        for _,g in sorted(gm.items()):
            bars.append({"t":g["t"],"o":g["o"],"h":g["h"],"l":g["l"],"c":g["c"],"v":g["v"],
                         "ct":g["last_t"]+15*60*1000-1})
        if bars:
            # Align E indicators with the split-adjusted price history used by the backtests.
            bars=apply_splits(bars,detect_splits(bars))
            dailies[s]=w.enrich(bars)
    return missing15,dailies

def day_key(z):return datetime.fromtimestamp(z["t"]/1000,UTC).astimezone(NY).date()

def detect_splits(bars):
    byday=defaultdict(list)
    for z in bars:byday[day_key(z)].append(z)
    days=sorted(byday); common=(2,3,4,5,7,10,15,20); ev=[]
    for i in range(1,len(days)):
        prev=byday[days[i-1]][-1]["c"];op=byday[days[i]][0]["o"]
        if prev<=0 or op<=0 or (days[i]-days[i-1]).days>14:continue
        ratio=prev/op;mag=ratio if ratio>=1 else 1/ratio
        if mag<1.7:continue
        f=min(common,key=lambda q:abs(mag/q))
        if abs(mag/f)<=.08:
            pm,vm=((1/f,f) if ratio>1 else (f,1/f));ev.append((days[i],pm,vm))
    return ev

def apply_splits(bars,ev):
    out=[]
    for z in bars:
        d=day_key(z);pm=vm=1.0
        for sd,p,v in ev:
            if d<sd:pm*=p;vm*=v
        q=z.copy()
        for k in ("o","h","l","c"):q[k]*=pm
        q["v"]*=vm;out.append(q)
    return out

def aggregate_4h(bars):
    g=defaultdict(list)
    for z in bars:
        dt=datetime.fromtimestamp(z["t"]/1000,UTC).astimezone(NY)
        mins=(dt.hour*60+dt.minute)-(9*60+30)
        if mins<0 or mins>=390:continue
        g[(dt.date(),0 if mins<240 else 1)].append(z)
    out=[]
    for _,a in sorted(g.items()):
        a.sort(key=lambda x:x["t"])
        out.append({"t":a[0]["t"],"o":a[0]["o"],"h":max(x["h"] for x in a),"l":min(x["l"] for x in a),
                    "c":a[-1]["c"],"v":sum(x["v"] for x in a)})
    return out

def aggregate_daily(bars):
    g=defaultdict(list)
    for z in bars:g[day_key(z)].append(z)
    out=[]
    for _,a in sorted(g.items()):
        a.sort(key=lambda x:x["t"])
        out.append({"t":a[0]["t"],"o":a[0]["o"],"h":max(x["h"] for x in a),"l":min(x["l"] for x in a),
                    "c":a[-1]["c"],"v":sum(x["v"] for x in a)})
    return out

def simulate_missing(by):
    alltr=[]
    old_dataset,old_filters=bt.dataset,bt.symbol_filters
    old_cap,old_risk=bt.CAP,bt.RISK
    bt.CAP=20000.0;bt.RISK=400.0
    try:
        for sym in MISSING10:
            bars=apply_splits(by[sym],detect_splits(by[sym]))
            H=w.enrich(aggregate_4h(bars));D=w.enrich(aggregate_daily(bars));M=bars
            bt._CACHE.clear()
            bt.dataset=lambda _s,D=D,H=H,M=M:(D,H,M)
            bt.symbol_filters=lambda _s:(0.01,0.0,0.0)
            r=bt.simulate(sym,a_params=A_OFF,b_params=None,
                start_ms=int(START.timestamp()*1000),end_ms=int(END.timestamp()*1000)-1,
                fee_bps=FEE_BPS,slippage_bps=SLIPPAGE_BPS,
                a_mode="snapshot",b_runner_mode="pivot",b_scale_mode="30_30_40")
            ts=[{"symbol":sym,**t} for t in r["trades"] if t["track"]=="B" and t["reason"]!="OPEN_MARK"]
            alltr.extend(ts)
            print("MISS_RESULT",sym,len(ts),sum(t["r"] for t in ts),flush=True)
    finally:
        bt.dataset,bt.symbol_filters=old_dataset,old_filters;bt.CAP,bt.RISK=old_cap,old_risk
    return alltr

def idx(D,t):
    return bisect.bisect_left([x.get("ct",x["t"]+24*60*60*1000-1) for x in D],t)-1
def ret20(D,i):
    return D[i]["c"]/D[i-20]["c"]-1 if i>=20 and D[i-20]["c"]>0 else None

def e_pass(t,dailies,universe):
    if t["direction"]!="LONG":return False
    D=dailies.get(t["symbol"]);spy=dailies.get("SPY")
    if not D or not spy:return False
    i=idx(D,t["entry_t"]);si=idx(spy,t["entry_t"])
    if i<50 or si<50:return False
    rr=ret20(D,i);sr=ret20(spy,si)
    if rr is None or sr is None:return False
    s=spy[si];votes=int(s["c"]>s["ema50"])+int(s["ema20"]>s["ema50"])+int(sr>0)
    eligible=above=0
    for sym in universe:
        U=dailies.get(sym)
        if not U:continue
        ui=idx(U,t["entry_t"])
        if ui>=50 and U[ui].get("ema50") is not None:
            eligible+=1;above+=int(U[ui]["c"]>U[ui]["ema50"])
    breadth=above/eligible if eligible else None
    return votes>=2 and rr>=sr and breadth is not None and breadth>=.50

def stats(ts):
    ts=sorted(ts,key=lambda x:(x["exit_t"],x["symbol"]))
    n=len(ts);w=sum(x["pnl"]>0 for x in ts);l=sum(x["pnl"]<0 for x in ts)
    net=sum(x["r"] for x in ts);gp=sum(x["r"] for x in ts if x["r"]>0);gl=sum(x["r"] for x in ts if x["r"]<0)
    cr=pr=mdd=0.0;st=best=0
    for x in ts:
        cr+=x["r"];pr=max(pr,cr);mdd=max(mdd,pr-cr)
        if x["r"]<0:st+=1;best=max(best,st)
        else:st=0
    return {"trades":n,"wins":w,"losses":l,"win_rate":w/n if n else None,
            "net_r":net,"avg_r":net/n if n else None,"profit_factor":gp/abs(gl) if gl<0 else None,
            "max_drawdown_r":mdd,"max_consecutive_losses":best}

def by_year(ts):
    out={}
    for y in range(2021,2027):
        xs=[t for t in ts if datetime.fromtimestamp(t["entry_t"]/1000,UTC).year==y]
        if xs:out[str(y)]=stats(xs)
    return out

def main():
    stock50=json.loads(STOCK50.read_text())
    t50=[t for t in stock50["trades"] if int(START.timestamp()*1000)<=t["entry_t"]<int(END.timestamp()*1000)]
    overlap=set(OVERLAP)
    t30_overlap=[t for t in t50 if t["symbol"] in overlap]
    missing15,dailies=collect_all()
    t30_missing=simulate_missing(missing15)
    t30=sorted(t30_overlap+t30_missing,key=lambda x:(x["entry_t"],x["symbol"]))
    e30=[t for t in t30 if e_pass(t,dailies,SYMS30)]
    e50=[t for t in t50 if e_pass(t,dailies,SYMS50)]
    report={
      "generated_at":datetime.now(UTC).isoformat(),
      "period":{"start":START.isoformat(),"end_exclusive":END.isoformat()},
      "universes":{"stock30":list(SYMS30),"stock50":list(SYMS50),"overlap":list(OVERLAP),"missing10_simulated":list(MISSING10)},
      "definition_E":"LONG + SPY bull regime >=2/3 + stock 20d return >= SPY 20d return + universe breadth >=50% above EMA50",
      "results":{
        "stock30":{"base":stats(t30),"E":stats(e30),"E_by_year":by_year(e30)},
        "stock50":{"base":stats(t50),"E":stats(e50),"E_by_year":by_year(e50)}
      },
      "notes":[
        "The 20 symbols shared by stock30 and stock50 reuse the already validated stock50 exact-touch trades.",
        "The 10 stock30-only symbols are simulated with the same frozen exact-touch engine/costs.",
        "Breadth is recalculated independently inside each universe using only completed RTH daily bars before each entry."
      ]
    }
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report["results"],ensure_ascii=False,indent=2))

if __name__=="__main__":main()
