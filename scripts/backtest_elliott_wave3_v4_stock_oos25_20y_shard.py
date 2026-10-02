import json, os, statistics, time
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import datetime, time as dtime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

import backtest_elliott_wave3_v0_crypto as core
import backtest_elliott_wave3_v3_bbreak as v3

UTC=timezone.utc
NY=ZoneInfo("America/New_York")
HF_BASE="https://huggingface.co/datasets/mito0o852/OHLCV-1m/resolve/main/data"

TRADE_SYMS=(
"BAC","GS","MS","XOM","CVX","JNJ","PFE","MRK","ABBV","KO",
"PEP","MCD","SBUX","NKE","BA","GE","RTX","LMT","UPS","FDX",
"LOW","TGT","BKNG","ADBE","QCOM"
)
SOURCE_SYMS=tuple(sorted(set(TRADE_SYMS+("SPY","PCLN"))))
NOT_BEFORE={"RTX":datetime(2020,4,3,tzinfo=UTC)}

FEE_BPS=4.0
SLIP_BPS=2.0
ENTRY_VALID_SIGNAL_BARS=12
MAX_HOLD_SIGNAL_BARS=48
TP1_FRAC=0.50
SPLIT_FACTORS=(1.5,2,3,4,5,7,10,15,20)

def parse_date(s): return datetime.strptime(s,"%Y-%m-%d").replace(tzinfo=UTC)
EVAL_START=parse_date(os.environ["EVAL_START"])
EVAL_END=parse_date(os.environ["EVAL_END"])
WARMUP_START=EVAL_START-timedelta(days=400)
DATA_END=min(parse_date(os.environ.get("DATA_END","2026-04-01")),EVAL_END+timedelta(days=45))
OUT=Path(os.environ["OUT"])

def month_iter(start,end):
    y,m=start.year,start.month
    stop=(end.year,end.month)
    while (y,m)<=stop:
        yield y,m
        m+=1
        if m==13:y,m=y+1,1

def canonical(ticker,et):
    d=et.date()
    if ticker=="PCLN":
        return "BKNG" if d<datetime(2018,2,27).date() else None
    if ticker=="BKNG":
        return "BKNG" if d>=datetime(2018,2,27).date() else None
    return ticker if ticker in set(TRADE_SYMS+("SPY",)) else None

def remote_15m(con,y,m):
    url=f"{HF_BASE}/ohlcv_{y:04d}-{m:02d}.parquet"
    ph=",".join(["?"]*len(SOURCE_SYMS))
    q=f"""
    WITH src AS (
      SELECT ticker,timezone('America/New_York',timestamp) et,
             open,high,low,"close",volume
      FROM read_parquet('{url}')
      WHERE ticker IN ({ph})
    ),rth AS (
      SELECT * FROM src
      WHERE cast(et as time)>=time '09:30:00'
        AND cast(et as time)<time '16:00:00'
    ),agg AS (
      SELECT ticker,time_bucket(interval '15 minutes',et) b,
             arg_min(open,et) o,max(high) h,min(low) l,arg_max("close",et) c,sum(volume) v
      FROM rth GROUP BY ticker,b
    )
    SELECT ticker,b,o,h,l,c,v FROM agg ORDER BY ticker,b
    """
    rows=con.execute(q,list(SOURCE_SYMS)).fetchall()
    print("MONTH",f"{y:04d}-{m:02d}","rows",len(rows),flush=True)
    return rows

def collect():
    con=duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    by={s:[] for s in TRADE_SYMS+("SPY",)}
    missing=[]; months=0
    for y,m in month_iter(WARMUP_START,DATA_END-timedelta(days=1)):
        rows=None
        for a in range(7):
            try:
                rows=remote_15m(con,y,m); break
            except Exception as e:
                print("MONTH_RETRY",y,m,a+1,repr(e),flush=True)
                time.sleep(min(45,5*(a+1)))
        if rows is None:
            missing.append(f"{y:04d}-{m:02d}"); continue
        months+=1
        for ticker,et,o,h,l,c,v in rows:
            if et.tzinfo is None: et=et.replace(tzinfo=NY)
            else: et=et.astimezone(NY)
            canon=canonical(str(ticker),et)
            if canon is None: continue
            utc=et.astimezone(UTC)
            nb=NOT_BEFORE.get(canon)
            if nb and utc<nb: continue
            if utc<WARMUP_START or utc>=DATA_END: continue
            t=int(utc.timestamp()*1000)
            by[canon].append({"t":t,"ct":t+15*60_000,"o":float(o),"h":float(h),"l":float(l),"c":float(c),"v":float(v or 0)})
    con.close()
    for s in by: by[s].sort(key=lambda z:z["t"])
    return by,months,missing

def day_key(z):
    return datetime.fromtimestamp(z["t"]/1000,UTC).astimezone(NY).date()

def detect_splits(bars):
    by=defaultdict(list)
    for z in bars: by[day_key(z)].append(z)
    days=sorted(by); ev=[]
    for i in range(1,len(days)):
        if (days[i]-days[i-1]).days>14: continue
        prev=by[days[i-1]][-1]["c"]; op=by[days[i]][0]["o"]
        if prev<=0 or op<=0: continue
        ratio=prev/op; mag=ratio if ratio>=1 else 1/ratio
        if mag<1.35: continue
        f=min(SPLIT_FACTORS,key=lambda q:abs(mag/q-1))
        if abs(mag/f-1)<=.06:
            ev.append({"date":str(days[i]),"price_mult_before":1/f if ratio>1 else f,"factor":f})
    return ev

def apply_splits(bars,ev):
    if not ev:return [dict(x) for x in bars]
    parsed=[(datetime.fromisoformat(e["date"]).date(),e["price_mult_before"]) for e in ev]
    out=[]
    for z in bars:
        d=day_key(z); pm=1.0
        for sd,p in parsed:
            if d<sd:pm*=p
        q=dict(z)
        for k in ("o","h","l","c"):q[k]*=pm
        out.append(q)
    return out

def aggregate_1h(b15):
    by=defaultdict(list)
    for b in b15:
        dt=datetime.fromtimestamp(b["t"]/1000,UTC).astimezone(NY)
        if dtime(9,30)<=dt.time()<dtime(16,0): by[dt.date()].append(b)
    out=[]
    for d in sorted(by):
        xs=sorted(by[d],key=lambda z:z["t"])
        for k in range(0,24,4):
            part=xs[k:k+4]
            if len(part)!=4:continue
            if part[-1]["ct"]-part[0]["t"]!=60*60_000:continue
            out.append({"t":part[0]["t"],"ct":part[-1]["ct"],"o":part[0]["o"],
                        "h":max(x["h"] for x in part),"l":min(x["l"] for x in part),
                        "c":part[-1]["c"],"v":sum(x["v"] for x in part)})
    return out

def aggregate_daily(b15):
    by=defaultdict(list)
    for b in b15: by[day_key(b)].append(b)
    out=[]
    for d in sorted(by):
        xs=sorted(by[d],key=lambda z:z["t"])
        if len(xs)<24:continue
        out.append({"t":xs[0]["t"],"ct":xs[-1]["ct"],"o":xs[0]["o"],
                    "h":max(x["h"] for x in xs),"l":min(x["l"] for x in xs),
                    "c":xs[-1]["c"],"v":sum(x["v"] for x in xs)})
    return out

def add_spy_regime(spy15):
    d=aggregate_daily(spy15)
    if not d:return [],[]
    k=2/(200+1); e=None; emas=[]
    for x in d:
        e=x["c"] if e is None else e+k*(x["c"]-e)
        emas.append(e)
    times=[]; regs=[]
    for i,x in enumerate(d):
        if i<20:
            reg="UNKNOWN"
        else:
            slope=emas[i]-emas[i-20]
            if x["c"]>emas[i] and slope>0: reg="BULL"
            elif x["c"]<emas[i] and slope<0: reg="BEAR"
            else: reg="MIXED"
        times.append(x["ct"]); regs.append(reg)
    return times,regs

def regime_at(t,times,regs):
    i=bisect_right(times,t-1)-1
    return regs[i] if i>=0 else "UNKNOWN"

def signal_expiry(d,ki,n): return d[min(ki+n,len(d)-1)]["ct"]

def hold_expiry(d,fill_t,n):
    closes=[x["ct"] for x in d]
    i=bisect_left(closes,fill_t)
    return d[min(i+n,len(d)-1)]["ct"]

def simulate(sym,b15,reg_times,reg_vals):
    d=core.enrich_atr(aggregate_1h(b15))
    ps=core.zigzag(d); t15=[x["t"] for x in b15]
    lo=int(EVAL_START.timestamp()*1000); hi=int(EVAL_END.timestamp()*1000)
    by_known=defaultdict(list)
    for k in range(8,len(ps)):
        sig=v3.make_v3_signal(d,ps[k-8:k+1])
        if sig and sig["side"]=="LONG": by_known[sig["known_i"]].append(sig)
    trades=[]; st=defaultdict(int); busy_until=-1
    for ki in sorted(by_known):
        activation=d[ki]["ct"]
        if not(lo<=activation<hi):continue
        if activation<busy_until:st["signal_while_busy"]+=1;continue
        sig=by_known[ki][-1];st["patterns"]+=1
        entry,sl,tp1,tp2,risk=sig["entry"],sig["sl"],sig["tp1"],sig["tp2"],sig["risk"]
        start=bisect_left(t15,activation);valid_until=signal_expiry(d,ki,ENTRY_VALID_SIGNAL_BARS)
        fill_i=None;fill=None;cancelled=False
        for j in range(start,len(b15)):
            b=b15[j]
            if b["t"]>=hi or b["t"]>=valid_until:break
            if b["o"]>=entry:fill_i,fill=j,b["o"];break
            if b["l"]<=sl:cancelled=True;break
            if b["h"]>=entry:fill_i,fill=j,entry;break
        if fill_i is None:
            st["cancelled_before_entry" if cancelled else "entry_expired"]+=1
            busy_until=valid_until;continue
        st["filled"]+=1
        pnl=-core.cost(fill);rem=1.;stop=sl;hit1=hit2=False
        exit_t=b15[fill_i]["ct"];reason="TIME";last_i=fill_i
        hold_until=hold_expiry(d,b15[fill_i]["t"],MAX_HOLD_SIGNAL_BARS)
        for j in range(fill_i,len(b15)):
            b=b15[j]
            if b["t"]>=hi or b["t"]>=hold_until:break
            last_i=j
            if b["o"]<=stop:
                pnl+=rem*(b["o"]-fill)-core.cost(b["o"],rem);rem=0;exit_t=b["ct"];reason="GAP_STOP";break
            if b["l"]<=stop:
                pnl+=rem*(stop-fill)-core.cost(stop,rem);rem=0;exit_t=b["ct"];reason="STOP";break
            if not hit1:
                px=b["o"] if b["o"]>=tp1 else (tp1 if b["h"]>=tp1 else None)
                if px is not None:
                    f=min(TP1_FRAC,rem);pnl+=f*(px-fill)-core.cost(px,f);rem-=f;hit1=True;stop=max(stop,fill)
                    if rem>0 and b["l"]<=stop:
                        pnl+=rem*(stop-fill)-core.cost(stop,rem);rem=0;exit_t=b["ct"];reason="BE_AFTER_TP1";break
            if rem>0 and hit1 and (b["o"]>=tp2 or b["h"]>=tp2):
                px=b["o"] if b["o"]>=tp2 else tp2
                pnl+=rem*(px-fill)-core.cost(px,rem);rem=0;hit2=True;exit_t=b["ct"];reason="TP2";break
        if rem>0:
            b=b15[last_i];px=b["c"];pnl+=rem*(px-fill)-core.cost(px,rem);exit_t=b["ct"];reason="TIME"
        trades.append({"symbol":sym,"direction":"LONG","timeframe":"1H_RTH","signal_t":activation,
            "entry_t":b15[fill_i]["t"],"exit_t":exit_t,"entry":entry,"fill":fill,"initial_sl":sl,
            "tp1":tp1,"tp2":tp2,"risk":risk,"r":pnl/risk,"reason":reason,"tp1_hit":hit1,"tp2_hit":hit2,
            "regime":regime_at(activation,reg_times,reg_vals),
            "wave2_retracement":sig.get("wave2_retracement"),"abc_b_retracement":sig.get("abc_b_retracement"),
            "abc_c_to_a":sig.get("abc_c_to_a"),"impulse_atr":sig.get("impulse_atr"),"risk_atr":sig.get("risk_atr")})
        busy_until=exit_t
    st=dict(st);st["signal_bars"]=len(d);st["pivots"]=len(ps)
    return trades,st

def metrics(ts):
    o=sorted(ts,key=lambda z:(z["exit_t"],z["symbol"]));rs=[x["r"] for x in o]
    pos=[r for r in rs if r>0];neg=[r for r in rs if r<0]
    eq=peak=0.;dd=0.;cur=mx=0
    for r in rs:
        eq+=r;peak=max(peak,eq);dd=min(dd,eq-peak)
        if r<0:cur+=1;mx=max(mx,cur)
        else:cur=0
    return {"trades":len(o),"win_rate":len(pos)/len(o) if o else None,"total_r":sum(rs),
        "avg_r":statistics.fmean(rs) if rs else None,"profit_factor":sum(pos)/abs(sum(neg)) if neg else None,
        "max_drawdown_r":dd,"max_losing_streak":mx,
        "tp1_hit_rate":sum(t["tp1_hit"] for t in o)/len(o) if o else None,
        "tp2_hit_rate":sum(t["tp2_hit"] for t in o)/len(o) if o else None}

def main():
    by,months,missing=collect()
    if missing:raise RuntimeError("missing months="+",".join(missing))
    spy=apply_splits(by["SPY"],detect_splits(by["SPY"]))
    reg_times,reg_vals=add_spy_regime(spy)
    alltr=[];cells={};errors={}
    for sym in TRADE_SYMS:
        try:
            raw=by[sym]
            if len(raw)<500:raise RuntimeError(f"insufficient bars {len(raw)}")
            ev=detect_splits(raw);bars=apply_splits(raw,ev)
            ts,st=simulate(sym,bars,reg_times,reg_vals)
            alltr+=ts;cells[sym]={"metrics":metrics(ts),"stats":st,"split_adjustments":ev,"bars15":len(bars)}
            print("RESULT",sym,json.dumps(cells[sym]),flush=True)
        except Exception as e:
            errors[sym]=repr(e);print("ERROR",sym,repr(e),flush=True)
    byreg=defaultdict(list)
    for t in alltr:byreg[t["regime"]].append(t)
    report={"strategy":"Elliott Wave 3 v4 frozen — OOS25 RTH 1H LONG 20Y shard",
      "shard":{"eval_start":EVAL_START.isoformat(),"eval_end_exclusive":EVAL_END.isoformat(),
               "warmup_start":WARMUP_START.isoformat(),"data_end":DATA_END.isoformat()},
      "symbols":list(TRADE_SYMS),"months_loaded":months,"missing_months":missing,
      "summary":metrics(alltr),"regimes":{k:metrics(v) for k,v in sorted(byreg.items())},
      "errors":errors,"symbols_detail":cells,"trades":alltr}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print("FINAL",json.dumps({"summary":report["summary"],"regimes":report["regimes"],"errors":errors},indent=2),flush=True)

if __name__=="__main__":main()
