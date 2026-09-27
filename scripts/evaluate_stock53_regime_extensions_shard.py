import bisect, json, math, os, time
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
# 252 trading-day volatility percentile needs more than the old 190-calendar-day warmup.
WARMUP_START=EVAL_START-timedelta(days=390)
OUT=Path(os.environ["OUT"])
BASE=Path("data/validation/stock53_track_b_hf_20y_exact_touch.json")

def month_iter(start,end):
    y,m=start.year,start.month
    while (y,m)<=(end.year,end.month):
        yield y,m
        m+=1
        if m==13:y,m=y+1,1

def canonical(ticker,et):
    d=et.date()
    if ticker=="FB": return "META" if d<datetime(2022,6,9).date() else None
    if ticker=="META": return "META" if d>=datetime(2022,6,9).date() else None
    if ticker=="GOOG": return "GOOGL" if d<datetime(2014,4,3).date() else None
    if ticker=="GOOGL": return "GOOGL" if d>=datetime(2014,4,3).date() else None
    return ticker if ticker in SYMS else None

def remote_15m(con,y,m):
    url=f"{HF_BASE}/ohlcv_{y:04d}-{m:02d}.parquet"
    ph=",".join(["?"]*len(SOURCE_TICKERS))
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
    return con.execute(q,list(SOURCE_TICKERS)).fetchall()

def collect():
    con=duckdb.connect(); con.execute("INSTALL httpfs; LOAD httpfs;")
    by={s:[] for s in SYMS}; missing=[]; months=0
    for y,m in month_iter(WARMUP_START,EVAL_END-timedelta(days=1)):
        rows=None
        for a in range(5):
            try:
                t=time.time(); rows=remote_15m(con,y,m)
                print("MONTH",f"{y:04d}-{m:02d}",len(rows),round(time.time()-t,2),flush=True); break
            except Exception as e:
                print("RETRY",y,m,a+1,repr(e),flush=True); time.sleep(4*(a+1))
        if rows is None:
            missing.append(f"{y:04d}-{m:02d}"); continue
        months+=1
        for ticker,et,o,h,l,c,v in rows:
            et=et.replace(tzinfo=NY) if et.tzinfo is None else et.astimezone(NY)
            s=canonical(str(ticker),et)
            if not s: continue
            utc=et.astimezone(UTC)
            if utc<WARMUP_START or utc>=EVAL_END: continue
            nb=NOT_BEFORE.get(s)
            if nb and utc<nb: continue
            tms=int(utc.timestamp()*1000)
            by[s].append({"t":tms,"o":float(o),"h":float(h),"l":float(l),"c":float(c),
                          "v":float(v or 0),"ct":tms+15*60*1000-1})
    con.close()
    if missing: raise RuntimeError("missing months="+",".join(missing))
    for s in by: by[s].sort(key=lambda z:z["t"])
    return by,months

def day_key(z): return datetime.fromtimestamp(z["t"]/1000,UTC).astimezone(NY).date()

def detect_splits(bars):
    byday=defaultdict(list)
    for z in bars: byday[day_key(z)].append(z)
    days=sorted(byday); common=(2,3,4,5,7,10,15,20); ev=[]
    for i in range(1,len(days)):
        prev=byday[days[i-1]][-1]["c"]; op=byday[days[i]][0]["o"]
        if prev<=0 or op<=0 or (days[i]-days[i-1]).days>14: continue
        ratio=prev/op; mag=ratio if ratio>=1 else 1/ratio
        if mag<1.7: continue
        f=min(common,key=lambda q:abs(mag/q))
        if abs(mag/f)<=.08:
            pm,vm=((1/f,f) if ratio>1 else (f,1/f)); ev.append((days[i],pm,vm))
    return ev

def apply_splits(bars,ev):
    out=[]
    for z in bars:
        d=day_key(z); pm=vm=1.0
        for sd,p,v in ev:
            if d<sd: pm*=p; vm*=v
        q=z.copy()
        for k in ("o","h","l","c"): q[k]*=pm
        q["v"]*=vm; out.append(q)
    return out

def daily(bars):
    g=defaultdict(list)
    for z in bars: g[day_key(z)].append(z)
    out=[]
    for _,a in sorted(g.items()):
        a.sort(key=lambda x:x["t"])
        out.append({"t":a[0]["t"],"o":a[0]["o"],"h":max(x["h"] for x in a),
                    "l":min(x["l"] for x in a),"c":a[-1]["c"],"v":sum(x["v"] for x in a),
                    "ct":a[-1]["ct"]})
    return w.enrich(out)

def latest_idx(D,entry_t):
    cts=[x.get("ct",x["t"]+24*60*60*1000-1) for x in D]
    return bisect.bisect_left(cts,entry_t)-1

def ret20(D,i):
    if i<20 or D[i-20]["c"]<=0:return None
    return D[i]["c"]/D[i-20]["c"]-1

def q90(vals):
    if not vals:return None
    a=sorted(vals)
    return a[max(0,math.ceil(.90*len(a))-1)]

def state_for(sym,dailies,entry_t):
    D=dailies.get(sym); spyD=dailies.get("SPY")
    if not D or not spyD:return None
    i=latest_idx(D,entry_t); si=latest_idx(spyD,entry_t)
    if i<50 or si<50:return None
    rr=ret20(D,i); sr=ret20(spyD,si)
    if rr is None or sr is None:return None
    s=spyD[si]
    bull_votes=int(s["c"]>s["ema50"])+int(s["ema20"]>s["ema50"])+int(sr>0)
    bear_votes=int(s["c"]<s["ema50"])+int(s["ema20"]<s["ema50"])+int(sr<0)

    # E: cross-sectional market breadth, using only each symbol's latest completed daily bar.
    eligible=above=0
    rs_values=[]
    for u,UD in dailies.items():
        ui=latest_idx(UD,entry_t)
        if ui>=50 and UD[ui].get("ema50") is not None:
            eligible+=1
            above+=int(UD[ui]["c"]>UD[ui]["ema50"])
            ur=ret20(UD,ui)
            if ur is not None: rs_values.append((u,ur))
    breadth=(above/eligible) if eligible else None

    # F: current completed SPY NATR14 versus the 90th percentile of the PRECEDING 252 sessions.
    vol_ok=None; current_natr=None; vol_q90=None
    if si>=252 and s.get("atr") is not None and s["c"]>0:
        current_natr=s["atr"]/s["c"]
        hist=[]
        for k in range(si-252,si):
            if spyD[k].get("atr") is not None and spyD[k]["c"]>0:
                hist.append(spyD[k]["atr"]/spyD[k]["c"])
        if len(hist)>=240:
            vol_q90=q90(hist); vol_ok=current_natr<=vol_q90

    # G: stock 20d return must be at/above cross-sectional median (top half), known before entry.
    rs_top_half=None; rs_median=None
    if rs_values:
        vals=sorted(v for _,v in rs_values)
        n=len(vals)
        rs_median=vals[n//2] if n%2 else (vals[n//2-1]+vals[n//2])/2
        rs_top_half=rr>=rs_median

    return {
      "stock_ret20":rr,"spy_ret20":sr,
      "bull_regime":bull_votes>=2,"bear_regime":bear_votes>=2,
      "rs_vs_spy_long":rr>=sr,"rs_vs_spy_short":rr<=sr,
      "breadth":breadth,"breadth_ok":breadth is not None and breadth>=.50,
      "spy_natr14":current_natr,"vol_q90_252":vol_q90,"vol_ok":vol_ok,
      "rs_median20":rs_median,"rs_top_half":rs_top_half,
      "eligible_breadth":eligible,"eligible_rs":len(rs_values)
    }

def main():
    base=json.loads(BASE.read_text())
    lo=int(EVAL_START.timestamp()*1000); hi=int(EVAL_END.timestamp()*1000)
    trades=[t for t in base["trades"] if lo<=t["entry_t"]<hi]
    by,months=collect()
    dailies={}; errors={}
    for s in SYMS:
        try:
            bars=apply_splits(by[s],detect_splits(by[s]))
            if bars:dailies[s]=daily(bars)
        except Exception as e: errors[s]=repr(e)
    if "SPY" not in dailies: raise RuntimeError("SPY daily missing")

    variants={
      "D_long_spy_regime_rs20":[],
      "E_D_plus_breadth50":[],
      "F_D_plus_spy_volshock_q90":[],
      "G_D_plus_cross_section_rs_top50":[],
      "H_D_long_plus_bearish_short":[]
    }
    audit=[]
    for t in trades:
        st=state_for(t["symbol"],dailies,t["entry_t"])
        if st is None: continue

        is_d=(t["direction"]=="LONG" and st["bull_regime"] and st["rs_vs_spy_long"])
        is_h_short=(t["direction"]=="SHORT" and st["bear_regime"] and st["rs_vs_spy_short"])

        if is_d:
            variants["D_long_spy_regime_rs20"].append(t)
            variants["H_D_long_plus_bearish_short"].append(t)
            if st["breadth_ok"]: variants["E_D_plus_breadth50"].append(t)
            if st["vol_ok"] is True: variants["F_D_plus_spy_volshock_q90"].append(t)
            if st["rs_top_half"] is True: variants["G_D_plus_cross_section_rs_top50"].append(t)
        elif is_h_short:
            variants["H_D_long_plus_bearish_short"].append(t)

        if is_d or is_h_short:
            audit.append({"symbol":t["symbol"],"direction":t["direction"],"entry_t":t["entry_t"],
                          "r":t["r"],"state":st})

    definitions={
      "D_long_spy_regime_rs20":"LONG + prior completed SPY daily bull regime (>=2/3 close>EMA50, EMA20>EMA50, 20d return>0) + stock 20d return >= SPY 20d return",
      "E_D_plus_breadth50":"D + >=50% of available universe closes above EMA50 on latest completed daily bars",
      "F_D_plus_spy_volshock_q90":"D + completed SPY ATR14/close <= 90th percentile of preceding 252 completed SPY sessions",
      "G_D_plus_cross_section_rs_top50":"D + stock 20d return >= cross-sectional median 20d return of available universe at prior close",
      "H_D_long_plus_bearish_short":"D longs + SHORT only when prior completed SPY bear regime (>=2/3 close<EMA50, EMA20<EMA50, 20d return<0) and stock 20d return <= SPY 20d return"
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps({
      "eval_start":EVAL_START.isoformat(),"eval_end_exclusive":EVAL_END.isoformat(),
      "warmup_start":WARMUP_START.isoformat(),"months_loaded":months,
      "definitions":definitions,"errors":errors,"variants":variants,"audit":audit
    },ensure_ascii=False,indent=2),encoding="utf-8")
    print("FINAL",json.dumps({k:len(v) for k,v in variants.items()}),flush=True)

if __name__=="__main__":main()
