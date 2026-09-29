import csv, io, json, statistics, time, urllib.request, urllib.error, zipfile
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/validation/cat_short_swing_v0_2_crypto_pilot.json"
UTC = timezone.utc

SYMBOLS = ("BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT")
FETCH_START = datetime(2023,1,1,tzinfo=UTC)
EVAL_START = datetime(2023,9,1,tzinfo=UTC)
EVAL_END = datetime(2026,9,1,tzinfo=UTC)

FEE_BPS = 4.0
SLIP_BPS = 2.0
COST_BPS = FEE_BPS + SLIP_BPS
ENTRY_BUFFER_ATR = 0.05
STOP_STRUCT_ATR = 0.25
STOP_MIN_ATR = 1.0
STOP_MAX_ATR = 2.0
TP1_R = 1.5
TP2_R = 2.5
ENTRY_VALID_BARS = 32
MAX_HOLD_BARS = 72 * 4

def month_iter(start, end):
    y,m=start.year,start.month
    while (y,m)<(end.year,end.month):
        yield y,m
        m+=1
        if m==13:y,m=y+1,1

def fetch_zip(url, attempts=5):
    last=None
    for a in range(1,attempts+1):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"cat-short-swing-v0.2/1.0"})
            with urllib.request.urlopen(req,timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code==404:return None
            last=e
        except Exception as e:
            last=e
        time.sleep(min(20,2*a))
    raise RuntimeError(f"download failed: {url} {last!r}")

def normalize_ms(x):
    v=int(float(x))
    while v>10_000_000_000_000:v//=1000
    if v<10_000_000_000:v*=1000
    return v

def load_15m(sym):
    out=[]
    for y,m in month_iter(FETCH_START,EVAL_END):
        url=f"https://data.binance.vision/data/futures/um/monthly/klines/{sym}/15m/{sym}-15m-{y:04d}-{m:02d}.zip"
        raw=fetch_zip(url)
        if raw is None:
            print("MISSING",sym,y,m,flush=True);continue
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            txt=z.read(z.namelist()[0]).decode("utf-8-sig")
        n=0
        for r in csv.reader(io.StringIO(txt)):
            if not r:continue
            try:
                t=normalize_ms(r[0]);o,h,l,c,v=map(float,r[1:6])
            except Exception:
                continue
            if int(FETCH_START.timestamp()*1000)<=t<int(EVAL_END.timestamp()*1000):
                out.append({"t":t,"ct":t+15*60_000,"o":o,"h":h,"l":l,"c":c,"v":v});n+=1
        print("MONTH",sym,f"{y:04d}-{m:02d}",n,flush=True)
    dedup={x["t"]:x for x in out}
    out=[dedup[k] for k in sorted(dedup)]
    print("LOADED",sym,len(out),flush=True)
    return out

def aggregate(base,minutes):
    ms=minutes*60_000;buckets=defaultdict(list)
    for b in base:buckets[(b["t"]//ms)*ms].append(b)
    need=minutes//15;out=[]
    for k in sorted(buckets):
        xs=sorted(buckets[k],key=lambda x:x["t"])
        if len(xs)!=need or xs[0]["t"]!=k or xs[-1]["ct"]!=k+ms:continue
        out.append({"t":k,"ct":k+ms,"o":xs[0]["o"],"h":max(x["h"] for x in xs),
                    "l":min(x["l"] for x in xs),"c":xs[-1]["c"],"v":sum(x["v"] for x in xs)})
    return out

def ema(vals,n):
    k=2/(n+1);e=None;out=[]
    for x in vals:
        e=x if e is None else e+k*(x-e);out.append(e)
    return out

def enrich(D):
    if not D:return D
    cs=[x["c"] for x in D];e50=ema(cs,50);e200=ema(cs,200);atr=None
    for i,x in enumerate(D):
        pc=cs[i-1] if i else x["c"]
        tr=max(x["h"]-x["l"],abs(x["h"]-pc),abs(x["l"]-pc))
        atr=tr if atr is None else ((atr*13)+tr)/14
        x["atr14"]=atr;x["ema50"]=e50[i];x["ema200"]=e200[i]
        for n in (20,60,120):
            x[f"ret{n}"]=x["c"]/D[i-n]["c"]-1 if i>=n and D[i-n]["c"]>0 else None
        if i>=20:
            path=sum(abs(D[j]["c"]-D[j-1]["c"]) for j in range(i-19,i+1))
            x["er20"]=abs(x["c"]-D[i-20]["c"])/path if path>0 else 0.0
            x["prior20h"]=max(z["h"] for z in D[i-20:i])
        else:
            x["er20"]=None;x["prior20h"]=None
        x["low5"]=min(z["l"] for z in D[max(0,i-4):i+1])
    return D

def regime4(x):
    if x is None:return False
    vals=[x.get(f"ret{n}") for n in (20,60,120)]
    return (all(v is not None for v in vals) and x["c"]>x["ema200"] and
            x["ema50"]>x["ema200"] and sum(v>0 for v in vals)>=2)

def setup1(x):
    return (x.get("atr14") is not None and x["atr14"]>0 and
            x.get("er20") is not None and x["er20"]>=0.30 and
            x.get("prior20h") is not None and
            x["c"]>x["ema50"]>x["ema200"] and x["c"]>x["prior20h"])

def fill_cost(px,frac=1.0):
    return frac*px*COST_BPS/10000.0

def metrics(ts):
    ordered=sorted(ts,key=lambda z:(z["exit_t"],z["symbol"]));rs=[x["r"] for x in ordered]
    pos=[r for r in rs if r>0];neg=[r for r in rs if r<0]
    eq=peak=0.0;dd=0.0;cur=mx=0
    for r in rs:
        eq+=r;peak=max(peak,eq);dd=min(dd,eq-peak)
        if r<0:cur+=1;mx=max(mx,cur)
        else:cur=0
    holds=[x["hold_hours"] for x in ordered]
    return {"trades":len(ordered),"wins":len(pos),"losses":len(neg),
            "win_rate":len(pos)/len(ordered) if ordered else None,
            "total_r":sum(rs),"avg_r":statistics.fmean(rs) if rs else None,
            "profit_factor":sum(pos)/abs(sum(neg)) if neg else None,
            "max_drawdown_r":dd,"max_losing_streak":mx,
            "tp1_hit_rate":sum(x["tp1_hit"] for x in ordered)/len(ordered) if ordered else None,
            "tp2_hit_rate":sum(x["tp2_hit"] for x in ordered)/len(ordered) if ordered else None,
            "avg_hold_hours":statistics.fmean(holds) if holds else None,
            "median_hold_hours":statistics.median(holds) if holds else None}

def simulate_symbol(sym,b15):
    h1=enrich(aggregate(b15,60));h4=enrich(aggregate(b15,240))
    h4_ct=[x["ct"] for x in h4];b15_t=[x["t"] for x in b15]
    eval_lo=int(EVAL_START.timestamp()*1000);eval_hi=int(EVAL_END.timestamp()*1000)
    trades=[];stats=defaultdict(int);busy_until=-1

    for x in h1:
        if x["ct"]<eval_lo or x["ct"]>=eval_hi:continue
        if x["ct"]<busy_until:
            stats["setup_while_busy"]+=1;continue
        if not setup1(x):continue
        k=bisect_left(h4_ct,x["ct"]+1)-1
        if k<0 or not regime4(h4[k]):continue

        stats["setups"]+=1
        A=x["atr14"];planned_entry=x["prior20h"]+ENTRY_BUFFER_ATR*A
        raw_stop=x["low5"]-STOP_STRUCT_ATR*A
        raw_dist=planned_entry-raw_stop
        dist=max(STOP_MIN_ATR*A,min(STOP_MAX_ATR*A,raw_dist))
        sl=planned_entry-dist
        if sl<=0 or sl>=planned_entry:
            stats["invalid_levels"]+=1;continue
        R=planned_entry-sl;tp1=planned_entry+TP1_R*R;tp2=planned_entry+TP2_R*R

        start=bisect_left(b15_t,x["ct"])
        pending_end_t=x["ct"]+ENTRY_VALID_BARS*15*60_000
        busy_until=pending_end_t
        fill_idx=None;fill_px=None;cancel_t=None
        for j in range(start,min(start+ENTRY_VALID_BARS,len(b15))):
            b=b15[j]
            if b["t"]>=eval_hi:break
            if b["o"]<=sl:
                stats["cancel_gap_through"]+=1;cancel_t=b["ct"];break
            if b["o"]<=planned_entry:
                fill_idx=j;fill_px=b["o"];break
            if b["l"]<=planned_entry<=b["h"]:
                fill_idx=j;fill_px=planned_entry;break

        if fill_idx is None:
            if cancel_t is not None:busy_until=cancel_t
            else:stats["expired"]+=1
            continue

        stats["filled"]+=1
        pnl=-fill_cost(fill_px,1.0);remaining=1.0;tp1_hit=False;tp2_hit=False
        exit_t=b15[fill_idx]["ct"];exit_px=fill_px;reason="TIME"
        last_idx=min(fill_idx+MAX_HOLD_BARS-1,len(b15)-1)

        for j in range(fill_idx,last_idx+1):
            b=b15[j]
            if b["t"]>=eval_hi:
                last_idx=j;break

            if b["o"]<=sl:
                pnl+=remaining*(b["o"]-fill_px)-fill_cost(b["o"],remaining)
                exit_px=b["o"];exit_t=b["ct"];reason="GAP_SL";remaining=0.0;break
            if b["l"]<=sl:
                pnl+=remaining*(sl-fill_px)-fill_cost(sl,remaining)
                exit_px=sl;exit_t=b["ct"];reason="SL";remaining=0.0;break

            if not tp1_hit and b["h"]>=tp1:
                frac=min(0.5,remaining)
                pnl+=frac*(tp1-fill_px)-fill_cost(tp1,frac)
                remaining-=frac;tp1_hit=True
            if remaining>0 and b["h"]>=tp2:
                pnl+=remaining*(tp2-fill_px)-fill_cost(tp2,remaining)
                remaining=0.0;tp2_hit=True;exit_px=tp2;exit_t=b["ct"];reason="TP2";break

            if j==last_idx and remaining>0:
                px=b["c"];pnl+=remaining*(px-fill_px)-fill_cost(px,remaining)
                exit_px=px;exit_t=b["ct"];reason="TIME";remaining=0.0;break

        if remaining>0:
            b=b15[last_idx];px=b["c"]
            pnl+=remaining*(px-fill_px)-fill_cost(px,remaining)
            exit_px=px;exit_t=b["ct"];reason="END";remaining=0.0

        r=pnl/R;hold_hours=max(0.0,(exit_t-b15[fill_idx]["t"])/3_600_000)
        trades.append({"symbol":sym,"setup_t":x["ct"],"entry_t":b15[fill_idx]["t"],"exit_t":exit_t,
                       "planned_entry":planned_entry,"fill":fill_px,"sl":sl,"tp1":tp1,"tp2":tp2,
                       "planned_risk":R,"risk_atr":R/A,"r":r,"reason":reason,
                       "tp1_hit":tp1_hit,"tp2_hit":tp2_hit,"hold_hours":hold_hours,
                       "regime4_t":h4[k]["ct"],"er20_1h":x["er20"]})
        busy_until=exit_t

    stats=dict(stats)
    stats["fill_rate"]=stats.get("filled",0)/stats.get("setups",1) if stats.get("setups",0) else None
    stats["expiry_rate"]=stats.get("expired",0)/stats.get("setups",1) if stats.get("setups",0) else None
    return trades,stats

def main():
    all_trades=[];symbols={}
    for sym in SYMBOLS:
        b15=load_15m(sym);ts,st=simulate_symbol(sym,b15)
        symbols[sym]={"metrics":metrics(ts),"stats":st};all_trades+=ts
        print("RESULT",sym,json.dumps(symbols[sym]),flush=True)

    years=defaultdict(list)
    for t in all_trades:
        years[str(datetime.fromtimestamp(t["entry_t"]/1000,UTC).year)].append(t)
    total_setups=sum(v["stats"].get("setups",0) for v in symbols.values())
    total_filled=sum(v["stats"].get("filled",0) for v in symbols.values())
    total_expired=sum(v["stats"].get("expired",0) for v in symbols.values())
    total_cancel=sum(v["stats"].get("cancel_gap_through",0) for v in symbols.values())
    out={"strategy":"CAT Short-Swing v0.2 breakout-retest frozen pilot",
         "asset_class":"Binance USDT-M perpetual",
         "period":{"fetch_start":FETCH_START.isoformat(),"eval_start":EVAL_START.isoformat(),"eval_end_exclusive":EVAL_END.isoformat()},
         "rules":{"direction":"LONG only",
                  "regime_4h":"close>EMA200, EMA50>EMA200, 2 of ret20/60/120 > 0",
                  "setup_1h":"close>EMA50>EMA200, ER20>=0.30, close>prior20h",
                  "entry":"prior20h + 0.05 ATR14 buy-limit; valid next 32x15m bars",
                  "stop":"last-5 completed 1H low - 0.25 ATR, distance clamped 1.0-2.0 ATR",
                  "tp":"50% at 1.5R, 50% at 2.5R; no BE; no trail",
                  "max_hold":"72h","intrabar":"adverse-first",
                  "cost_bps_per_fill_equivalent":COST_BPS},
         "summary":metrics(all_trades),
         "execution":{"setups":total_setups,"filled":total_filled,"expired":total_expired,
                      "cancel_gap_through":total_cancel,
                      "fill_rate":total_filled/total_setups if total_setups else None,
                      "expiry_rate":total_expired/total_setups if total_setups else None},
         "years":{k:metrics(v) for k,v in sorted(years.items())},
         "symbols":symbols,"trades":all_trades}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2),encoding="utf-8")
    print("FINAL",json.dumps({k:v for k,v in out.items() if k!="trades"},indent=2),flush=True)

if __name__=="__main__":main()
