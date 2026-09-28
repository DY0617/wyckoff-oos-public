import bisect, json, math, os, sys, time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import duckdb

sys.path.insert(0,str(Path(__file__).parent))
import backtest_wyckoff_exact_touch_ct as bt
import wyckoff_status as w

UTC=timezone.utc; NY=ZoneInfo("America/New_York")
HF_BASE="https://huggingface.co/datasets/mito0o852/OHLCV-1m/resolve/main/data"
FEE_BPS=4.0; SLIPPAGE_BPS=2.0
A_OFF={"climax_spread_min":999.0,"climax_volume_min":999.0}
BASE53=Path("data/validation/stock53_track_b_hf_20y_exact_touch.json")

STOCK50=(
"AAPL","AMZN","AVGO","CRCL","MSFT","MU","SNDK","SNXX","SOXL","SPCX",
"AMD","BABA","INTC","JPM","KORU","MSTR","NFLX","SKHY","SOXS","V",
"COST","GOOGL","LLY","META","NBIS","NVDA","QQQ","TSLA","UBER","WMT",
"AMAT","CAT","DRAM","EWY","HD","MRVL","MUU","ORCL","SPY","TSM",
"AAOI","BE","COIN","CRM","CSCO","DIS","HOOD","IBM","LITE","TQQQ"
)
STOCK53=(
"AAPL","AMZN","AVGO","CRCL","DELL","MSFT","MU","SNDK","SNXX","SOXL","SPCX",
"AMD","BABA","INTC","JPM","KORU","MSTR","NFLX","SKHY","SMCI","SOXS","V",
"COST","GOOGL","LLY","META","NBIS","NVDA","QQQ","TSLA","UBER","WMT",
"AMAT","CAT","DRAM","EWY","HD","MRVL","MUU","ORCL","SPY","TSM",
"AAOI","AXTI","BE","COIN","CRM","CSCO","DIS","HOOD","IBM","LITE","TQQQ"
)
STOCK30=("SPY","QQQ","IWM","AAPL","MSFT","NVDA","AMZN","META","GOOGL","TSLA",
         "AVGO","AMD","NFLX","ORCL","JPM","BAC","GS","V","MA","XOM","CVX","JNJ",
         "UNH","LLY","MRK","WMT","COST","HD","CAT","KO")
OVERLAP30=tuple(sorted(set(STOCK30)&set(STOCK53)))
MISSING10=tuple(sorted(set(STOCK30)-set(STOCK53)))
UNIVERSE=tuple(sorted(set(STOCK53)|set(STOCK30)))
SOURCE=tuple(sorted(set(UNIVERSE)|{"FB","GOOG"}))

def pd(s): return datetime.strptime(s,"%Y-%m-%d").replace(tzinfo=UTC)
EVAL_START=pd(os.environ["EVAL_START"])
EVAL_END=pd(os.environ["EVAL_END"])
DATA_END=min(pd(os.environ.get("DATA_END","2026-04-01")),EVAL_END+timedelta(days=90))
WARMUP_START=EVAL_START-timedelta(days=390)
OUT=Path(os.environ["OUT"])

NOT_BEFORE={
    "DELL":datetime(2018,12,28,tzinfo=UTC),
    "SNDK":datetime(2025,2,24,tzinfo=UTC),
}

def month_iter(start,end):
    y,m=start.year,start.month
    while (y,m)<=(end.year,end.month):
        yield y,m
        m+=1
        if m==13:y,m=y+1,1

def canonical(ticker,d):
    if ticker=="FB": return "META" if d<datetime(2022,6,9).date() else None
    if ticker=="META": return "META" if d>=datetime(2022,6,9).date() else None
    if ticker=="GOOG": return "GOOGL" if d<datetime(2014,4,3).date() else None
    if ticker=="GOOGL": return "GOOGL" if d>=datetime(2014,4,3).date() else None
    return ticker if ticker in UNIVERSE else None

def remote_15m(con,y,m):
    url=f"{HF_BASE}/ohlcv_{y:04d}-{m:02d}.parquet"
    ph=",".join(["?"]*len(SOURCE))
    q=f"""
    WITH src AS (
      SELECT ticker,timezone('America/New_York',timestamp) et,
             open,high,low,"close",volume
      FROM read_parquet('{url}') WHERE ticker IN ({ph})
    ),rth AS (
      SELECT * FROM src
      WHERE cast(et as time)>=time '09:30:00' and cast(et as time)<time '16:00:00'
    ),agg AS (
      SELECT ticker,time_bucket(interval '15 minutes',et) et_bucket,
             arg_min(open,et) o,max(high) h,min(low) l,arg_max("close",et) c,sum(volume) v
      FROM rth GROUP BY ticker,et_bucket
    )
    SELECT ticker,et_bucket,o,h,l,c,v FROM agg ORDER BY ticker,et_bucket
    """
    return con.execute(q,list(SOURCE)).fetchall()

def collect():
    con=duckdb.connect();con.execute("INSTALL httpfs; LOAD httpfs;")
    allbars={s:[] for s in UNIVERSE};missing=[];months=0
    for y,m in month_iter(WARMUP_START,DATA_END-timedelta(days=1)):
        rows=None
        for a in range(6):
            try:
                t0=time.time();rows=remote_15m(con,y,m)
                print("MONTH",f"{y:04d}-{m:02d}",len(rows),round(time.time()-t0,2),flush=True);break
            except Exception as e:
                print("RETRY",y,m,a+1,repr(e),flush=True);time.sleep(min(30,4*(a+1)))
        if rows is None:
            missing.append(f"{y:04d}-{m:02d}");continue
        months+=1
        for ticker,et,o,h,l,c,v in rows:
            if et.tzinfo is None: et=et.replace(tzinfo=NY)
            else: et=et.astimezone(NY)
            sym=canonical(str(ticker),et.date())
            if not sym: continue
            utc=et.astimezone(UTC)
            nb=NOT_BEFORE.get(sym)
            if nb and utc<nb: continue
            if utc<WARMUP_START or utc>=DATA_END: continue
            tms=int(utc.timestamp()*1000)
            allbars[sym].append({"t":tms,"o":float(o),"h":float(h),"l":float(l),"c":float(c),
                                 "v":float(v or 0),"ct":tms+15*60*1000-1})
    con.close()
    if missing: raise RuntimeError("missing months="+",".join(missing))
    for s in allbars:allbars[s].sort(key=lambda z:z["t"])
    return allbars,months

def day_key(z):
    return datetime.fromtimestamp(z["t"]/1000,UTC).astimezone(NY).date()

def detect_splits(bars):
    byday=defaultdict(list)
    for z in bars:byday[day_key(z)].append(z)
    days=sorted(byday); common=(2,3,4,5,7,10,15,20);ev=[]
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
                    "c":a[-1]["c"],"v":sum(x["v"] for x in a),"ct":a[-1]["ct"]})
    return out

def aggregate_daily(bars):
    g=defaultdict(list)
    for z in bars:g[day_key(z)].append(z)
    out=[]
    for _,a in sorted(g.items()):
        a.sort(key=lambda x:x["t"])
        out.append({"t":a[0]["t"],"o":a[0]["o"],"h":max(x["h"] for x in a),"l":min(x["l"] for x in a),
                    "c":a[-1]["c"],"v":sum(x["v"] for x in a),"ct":a[-1]["ct"]})
    return out

def idx(D,t):
    return bisect.bisect_left([x["ct"] for x in D],t)-1

def ret20(D,i):
    return D[i]["c"]/D[i-20]["c"]-1 if i>=20 and D[i-20]["c"]>0 else None

def e_state(t,dailies,universe):
    if t["direction"]!="LONG":return False,None
    D=dailies.get(t["symbol"]);spy=dailies.get("SPY")
    if not D or not spy:return False,None
    i=idx(D,t["entry_t"]);si=idx(spy,t["entry_t"])
    if i<50 or si<50:return False,None
    rr=ret20(D,i);sr=ret20(spy,si)
    if rr is None or sr is None:return False,None
    s=spy[si]
    votes=int(s["c"]>s["ema50"])+int(s["ema20"]>s["ema50"])+int(sr>0)
    eligible=above=0
    for sym in universe:
        U=dailies.get(sym)
        if not U:continue
        ui=idx(U,t["entry_t"])
        if ui>=50 and U[ui].get("ema50") is not None:
            eligible+=1;above+=int(U[ui]["c"]>U[ui]["ema50"])
    breadth=above/eligible if eligible else None
    ok=votes>=2 and rr>=sr and breadth is not None and breadth>=.50
    return ok,{"spy_votes":votes,"stock_ret20":rr,"spy_ret20":sr,"breadth":breadth,
               "breadth_above":above,"breadth_eligible":eligible}

def stats(ts):
    n=len(ts);w=sum(t["pnl"]>0 for t in ts);l=sum(t["pnl"]<0 for t in ts)
    net=sum(t["r"] for t in ts);gp=sum(t["r"] for t in ts if t["r"]>0);gl=sum(t["r"] for t in ts if t["r"]<0)
    return {"closed":n,"wins":w,"losses":l,"win_rate":w/n if n else None,
            "net_r":net,"avg_r":net/n if n else None,"profit_factor":gp/abs(gl) if gl<0 else None}

def risk(ts):
    cr=pr=mdd=0.0;st=best=0
    for t in sorted(ts,key=lambda x:(x["exit_t"],x["symbol"])):
        cr+=t["r"];pr=max(pr,cr);mdd=max(mdd,pr-cr)
        if t["r"]<0:st+=1;best=max(best,st)
        else:st=0
    return {"max_drawdown_r":mdd,"max_consecutive_losses":best}

def simulate_missing(bysym):
    out=[]
    old_dataset,old_filters=bt.dataset,bt.symbol_filters
    old_cap,old_risk=bt.CAP,bt.RISK
    bt.CAP=20000.0;bt.RISK=400.0
    start_ms=int(EVAL_START.timestamp()*1000);end_ms=int(EVAL_END.timestamp()*1000)
    engine_end=int(DATA_END.timestamp()*1000)-1
    try:
        for sym in MISSING10:
            bars=apply_splits(bysym[sym],detect_splits(bysym[sym]))
            if not bars:continue
            H=w.enrich(aggregate_4h(bars));D=w.enrich(aggregate_daily(bars));M=bars
            if len(D)<60 or len(H)<60:continue
            bt._CACHE.clear()
            bt.dataset=lambda _s,D=D,H=H,M=M:(D,H,M)
            bt.symbol_filters=lambda _s:(0.01,0.0,0.0)
            r=bt.simulate(sym,a_params=A_OFF,b_params=None,start_ms=start_ms,end_ms=engine_end,
                          fee_bps=FEE_BPS,slippage_bps=SLIPPAGE_BPS,
                          a_mode="snapshot",b_runner_mode="pivot",b_scale_mode="30_30_40")
            ts=[{"symbol":sym,**t} for t in r["trades"] if t["track"]=="B" and t["reason"]!="OPEN_MARK"
                and start_ms<=t["entry_t"]<end_ms]
            out.extend(ts)
            print("MISSING",sym,len(ts),round(sum(t["r"] for t in ts),4),flush=True)
    finally:
        bt.dataset,bt.symbol_filters=old_dataset,old_filters;bt.CAP,bt.RISK=old_cap,old_risk
    return out

def main():
    base=json.loads(BASE53.read_text())
    lo=int(EVAL_START.timestamp()*1000);hi=int(EVAL_END.timestamp()*1000)
    base53=[t for t in base["trades"] if lo<=t["entry_t"]<hi]
    bysym,months=collect()
    adj={};dailies={}
    for sym,bars in bysym.items():
        if not bars:continue
        a=apply_splits(bars,detect_splits(bars));adj[sym]=a
        D=aggregate_daily(a)
        if D:dailies[sym]=w.enrich(D)
    miss=simulate_missing(adj)

    t53=base53
    t50=[t for t in base53 if t["symbol"] in set(STOCK50)]
    t30=[t for t in base53 if t["symbol"] in set(OVERLAP30)]+miss
    t30.sort(key=lambda x:(x["entry_t"],x["symbol"]))

    variants={}
    audits={}
    for name,trades,u in [("stock30",t30,STOCK30),("stock50",t50,STOCK50),("stock53_control",t53,STOCK53)]:
        kept=[];audit=[]
        for t in trades:
            ok,ctx=e_state(t,dailies,u)
            if ok:kept.append(t)
            audit.append({"symbol":t["symbol"],"entry_t":t["entry_t"],"r":t["r"],"pass":ok,"ctx":ctx})
        variants[name]={"base_trades":trades,"e_trades":kept,"audit":audit}
        print("VARIANT",name,"base",len(trades),"E",len(kept),"R",round(sum(x["r"] for x in kept),4),flush=True)

    report={
      "eval_start":EVAL_START.isoformat(),"eval_end_exclusive":EVAL_END.isoformat(),"months_loaded":months,
      "universes":{"stock30":list(STOCK30),"stock50":list(STOCK50),"stock53_control":list(STOCK53),
                   "stock30_only_missing10":list(MISSING10),"stock30_overlap53":list(OVERLAP30)},
      "definition_E":"LONG + prior completed SPY bull regime >=2/3 of close>EMA50, EMA20>EMA50, 20d return>0 + stock 20d return >= SPY 20d return + universe breadth >=50% above EMA50",
      "variants":variants
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")

if __name__=="__main__":main()
