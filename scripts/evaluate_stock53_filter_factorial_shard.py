import bisect, json, os, time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
import sys
sys.path.insert(0, str(Path(__file__).parent))
import wyckoff_status as w

SYMS=(
"AAPL","AMZN","AVGO","CRCL","DELL","MSFT","MU","SNDK","SNXX","SOXL","SPCX",
"AMD","BABA","INTC","JPM","KORU","MSTR","NFLX","SKHY","SMCI","SOXS","V",
"COST","GOOGL","LLY","META","NBIS","NVDA","QQQ","TSLA","UBER","WMT",
"AMAT","CAT","DRAM","EWY","HD","MRVL","MUU","ORCL","SPY","TSM",
"AAOI","AXTI","BE","COIN","CRM","CSCO","DIS","HOOD","IBM","LITE","TQQQ"
)
SOURCE_TICKERS=tuple(sorted(set(SYMS+("FB","GOOG"))))
HF_BASE="https://huggingface.co/datasets/mito0o852/OHLCV-1m/resolve/main/data"
NY=ZoneInfo("America/New_York"); UTC=timezone.utc
NOT_BEFORE={"DELL":datetime(2018,12,28,tzinfo=UTC),"SNDK":datetime(2025,2,24,tzinfo=UTC)}

def pd(s): return datetime.strptime(s,"%Y-%m-%d").replace(tzinfo=UTC)
EVAL_START=pd(os.environ["EVAL_START"]); EVAL_END=pd(os.environ["EVAL_END"])
WARMUP_START=EVAL_START-timedelta(days=390)
OUT=Path(os.environ["OUT"])
BASE=Path("data/validation/stock53_track_b_hf_20y_exact_touch.json")

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
    return ticker if ticker in SYMS else None

def remote_daily(con,y,m):
    url=f"{HF_BASE}/ohlcv_{y:04d}-{m:02d}.parquet"
    ph=",".join(["?"]*len(SOURCE_TICKERS))
    q=f"""
    WITH src AS (
      SELECT ticker,timezone('America/New_York',timestamp) et,open,high,low,"close",volume
      FROM read_parquet('{url}') WHERE ticker IN ({ph})
    ),rth AS (
      SELECT * FROM src WHERE cast(et as time)>=time '09:30:00' and cast(et as time)<time '16:00:00'
    )
    SELECT ticker,cast(et as date) d,min(et) first_et,max(et) last_et,
           arg_min(open,et) o,max(high) h,min(low) l,arg_max("close",et) c,sum(volume) v
    FROM rth
    GROUP BY ticker,cast(et as date)
    ORDER BY ticker,d
    """
    return con.execute(q,list(SOURCE_TICKERS)).fetchall()

def collect():
    con=duckdb.connect();con.execute("INSTALL httpfs; LOAD httpfs;")
    by={s:[] for s in SYMS};missing=[];months=0
    for y,m in month_iter(WARMUP_START,EVAL_END-timedelta(days=1)):
        rows=None
        for a in range(5):
            try:
                t0=time.time();rows=remote_daily(con,y,m)
                print("MONTH",f"{y:04d}-{m:02d}",len(rows),round(time.time()-t0,2),flush=True);break
            except Exception as e:
                print("RETRY",y,m,a+1,repr(e),flush=True);time.sleep(4*(a+1))
        if rows is None:
            missing.append(f"{y:04d}-{m:02d}");continue
        months+=1
        for ticker,d,first_et,last_et,o,h,l,c,v in rows:
            s=canonical(str(ticker),d)
            if not s:continue
            f=first_et.replace(tzinfo=NY) if first_et.tzinfo is None else first_et.astimezone(NY)
            z=last_et.replace(tzinfo=NY) if last_et.tzinfo is None else last_et.astimezone(NY)
            utc=f.astimezone(UTC)
            if utc<WARMUP_START or utc>=EVAL_END:continue
            nb=NOT_BEFORE.get(s)
            if nb and utc<nb:continue
            tms=int(utc.timestamp()*1000)
            ct=int(z.astimezone(UTC).timestamp()*1000)+60_000-1
            by[s].append({"t":tms,"o":float(o),"h":float(h),"l":float(l),"c":float(c),
                          "v":float(v or 0),"ct":ct})
    con.close()
    if missing:raise RuntimeError("missing months="+",".join(missing))
    for s in by:by[s].sort(key=lambda z:z["t"])
    return by,months

def detect_splits(bars):
    common=(2,3,4,5,7,10,15,20);ev=[]
    for i in range(1,len(bars)):
        prev=bars[i-1]["c"];op=bars[i]["o"]
        if prev<=0 or op<=0:continue
        d0=datetime.fromtimestamp(bars[i-1]["t"]/1000,UTC).date()
        d1=datetime.fromtimestamp(bars[i]["t"]/1000,UTC).date()
        if (d1-d0).days>14:continue
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

def ret20(D,i):
    if i<20 or D[i-20]["c"]<=0:return None
    return D[i]["c"]/D[i-20]["c"]-1

def latest_idx(D,entry_t):
    cts=[x["ct"] for x in D]
    return bisect.bisect_left(cts,entry_t)-1

def state_for(sym,dailies,entry_t):
    D=dailies.get(sym);spyD=dailies.get("SPY")
    if not D or not spyD:return None
    i=latest_idx(D,entry_t);si=latest_idx(spyD,entry_t)
    if i<50 or si<50:return None
    rr=ret20(D,i);sr=ret20(spyD,si)
    if rr is None or sr is None:return None
    s=spyD[si]
    votes=int(s["c"]>s["ema50"])+int(s["ema20"]>s["ema50"])+int(sr>0)
    eligible=above=0
    for _,UD in dailies.items():
        ui=latest_idx(UD,entry_t)
        if ui>=50 and UD[ui].get("ema50") is not None:
            eligible+=1
            above+=int(UD[ui]["c"]>UD[ui]["ema50"])
    breadth=(above/eligible) if eligible else None
    return {
      "spy_regime":votes>=2,"spy_votes":votes,
      "rs_ok":rr>=sr,"stock_ret20":rr,"spy_ret20":sr,
      "breadth":breadth,"breadth_ok":breadth is not None and breadth>=.50,
      "breadth_above":above,"breadth_eligible":eligible
    }

def main():
    base=json.loads(BASE.read_text())
    lo=int(EVAL_START.timestamp()*1000);hi=int(EVAL_END.timestamp()*1000)
    trades=[t for t in base["trades"] if lo<=t["entry_t"]<hi]
    by,months=collect()
    dailies={};errors={}
    for s in SYMS:
        try:
            bars=apply_splits(by[s],detect_splits(by[s]))
            if bars:dailies[s]=w.enrich(bars)
        except Exception as e:errors[s]=repr(e)
    if "SPY" not in dailies:raise RuntimeError("SPY daily missing")

    variants={k:[] for k in (
      "A_current","B_long_only","C_spy_only","R_rs_only","M_breadth_only",
      "CR_D_spy_rs","CM_spy_breadth","RM_rs_breadth","CRM_E_spy_rs_breadth"
    )}
    audit=[]
    for t in trades:
        variants["A_current"].append(t)
        if t["direction"]!="LONG":continue
        variants["B_long_only"].append(t)
        st=state_for(t["symbol"],dailies,t["entry_t"])
        audit.append({"symbol":t["symbol"],"entry_t":t["entry_t"],"r":t["r"],"state":st})
        if not st:continue
        S=st["spy_regime"];R=st["rs_ok"];M=st["breadth_ok"]
        if S:variants["C_spy_only"].append(t)
        if R:variants["R_rs_only"].append(t)
        if M:variants["M_breadth_only"].append(t)
        if S and R:variants["CR_D_spy_rs"].append(t)
        if S and M:variants["CM_spy_breadth"].append(t)
        if R and M:variants["RM_rs_breadth"].append(t)
        if S and R and M:variants["CRM_E_spy_rs_breadth"].append(t)

    definitions={
      "A_current":"all current Track B trades, LONG+SHORT",
      "B_long_only":"Track B LONG only",
      "C_spy_only":"LONG + prior completed SPY bull regime: >=2/3 of close>EMA50, EMA20>EMA50, 20d return>0",
      "R_rs_only":"LONG + stock 20d return >= SPY 20d return",
      "M_breadth_only":"LONG + >=50% of available 53-symbol universe closes above EMA50",
      "CR_D_spy_rs":"LONG + SPY bull regime + stock 20d return >= SPY 20d return (D)",
      "CM_spy_breadth":"LONG + SPY bull regime + breadth>=50%",
      "RM_rs_breadth":"LONG + stock 20d return >= SPY 20d return + breadth>=50%, no SPY regime requirement",
      "CRM_E_spy_rs_breadth":"LONG + SPY bull regime + stock 20d return >= SPY 20d return + breadth>=50% (E)"
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps({
      "eval_start":EVAL_START.isoformat(),"eval_end_exclusive":EVAL_END.isoformat(),
      "months_loaded":months,"definitions":definitions,"errors":errors,
      "variants":variants,"audit":audit
    },ensure_ascii=False,indent=2),encoding="utf-8")
    print("FINAL",json.dumps({k:len(v) for k,v in variants.items()}),flush=True)

if __name__=="__main__":main()
