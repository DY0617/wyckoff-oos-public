
import json, statistics
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import duckdb

import backtest_elliott_wave3_v0_crypto as core
import backtest_elliott_wave3_v3_bbreak as v3

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data/cache/elliott_stock_oos25_recent5y_15m.parquet"
OUT=ROOT/"data/validation/elliott_wave3_v4_stock_oos25_1h_long.json"
UTC=timezone.utc
NY=ZoneInfo("America/New_York")

SYMS=(
"BAC","GS","MS","XOM","CVX","JNJ","PFE","MRK","ABBV","KO",
"PEP","MCD","SBUX","NKE","BA","GE","RTX","LMT","UPS","FDX",
"LOW","TGT","BKNG","ADBE","QCOM"
)

EVAL_START=datetime(2021,4,1,tzinfo=UTC)
EVAL_END=datetime(2026,4,1,tzinfo=UTC)
ENTRY_VALID_SIGNAL_BARS=12
MAX_HOLD_SIGNAL_BARS=48
TP1_FRAC=0.50
SPLIT_FACTORS=(1.5,2,3,4,5,7,10,15,20)

def to_ms(ts):
    if ts.tzinfo is None: ts=ts.replace(tzinfo=NY)
    return int(ts.astimezone(UTC).timestamp()*1000)

def load_symbol(con,sym):
    rows=con.execute("""
        SELECT b,o,h,l,c,v FROM read_parquet(?) WHERE symbol=? ORDER BY b
    """,[str(DATA),sym]).fetchall()
    out=[]
    for ts,o,h,l,c,v in rows:
        t=to_ms(ts)
        out.append({"t":t,"ct":t+15*60_000,"o":float(o),"h":float(h),"l":float(l),"c":float(c),"v":float(v or 0)})
    return out

def ny_date(ms):
    return datetime.fromtimestamp(ms/1000,UTC).astimezone(NY).date()

def detect_splits_15m(bars):
    by=defaultdict(list)
    for b in bars: by[ny_date(b["t"])].append(b)
    events=[]; prev=None
    for d in sorted(by):
        xs=sorted(by[d],key=lambda z:z["t"])
        if not xs: continue
        op=xs[0]["o"]
        if prev and prev>0 and op>0:
            ratio=prev/op
            mag=ratio if ratio>=1 else 1/ratio
            if mag>=1.35:
                f=min(SPLIT_FACTORS,key=lambda q:abs(mag/q-1))
                if abs(mag/f-1)<=0.05:
                    events.append((d,1/f if ratio>1 else f))
        prev=xs[-1]["c"]
    return events

def adjust_splits_15m(bars):
    ev=detect_splits_15m(bars)
    out=[]
    for b in bars:
        d=ny_date(b["t"]); pm=1.0
        for ed,m in ev:
            if d<ed: pm*=m
        q=dict(b)
        for k in ("o","h","l","c"): q[k]*=pm
        out.append(q)
    return out,[(str(d),m) for d,m in ev]

def aggregate_rth_1h(b15):
    by=defaultdict(list)
    for b in b15:
        dt=datetime.fromtimestamp(b["t"]/1000,UTC).astimezone(NY)
        if time(9,30)<=dt.time()<time(16,0): by[dt.date()].append(b)
    out=[]
    for d in sorted(by):
        xs=sorted(by[d],key=lambda z:z["t"])
        for k in range(0,24,4):
            part=xs[k:k+4]
            if len(part)!=4: continue
            if part[-1]["ct"]-part[0]["t"]!=60*60_000: continue
            out.append({"t":part[0]["t"],"ct":part[-1]["ct"],"o":part[0]["o"],
                        "h":max(x["h"] for x in part),"l":min(x["l"] for x in part),
                        "c":part[-1]["c"],"v":sum(x["v"] for x in part)})
    return out

def signal_expiry(d,ki,n):
    return d[min(ki+n,len(d)-1)]["ct"]

def hold_expiry(d,fill_t,n):
    closes=[x["ct"] for x in d]
    i=bisect_left(closes,fill_t)
    return d[min(i+n,len(d)-1)]["ct"]

def simulate(sym,b15):
    d=core.enrich_atr(aggregate_rth_1h(b15))
    ps=core.zigzag(d)
    t15=[x["t"] for x in b15]
    lo=int(EVAL_START.timestamp()*1000); hi=int(EVAL_END.timestamp()*1000)
    by_known=defaultdict(list)

    for k in range(8,len(ps)):
        sig=v3.make_v3_signal(d,ps[k-8:k+1])
        if sig and sig["side"]=="LONG":
            by_known[sig["known_i"]].append(sig)

    trades=[]; st=defaultdict(int); busy_until=-1
    for ki in sorted(by_known):
        activation=d[ki]["ct"]
        if not (lo<=activation<hi): continue
        if activation<busy_until:
            st["signal_while_busy"]+=1; continue
        sig=by_known[ki][-1]; st["patterns"]+=1
        entry,sl,tp1,tp2,risk=sig["entry"],sig["sl"],sig["tp1"],sig["tp2"],sig["risk"]

        start=bisect_left(t15,activation)
        valid_until=signal_expiry(d,ki,ENTRY_VALID_SIGNAL_BARS)
        fill_i=None; fill=None; cancelled=False
        for j in range(start,len(b15)):
            b=b15[j]
            if b["t"]>=hi or b["t"]>=valid_until: break
            if b["o"]>=entry:
                fill_i,fill=j,b["o"]; break
            if b["l"]<=sl:
                cancelled=True; break
            if b["h"]>=entry:
                fill_i,fill=j,entry; break

        if fill_i is None:
            st["cancelled_before_entry" if cancelled else "entry_expired"]+=1
            busy_until=valid_until; continue

        st["filled"]+=1
        pnl=-core.cost(fill); rem=1.0; stop=sl; hit1=hit2=False
        exit_t=b15[fill_i]["ct"]; reason="TIME"
        hold_until=hold_expiry(d,b15[fill_i]["t"],MAX_HOLD_SIGNAL_BARS)
        last_i=fill_i

        for j in range(fill_i,len(b15)):
            b=b15[j]
            if b["t"]>=hi or b["t"]>=hold_until: break
            last_i=j
            if b["o"]<=stop:
                pnl+=rem*(b["o"]-fill)-core.cost(b["o"],rem)
                rem=0; exit_t=b["ct"]; reason="GAP_STOP"; break
            if b["l"]<=stop:
                pnl+=rem*(stop-fill)-core.cost(stop,rem)
                rem=0; exit_t=b["ct"]; reason="STOP"; break
            if not hit1:
                px=b["o"] if b["o"]>=tp1 else (tp1 if b["h"]>=tp1 else None)
                if px is not None:
                    f=min(TP1_FRAC,rem)
                    pnl+=f*(px-fill)-core.cost(px,f)
                    rem-=f; hit1=True; stop=max(stop,fill)
                    if rem>0 and b["l"]<=stop:
                        pnl+=rem*(stop-fill)-core.cost(stop,rem)
                        rem=0; exit_t=b["ct"]; reason="BE_AFTER_TP1"; break
            if rem>0 and hit1 and (b["o"]>=tp2 or b["h"]>=tp2):
                px=b["o"] if b["o"]>=tp2 else tp2
                pnl+=rem*(px-fill)-core.cost(px,rem)
                rem=0; hit2=True; exit_t=b["ct"]; reason="TP2"; break

        if rem>0:
            b=b15[last_i]; px=b["c"]
            pnl+=rem*(px-fill)-core.cost(px,rem)
            exit_t=b["ct"]; reason="TIME"

        trades.append({
            "symbol":sym,"timeframe":"1H_RTH","direction":"LONG",
            "signal_t":activation,"entry_t":b15[fill_i]["t"],"exit_t":exit_t,
            "entry":entry,"fill":fill,"initial_sl":sl,"tp1":tp1,"tp2":tp2,
            "risk":risk,"r":pnl/risk,"reason":reason,"tp1_hit":hit1,"tp2_hit":hit2,
            "wave2_retracement":sig.get("wave2_retracement"),
            "abc_b_retracement":sig.get("abc_b_retracement"),
            "abc_c_to_a":sig.get("abc_c_to_a"),
            "impulse_atr":sig.get("impulse_atr"),"risk_atr":sig.get("risk_atr")
        })
        busy_until=exit_t

    st=dict(st)
    st["fill_rate"]=st.get("filled",0)/st.get("patterns",1) if st.get("patterns",0) else None
    st["signal_bars"]=len(d); st["pivots"]=len(ps)
    return trades,st

def metrics(ts):
    o=sorted(ts,key=lambda z:(z["exit_t"],z["symbol"]))
    rs=[x["r"] for x in o]; pos=[r for r in rs if r>0]; neg=[r for r in rs if r<0]
    eq=peak=0.; dd=0.; cur=mx=0
    for r in rs:
        eq+=r; peak=max(peak,eq); dd=min(dd,eq-peak)
        if r<0: cur+=1; mx=max(mx,cur)
        else: cur=0
    return {"trades":len(o),"win_rate":len(pos)/len(o) if o else None,
            "total_r":sum(rs),"avg_r":statistics.fmean(rs) if rs else None,
            "profit_factor":sum(pos)/abs(sum(neg)) if neg else None,
            "max_drawdown_r":dd,"max_losing_streak":mx,
            "tp1_hit_rate":sum(t["tp1_hit"] for t in o)/len(o) if o else None,
            "tp2_hit_rate":sum(t["tp2_hit"] for t in o)/len(o) if o else None}

def main():
    if not DATA.exists(): raise FileNotFoundError(DATA)
    con=duckdb.connect(); alltr=[]; cells={}
    for i,sym in enumerate(SYMS,1):
        raw=load_symbol(con,sym)
        if len(raw)<500:
            cells[sym]={"metrics":metrics([]),"stats":{"skipped":"insufficient_data","bars15":len(raw)}}; continue
        adj,splits=adjust_splits_15m(raw)
        ts,st=simulate(sym,adj)
        st["bars15"]=len(adj)
        cells[sym]={"metrics":metrics(ts),"stats":st,"splits":splits}
        alltr+=ts
        print("RESULT",i,len(SYMS),sym,json.dumps(cells[sym]),flush=True)
    con.close()

    byy=defaultdict(list)
    for t in alltr:
        byy[str(datetime.fromtimestamp(t["entry_t"]/1000,UTC).year)].append(t)

    out={
        "strategy":"Elliott Wave 3 v4 candidate — Stock OOS25 RTH 1H LONG",
        "purpose":"Fresh symbol OOS of the post-hoc Stock30 observation: RTH 1H LONG-only using exact frozen v3 rules.",
        "universe":list(SYMS),
        "period":{"eval_start":EVAL_START.isoformat(),"eval_end_exclusive":EVAL_END.isoformat()},
        "rules":{
            "direction":"LONG only",
            "signal":"exact v3 5-wave impulse + ABC + B-wave breakout",
            "timeframe":"RTH 1H (six complete 60m bars 09:30-15:30 ET)",
            "execution":"15m RTH only; 15:30-16:00 execution-only",
            "entry_validity":"12 1H signal bars",
            "max_hold":"48 1H signal bars",
            "fees_bps":core.FEE_BPS,"slippage_bps":core.SLIP_BPS
        },
        "summary":metrics(alltr),
        "years":{k:metrics(v) for k,v in sorted(byy.items())},
        "symbols":cells,
        "trades":alltr
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2),encoding="utf-8")
    print("FINAL",json.dumps({"summary":out["summary"],"years":out["years"]},indent=2),flush=True)

if __name__=="__main__":
    main()
