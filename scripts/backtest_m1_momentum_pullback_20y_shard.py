import json, math, os, sys, time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import duckdb

sys.path.insert(0,str(Path(__file__).parent))
import wyckoff_status as w

UTC=timezone.utc
NY=ZoneInfo("America/New_York")
HF_BASE="https://huggingface.co/datasets/mito0o852/OHLCV-1m/resolve/main/data"

SYMS=(
"AAPL","AMZN","AVGO","CRCL","DELL","MSFT","MU","SNDK","SNXX","SOXL","SPCX",
"AMD","BABA","INTC","JPM","KORU","MSTR","NFLX","SKHY","SMCI","SOXS","V",
"COST","GOOGL","LLY","META","NBIS","NVDA","QQQ","TSLA","UBER","WMT",
"AMAT","CAT","DRAM","EWY","HD","MRVL","MUU","ORCL","SPY","TSM",
"AAOI","AXTI","BE","COIN","CRM","CSCO","DIS","HOOD","IBM","LITE","TQQQ"
)
SOURCE=tuple(sorted(set(SYMS+("FB","GOOG"))))
NOT_BEFORE={
  "DELL":datetime(2018,12,28,tzinfo=UTC),
  "SNDK":datetime(2025,2,24,tzinfo=UTC),
}
FEE_BPS=4.0
SLIPPAGE_BPS=2.0

def pd(s):return datetime.strptime(s,"%Y-%m-%d").replace(tzinfo=UTC)
EVAL_START=pd(os.environ["EVAL_START"])
EVAL_END=pd(os.environ["EVAL_END"])
DATA_END=min(pd(os.environ.get("DATA_END","2026-04-01")),EVAL_END+timedelta(days=120))
WARMUP_START=EVAL_START-timedelta(days=420)
OUT=Path(os.environ["OUT"])

# M1 v1 locked before test:
# - long only
# - prior completed SPY close > EMA200
# - stock 60d return in top 20% cross-section and > 0
# - stock close > EMA50 > EMA200
# - one of prior 5 sessions low <= EMA20, while minimum close over those sessions > EMA50
# - signal day closes > EMA20, > prior close, CLV >= .60
# - buy stop = signal-day high, valid next 3 sessions
# - initial stop = min low of prior 5 incl signal - .25*ATR14
# - reject if initial risk > 15% or < .5%
# - trailing stop = max(old stop, highest completed daily close since entry - 3*ATR14)
# - time exit at 60 completed sessions
TOP_FRAC=.20
ENTRY_VALID_DAYS=3
TRAIL_ATR=3.0
STOP_ATR_PAD=.25
MAX_HOLD_DAYS=60
MIN_RISK_PCT=.005
MAX_RISK_PCT=.15

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

def remote15(con,y,m):
    url=f"{HF_BASE}/ohlcv_{y:04d}-{m:02d}.parquet"
    ph=",".join(["?"]*len(SOURCE))
    q=f"""
    WITH src AS (
      SELECT ticker,timezone('America/New_York',timestamp) et,open,high,low,"close",volume
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
    con=duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    by={s:[] for s in SYMS};missing=[];months=0
    for y,m in month_iter(WARMUP_START,DATA_END-timedelta(days=1)):
        rows=None
        for a in range(6):
            try:
                t0=time.time();rows=remote15(con,y,m)
                print("MONTH",f"{y:04d}-{m:02d}",len(rows),round(time.time()-t0,2),flush=True)
                break
            except Exception as e:
                print("RETRY",y,m,a+1,repr(e),flush=True)
                time.sleep(min(30,4*(a+1)))
        if rows is None:
            missing.append(f"{y:04d}-{m:02d}");continue
        months+=1
        for ticker,et,o,h,l,c,v in rows:
            if et.tzinfo is None:et=et.replace(tzinfo=NY)
            else:et=et.astimezone(NY)
            sym=canonical(str(ticker),et.date())
            if not sym:continue
            utc=et.astimezone(UTC)
            nb=NOT_BEFORE.get(sym)
            if nb and utc<nb:continue
            if utc<WARMUP_START or utc>=DATA_END:continue
            tms=int(utc.timestamp()*1000)
            by[sym].append({"t":tms,"o":float(o),"h":float(h),"l":float(l),"c":float(c),
                            "v":float(v or 0),"ct":tms+15*60*1000-1})
    con.close()
    if missing:raise RuntimeError("missing months="+",".join(missing))
    for s in by:by[s].sort(key=lambda z:z["t"])
    return by,months

def day_key(z):
    return datetime.fromtimestamp(z["t"]/1000,UTC).astimezone(NY).date()

def detect_splits(bars):
    byday=defaultdict(list)
    for z in bars:byday[day_key(z)].append(z)
    days=sorted(byday);common=(2,3,4,5,7,10,15,20);ev=[]
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
    if not ev:return bars
    out=[]
    for z in bars:
        d=day_key(z);pm=vm=1.0
        for sd,p,v in ev:
            if d<sd:pm*=p;vm*=v
        q=z.copy()
        for k in ("o","h","l","c"):q[k]*=pm
        q["v"]*=vm;out.append(q)
    return out

def aggregate_daily(bars):
    g=defaultdict(list)
    for z in bars:g[day_key(z)].append(z)
    out=[]
    for d,a in sorted(g.items()):
        a.sort(key=lambda x:x["t"])
        out.append({"date":str(d),"t":a[0]["t"],"o":a[0]["o"],"h":max(x["h"] for x in a),
                    "l":min(x["l"] for x in a),"c":a[-1]["c"],"v":sum(x["v"] for x in a),
                    "ct":a[-1]["ct"]})
    return out

def ema(vals,n):
    k=2/(n+1);out=[];e=None
    for x in vals:
        e=x if e is None else e+k*(x-e);out.append(e)
    return out

def enrich_daily(D):
    if not D:return D
    cs=[x["c"] for x in D]
    e20=ema(cs,20);e50=ema(cs,50);e200=ema(cs,200)
    tr=[];atr=[];a=None
    for i,x in enumerate(D):
        prev=cs[i-1] if i else x["c"]
        t=max(x["h"]-x["l"],abs(x["h"]-prev),abs(x["l"]-prev));tr.append(t)
        a=t if a is None else ((a*13)+t)/14
        atr.append(a)
    for i,x in enumerate(D):
        x["ema20"]=e20[i];x["ema50"]=e50[i];x["ema200"]=e200[i];x["atr14"]=atr[i]
        x["ret60"]=x["c"]/D[i-60]["c"]-1 if i>=60 and D[i-60]["c"]>0 else None
        rng=x["h"]-x["l"];x["clv"]=(x["c"]-x["l"])/rng if rng>0 else .5
    return D

def build_indices(dailies):
    # date -> symbol -> daily index
    bydate=defaultdict(dict)
    for s,D in dailies.items():
        for i,x in enumerate(D):bydate[x["date"]][s]=i
    return bydate

def make_signals(dailies):
    bydate=build_indices(dailies)
    sigs=[]
    for ds,m in sorted(bydate.items()):
        # Only signals whose completed day lies before shard end and not before eval start.
        day=datetime.fromisoformat(ds).replace(tzinfo=UTC)
        if day<EVAL_START or day>=EVAL_END:continue
        spy_i=m.get("SPY")
        if spy_i is None:continue
        spy=dailies["SPY"][spy_i]
        if spy_i<200 or not (spy["c"]>spy["ema200"]):continue

        eligible=[]
        for s,i in m.items():
            D=dailies[s]
            if i<200:continue
            x=D[i]
            if x["ret60"] is None:continue
            eligible.append((s,x["ret60"]))
        if len(eligible)<10:continue
        eligible.sort(key=lambda z:z[1],reverse=True)
        k=max(1,math.ceil(len(eligible)*TOP_FRAC))
        top=set(s for s,_ in eligible[:k])

        for s in top:
            if s=="SOXS":continue
            i=m[s];D=dailies[s]
            if i<200 or i<5:continue
            x=D[i];prev=D[i-1]
            if x["ret60"] is None or x["ret60"]<=0:continue
            if not (x["c"]>x["ema50"]>x["ema200"]):continue
            win=D[i-4:i+1]
            if not any(z["l"]<=z["ema20"] for z in win):continue
            if not all(z["c"]>z["ema50"] for z in win):continue
            if not (x["c"]>x["ema20"] and x["c"]>prev["c"] and x["clv"]>=.60):continue
            entry=x["h"]
            stop=min(z["l"] for z in win)-STOP_ATR_PAD*x["atr14"]
            if stop<=0 or entry<=stop:continue
            risk_pct=(entry-stop)/entry
            if risk_pct<MIN_RISK_PCT or risk_pct>MAX_RISK_PCT:continue
            sigs.append({"symbol":s,"signal_date":ds,"signal_i":i,"signal_t":x["ct"],
                         "entry_stop":entry,"initial_stop":stop,"risk_pct":risk_pct,
                         "ret60":x["ret60"],"rank_n":len(eligible),"rank_top_k":k})
    return sigs

def session_map(bars):
    g=defaultdict(list)
    for z in bars:g[day_key(z)].append(z)
    for d in g:g[d].sort(key=lambda x:x["t"])
    return g

def simulate_symbol(sym,D,bars,signals):
    sessions=session_map(bars)
    dates=[datetime.fromisoformat(x["date"]).date() for x in D]
    date_to_i={d:i for i,d in enumerate(dates)}
    trades=[];busy_until=None
    for sig in sorted(signals,key=lambda x:x["signal_t"]):
        sd=datetime.fromisoformat(sig["signal_date"]).date()
        if busy_until is not None and sd<=busy_until:continue
        si=date_to_i.get(sd)
        if si is None:continue
        entry_px=sig["entry_stop"];istop=sig["initial_stop"]
        fill=None;fill_day_i=None;fill_bar=None
        for di in range(si+1,min(len(D),si+1+ENTRY_VALID_DAYS)):
            d=dates[di]
            for bar in sessions.get(d,[]):
                if bar["o"]>=entry_px:
                    px=bar["o"]*(1+SLIPPAGE_BPS/10000)
                    fill=(bar["t"],px);fill_day_i=di;fill_bar=bar;break
                if bar["h"]>=entry_px:
                    px=entry_px*(1+SLIPPAGE_BPS/10000)
                    fill=(bar["t"],px);fill_day_i=di;fill_bar=bar;break
            if fill:break
            if D[di]["c"]<D[di]["ema50"]:break
        if not fill:continue

        entry_t,entry_fill=fill
        initial_risk=entry_fill-istop
        if initial_risk<=0:continue
        stop=istop
        highest_close=D[fill_day_i-1]["c"] if fill_day_i>0 else entry_fill
        hold_days=0;exit_t=None;exit_fill=None;reason=None

        # Process entry day from fill bar onward, then subsequent sessions.
        for di in range(fill_day_i,min(len(D),fill_day_i+MAX_HOLD_DAYS+5)):
            d=dates[di];daybars=sessions.get(d,[])
            started=False
            for bar in daybars:
                if di==fill_day_i and not started:
                    if bar["t"]<entry_t:continue
                    started=True
                if bar["l"]<=stop:
                    raw=bar["o"] if bar["o"]<stop else stop
                    exit_fill=raw*(1-SLIPPAGE_BPS/10000)
                    exit_t=bar["t"];reason="STOP";break
            if exit_t is not None:break

            hold_days+=1
            highest_close=max(highest_close,D[di]["c"])
            # Update trailing stop only after the completed session.
            stop=max(stop,highest_close-TRAIL_ATR*D[di]["atr14"])

            if hold_days>=MAX_HOLD_DAYS:
                exit_fill=D[di]["c"]*(1-SLIPPAGE_BPS/10000)
                exit_t=D[di]["ct"];reason="TIME";break

        if exit_t is None:
            continue
        fee_entry=entry_fill*FEE_BPS/10000
        fee_exit=exit_fill*FEE_BPS/10000
        pnl_per_share=(exit_fill-entry_fill)-fee_entry-fee_exit
        r=pnl_per_share/initial_risk
        trades.append({
          "symbol":sym,"direction":"LONG","signal_t":sig["signal_t"],"entry_t":entry_t,"exit_t":exit_t,
          "entry":entry_fill,"initial_stop":istop,"exit":exit_fill,"reason":reason,
          "initial_risk":initial_risk,"r":r,"pnl":r*400.0,
          "signal_ret60":sig["ret60"],"signal_risk_pct":sig["risk_pct"],
          "hold_days":hold_days
        })
        busy_until=datetime.fromtimestamp(exit_t/1000,UTC).astimezone(NY).date()
    return trades

def stats(ts):
    n=len(ts);w=sum(t["r"]>0 for t in ts);l=sum(t["r"]<0 for t in ts)
    net=sum(t["r"] for t in ts);gp=sum(t["r"] for t in ts if t["r"]>0);gl=sum(t["r"] for t in ts if t["r"]<0)
    return {"closed":n,"wins":w,"losses":l,"win_rate":w/n if n else None,
            "net_r":net,"avg_r":net/n if n else None,"profit_factor":gp/abs(gl) if gl<0 else None}

def main():
    by,months=collect()
    dailies={};adj={}
    for s,bars in by.items():
        if not bars:continue
        a=apply_splits(bars,detect_splits(bars));adj[s]=a
        D=enrich_daily(aggregate_daily(a))
        if D:dailies[s]=D
    signals=make_signals(dailies)
    bysig=defaultdict(list)
    for s in signals:bysig[s["symbol"]].append(s)
    trades=[]
    for sym,sigs in bysig.items():
        ts=simulate_symbol(sym,dailies[sym],adj[sym],sigs)
        trades.extend(ts)
        print("RESULT",sym,"signals",len(sigs),"trades",len(ts),"R",round(sum(x["r"] for x in ts),4),flush=True)
    lo=int(EVAL_START.timestamp()*1000);hi=int(EVAL_END.timestamp()*1000)
    trades=[t for t in trades if lo<=t["entry_t"]<hi]
    trades.sort(key=lambda x:(x["entry_t"],x["symbol"]))
    report={
      "generated_at":datetime.now(UTC).isoformat(),
      "strategy":"M1_v1_cross_section_momentum_pullback",
      "locked_rules":{
        "market":"SPY prior completed close > EMA200",
        "selection":"60d return top 20% cross-section and >0",
        "trend":"close > EMA50 > EMA200",
        "pullback":"within prior 5 completed sessions at least one low <= EMA20 and closes remain above EMA50",
        "trigger":"signal close > EMA20, > prior close, CLV>=0.60",
        "entry":"buy stop at signal-day high, valid 3 sessions",
        "initial_stop":"5-session low - 0.25*ATR14",
        "risk_filter":"0.5% <= entry-stop distance <=15%",
        "exit":"3*ATR14 trailing stop using completed daily closes; 60-session time stop",
        "costs":{"fee_bps_each_side":FEE_BPS,"slippage_bps_each_side":SLIPPAGE_BPS}
      },
      "shard":{"eval_start":EVAL_START.isoformat(),"eval_end_exclusive":EVAL_END.isoformat(),
               "warmup_start":WARMUP_START.isoformat(),"data_end":DATA_END.isoformat()},
      "months_loaded":months,"signals":len(signals),"totals":stats(trades),"trades":trades
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("FINAL",json.dumps({"signals":len(signals),"totals":report["totals"]}),flush=True)

if __name__=="__main__":main()
