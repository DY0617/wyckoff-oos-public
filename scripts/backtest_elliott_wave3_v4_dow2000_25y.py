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
OUT=ROOT/"data/validation/elliott_wave3_v4_dow2000_1h_long_25y.json"
UTC=timezone.utc
NY=ZoneInfo("America/New_York")

DOW2000=("MMM","AA","MO","AXP","BA","CAT","C","KO","DD","EK","XOM","GE","GM","HPQ",
         "HD","HON","INTC","IBM","IP","JNJ","JPM","MCD","MRK","MSFT","PG","SBC","UTX",
         "WMT","DIS","T")

EVAL_START=datetime(2000,1,1,tzinfo=UTC)
EVAL_END=datetime(2026,1,1,tzinfo=UTC)
ENTRY_VALID_SIGNAL_BARS=12
MAX_HOLD_SIGNAL_BARS=48
TP1_FRAC=0.50
SPLIT_FACTORS=(1.5,2,3,4,5,7,10,15,20)


def load_all():
    files=sorted(DATA_DIR.glob("us30x2_15m_*.parquet"))
    if len(files)!=6:
        raise RuntimeError(f"expected 6 chunk parquets, got {len(files)}")
    frames=[pd.read_parquet(p) for p in files]
    df=pd.concat(frames,ignore_index=True)
    df=df.drop_duplicates(["ticker","t"]).sort_values(["ticker","t"]).reset_index(drop=True)
    keep=set(DOW2000+("SPY",))
    df=df[df["ticker"].isin(keep)]
    out={}
    for sym in DOW2000+("SPY",):
        g=df[df.ticker==sym]
        out[sym]=[
            {"t":int(r.t),"ct":int(r.t)+15*60_000,
             "o":float(r.o),"h":float(r.h),"l":float(r.l),"c":float(r.c),"v":float(r.v or 0)}
            for r in g.itertuples(index=False)
        ]
    return out,[p.name for p in files]


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
        if abs(mag/f-1)<=0.06:
            ev.append({
                "date":str(days[i]),"factor":f,
                "price_mult_before":1/f if ratio>1 else f,
                "raw_prevclose_open_ratio":ratio
            })
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
        if dtime(9,30)<=dt.time()<dtime(16,0):by[dt.date()].append(b)
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
    for b in b15:by[day_key(b)].append(b)
    out=[]
    for d in sorted(by):
        xs=sorted(by[d],key=lambda z:z["t"])
        if len(xs)<24:continue
        out.append({"t":xs[0]["t"],"ct":xs[-1]["ct"],"o":xs[0]["o"],
                    "h":max(x["h"] for x in xs),"l":min(x["l"] for x in xs),
                    "c":xs[-1]["c"],"v":sum(x["v"] for x in xs)})
    return out


def build_regime(spy):
    d=aggregate_daily(spy)
    k=2/(200+1); e=None; emas=[];times=[];regs=[]
    for x in d:
        e=x["c"] if e is None else e+k*(x["c"]-e)
        emas.append(e)
    for i,x in enumerate(d):
        if i<20:reg="UNKNOWN"
        else:
            slope=emas[i]-emas[i-20]
            if x["c"]>emas[i] and slope>0:reg="BULL"
            elif x["c"]<emas[i] and slope<0:reg="BEAR"
            else:reg="MIXED"
        times.append(x["ct"]);regs.append(reg)
    return times,regs


def regime_at(t,times,regs):
    i=bisect_right(times,t-1)-1
    return regs[i] if i>=0 else "UNKNOWN"


def signal_expiry(d,ki,n):
    return d[min(ki+n,len(d)-1)]["ct"]


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
        if sig and sig["side"]=="LONG":
            by_known[sig["known_i"]].append(sig)

    trades=[];st=defaultdict(int);busy_until=-1
    for ki in sorted(by_known):
        activation=d[ki]["ct"]
        if not(lo<=activation<hi):continue
        if activation<busy_until:
            st["signal_while_busy"]+=1;continue

        sig=by_known[ki][-1];st["patterns"]+=1
        entry,sl,tp1,tp2,risk=sig["entry"],sig["sl"],sig["tp1"],sig["tp2"],sig["risk"]
        start=bisect_left(t15,activation)
        valid_until=signal_expiry(d,ki,ENTRY_VALID_SIGNAL_BARS)

        fill_i=None;fill=None;cancelled=False
        for j in range(start,len(b15)):
            b=b15[j]
            if b["t"]>=hi or b["t"]>=valid_until:break
            if b["o"]>=entry:
                fill_i,fill=j,b["o"];break
            if b["l"]<=sl:
                cancelled=True;break
            if b["h"]>=entry:
                fill_i,fill=j,entry;break

        if fill_i is None:
            st["cancelled_before_entry" if cancelled else "entry_expired"]+=1
            busy_until=valid_until;continue

        st["filled"]+=1
        pnl=-core.cost(fill);rem=1.0;stop=sl;hit1=hit2=False
        exit_t=b15[fill_i]["ct"];reason="TIME";last_i=fill_i
        hold_until=hold_expiry(d,b15[fill_i]["t"],MAX_HOLD_SIGNAL_BARS)

        for j in range(fill_i,len(b15)):
            b=b15[j]
            if b["t"]>=hi or b["t"]>=hold_until:break
            last_i=j
            if b["o"]<=stop:
                pnl+=rem*(b["o"]-fill)-core.cost(b["o"],rem)
                rem=0;exit_t=b["ct"];reason="GAP_STOP";break
            if b["l"]<=stop:
                pnl+=rem*(stop-fill)-core.cost(stop,rem)
                rem=0;exit_t=b["ct"];reason="STOP";break
            if not hit1:
                px=b["o"] if b["o"]>=tp1 else (tp1 if b["h"]>=tp1 else None)
                if px is not None:
                    f=min(TP1_FRAC,rem)
                    pnl+=f*(px-fill)-core.cost(px,f)
                    rem-=f;hit1=True;stop=max(stop,fill)
                    if rem>0 and b["l"]<=stop:
                        pnl+=rem*(stop-fill)-core.cost(stop,rem)
                        rem=0;exit_t=b["ct"];reason="BE_AFTER_TP1";break
            if rem>0 and hit1 and (b["o"]>=tp2 or b["h"]>=tp2):
                px=b["o"] if b["o"]>=tp2 else tp2
                pnl+=rem*(px-fill)-core.cost(px,rem)
                rem=0;hit2=True;exit_t=b["ct"];reason="TP2";break

        if rem>0:
            b=b15[last_i];px=b["c"]
            pnl+=rem*(px-fill)-core.cost(px,rem)
            exit_t=b["ct"];reason="TIME"

        trades.append({
            "symbol":sym,"timeframe":"1H_RTH","direction":"LONG",
            "signal_t":activation,"entry_t":b15[fill_i]["t"],"exit_t":exit_t,
            "entry":entry,"fill":fill,"initial_sl":sl,"tp1":tp1,"tp2":tp2,
            "risk":risk,"r":pnl/risk,"reason":reason,"tp1_hit":hit1,"tp2_hit":hit2,
            "regime":regime_at(activation,reg_times,reg_vals),
            "wave2_retracement":sig.get("wave2_retracement"),
            "abc_b_retracement":sig.get("abc_b_retracement"),
            "abc_c_to_a":sig.get("abc_c_to_a"),
            "impulse_atr":sig.get("impulse_atr"),
            "risk_atr":sig.get("risk_atr")
        })
        busy_until=exit_t

    st=dict(st);st["signal_bars"]=len(d);st["pivots"]=len(ps)
    return trades,st


def metrics(ts):
    o=sorted(ts,key=lambda z:(z["exit_t"],z["symbol"]))
    rs=[x["r"] for x in o];pos=[r for r in rs if r>0];neg=[r for r in rs if r<0]
    eq=peak=0.;dd=0.;cur=mx=0
    for r in rs:
        eq+=r;peak=max(peak,eq);dd=min(dd,eq-peak)
        if r<0:cur+=1;mx=max(mx,cur)
        else:cur=0
    return {"trades":len(o),"win_rate":len(pos)/len(o) if o else None,
            "total_r":sum(rs),"avg_r":statistics.fmean(rs) if rs else None,
            "profit_factor":sum(pos)/abs(sum(neg)) if neg else None,
            "max_drawdown_r":dd,"max_losing_streak":mx,
            "tp1_hit_rate":sum(t["tp1_hit"] for t in o)/len(o) if o else None,
            "tp2_hit_rate":sum(t["tp2_hit"] for t in o)/len(o) if o else None}


def grouped(ts,keyfn):
    d=defaultdict(list)
    for t in ts:d[str(keyfn(t))].append(t)
    return {k:metrics(v) for k,v in sorted(d.items())}


def main():
    by,files=load_all()
    spy=apply_splits(by["SPY"],detect_splits(by["SPY"]))
    reg_times,reg_vals=build_regime(spy)

    alltr=[];cells={};errors={}
    for sym in DOW2000:
        try:
            raw=by[sym]
            if len(raw)<500:raise RuntimeError(f"insufficient bars {len(raw)}")
            first=datetime.fromtimestamp(raw[0]["t"]/1000,UTC)
            last=datetime.fromtimestamp(raw[-1]["t"]/1000,UTC)
            ev=detect_splits(raw);bars=apply_splits(raw,ev)
            ts,st=simulate(sym,bars,reg_times,reg_vals)
            alltr+=ts
            cells[sym]={
                "coverage":{"first":first.isoformat(),"last":last.isoformat()},
                "metrics":metrics(ts),"stats":st,
                "split_adjustments":ev,"bars15":len(bars)
            }
            print("RESULT",sym,json.dumps(cells[sym]),flush=True)
        except Exception as e:
            errors[sym]=repr(e);print("ERROR",sym,repr(e),flush=True)

    byyear=grouped(alltr,lambda t:datetime.fromtimestamp(t["entry_t"]/1000,UTC).year)
    byreg=grouped(alltr,lambda t:t["regime"])
    bysym=grouped(alltr,lambda t:t["symbol"])

    rolling5={}
    for y in range(2000,2022):
        q=[t for t in alltr if y<=datetime.fromtimestamp(t["entry_t"]/1000,UTC).year<y+5]
        rolling5[f"{y}-{y+4}"]=metrics(q)

    out={
      "strategy":"Elliott Wave 3 v4 frozen — DJIA 2000 constituents RTH 1H LONG",
      "purpose":"Survivorship-bias-reduced cross-era OOS using the DJIA constituent universe frozen at 2000-01.",
      "period":{"start":EVAL_START.isoformat(),"end_exclusive":EVAL_END.isoformat()},
      "universe":list(DOW2000),
      "data":{
        "source":"existing US 30x2 15m chunks from HF OHLCV-1m",
        "chunk_files":files,
        "session":"US RTH 09:30-16:00 ET",
        "signal":"six complete 1H RTH bars 09:30-15:30; 15:30-16:00 execution-only",
        "survivorship_note":"Universe frozen to the DJIA roster in effect at 2000-01; later replacements are not added."
      },
      "rules":{
        "direction":"LONG only","entry":"exact v3 B-wave breakout after confirmed ABC C",
        "entry_validity_signal_bars":ENTRY_VALID_SIGNAL_BARS,
        "max_hold_signal_bars":MAX_HOLD_SIGNAL_BARS,
        "fee_bps":core.FEE_BPS,"slippage_bps":core.SLIP_BPS
      },
      "summary":metrics(alltr),
      "by_year":byyear,
      "by_regime":byreg,
      "by_symbol":bysym,
      "rolling_5y":rolling5,
      "breadth":{
        "symbols_requested":len(DOW2000),
        "symbols_with_trades":len(bysym),
        "positive_symbols":sum(v["total_r"]>0 for v in bysym.values()),
        "negative_symbols":sum(v["total_r"]<0 for v in bysym.values()),
        "symbols_with_errors":len(errors)
      },
      "symbols_detail":cells,
      "errors":errors,
      "limitations":[
        "Freezing the 2000 DJIA roster reduces survivorship bias versus using today's winners, but does not eliminate corporate-action/ticker-continuity bias.",
        "Extinct or renamed historical tickers are not stitched to later successor tickers except where the extraction source already normalizes a ticker; this can truncate some histories.",
        "This test is untouched with respect to symbol selection, but the strategy itself was developed on other crypto/stock samples."
      ],
      "trades":alltr
    }

    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2),encoding="utf-8")
    print("FINAL",json.dumps({k:v for k,v in out.items() if k not in ("trades","symbols_detail","by_symbol")},indent=2),flush=True)

if __name__=="__main__":
    main()
