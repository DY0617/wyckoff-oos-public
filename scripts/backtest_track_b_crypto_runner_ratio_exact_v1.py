import csv, io, json, math, statistics, sys, time, zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0,str(Path(__file__).parent))
import backtest_wyckoff_crypto_exact_conservative as bt
import wyckoff_status as w

SYMS=("BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT")
TFS=("1d","4h","15m")
DATA_START=(2020,9)
EVAL_START_MS=1632355200000
EVAL_END_MS=1790020800000
RECENT_START_MS=EVAL_END_MS-365*24*60*60*1000
FEE_BPS=4.0
SLIPPAGE_BPS=2.0
RISK=400.0
CAP=20000.0
A_OFF={"climax_spread_min":999.0,"climax_volume_min":999.0}
OUT=Path("data/validation/track_b_crypto_runner_ratio_exact_v1.json")
TRADES_OUT=Path("data/validation/track_b_crypto_runner_ratio_exact_trades_v1.json")

FUTURES_FILTERS={
    "BTCUSDT":(0.1,0.001,0.001),
    "ETHUSDT":(0.01,0.001,0.001),
    "BNBUSDT":(0.01,0.01,0.01),
    "SOLUSDT":(0.01,0.01,0.01),
}

NAMED={
 "30_30_40":(.30,.30),
 "25_25_50":(.25,.25),
 "20_20_60":(.20,.20),
 "15_20_65":(.15,.20),
 "15_15_70":(.15,.15),
 "10_20_70":(.10,.20),
 "10_15_75":(.10,.15),
 "15_10_75":(.15,.10),
 "10_10_80":(.10,.10),
}

def month_iter(y0,m0,y1,m1):
    y,m=y0,m0
    while (y,m)<=(y1,m1):
        yield y,m
        m+=1
        if m==13:y,m=y+1,1

def archive_url(sym,tf,y,m):
    ym=f"{y:04d}-{m:02d}"
    return f"https://data.binance.vision/data/futures/um/monthly/klines/{sym}/{tf}/{sym}-{tf}-{ym}.zip"

def daily_archive_url(sym,tf,y,m,d):
    ds=f"{y:04d}-{m:02d}-{d:02d}"
    return f"https://data.binance.vision/data/futures/um/daily/klines/{sym}/{tf}/{sym}-{tf}-{ds}.zip"

def fetch_zip(url,attempts=4):
    last=None
    for n in range(attempts):
        try:
            req=Request(url,headers={"User-Agent":"wyckoff-runner-ratio-research","Accept":"application/zip"})
            with urlopen(req,timeout=40) as r:blob=r.read()
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                text=z.read(z.namelist()[0]).decode("utf-8")
            out=[]
            for row in csv.reader(io.StringIO(text)):
                if not row or not row[0].isdigit():continue
                out.append({"t":int(row[0]),"o":float(row[1]),"h":float(row[2]),"l":float(row[3]),"c":float(row[4]),"v":float(row[5])})
            return out
        except Exception as e:
            last=e; time.sleep(1.5*(n+1))
    raise RuntimeError(f"archive fetch failed: {url}: {type(last).__name__}: {last}")

def load_market():
    months=list(month_iter(DATA_START[0],DATA_START[1],2026,8))
    tasks=[];market={s:{tf:{} for tf in TFS} for s in SYMS}
    with ThreadPoolExecutor(max_workers=16) as ex:
        for s in SYMS:
            for tf in TFS:
                for y,m in months:
                    tasks.append((ex.submit(fetch_zip,archive_url(s,tf,y,m)),s,tf,y,m))
        for n,(fut,s,tf,y,m) in enumerate(tasks,1):
            rows=fut.result()
            for x in rows:market[s][tf][x["t"]]=x
            if n%100==0:print("downloaded",n,"/",len(tasks),flush=True)
    daily=[]
    with ThreadPoolExecutor(max_workers=16) as ex:
        for s in SYMS:
            for tf in TFS:
                for d in range(1,22):
                    daily.append((ex.submit(fetch_zip,daily_archive_url(s,tf,2026,9,d)),s,tf,d))
        for fut,s,tf,d in daily:
            for x in fut.result():market[s][tf][x["t"]]=x
    out={}
    for s in SYMS:
        out[s]={}
        for tf in TFS:
            rows=[market[s][tf][k] for k in sorted(market[s][tf])]
            out[s][tf]=rows
            print(s,tf,len(rows),rows[0]["t"],rows[-1]["t"],flush=True)
    return out

def replay(t,f1,f2):
    # All grid points leave a non-zero runner. TP1/TP2 stop ratchets and pivot
    # trail therefore follow the exact same path; only realized fractions vary.
    sign=1 if t["direction"]=="LONG" else -1
    entry=float(t["entry"]); size=float(t["size"])
    cost=(FEE_BPS+SLIPPAGE_BPS)/10000.0
    realized=-size*entry*cost
    remain=1.0
    has_tp1=any(e.get("type")=="TP1" for e in t.get("events",[]))
    for e in t.get("events",[]):
        typ=e.get("type")
        if typ=="TP1":
            frac=min(f1,remain);px=float(e["price"])
            realized += frac*sign*(px-entry)*size-frac*size*px*cost
            remain-=frac
        elif typ=="TP2":
            # If setup has no TP1, preserve original semantics by reallocating
            # TP1's intended fraction to TP2 while keeping runner unchanged.
            desired=f2 if has_tp1 else f1+f2
            frac=min(desired,remain);px=float(e["price"])
            realized += frac*sign*(px-entry)*size-frac*size*px*cost
            remain-=frac
        elif typ in ("STOP","BE","FIB1618_FULL","FIB1618_PARTIAL","OPEN_MARK"):
            if remain<=1e-12:break
            px=float(e["price"]);frac=remain
            realized += frac*sign*(px-entry)*size-frac*size*px*cost
            remain=0.0;break
    if remain>1e-8:
        raise RuntimeError(f"open remainder {remain} {t.get('symbol')}")
    q=dict(t);q["pnl"]=realized;q["r"]=realized/RISK
    q["fractions"]=[f1,f2,1-f1-f2]
    return q

def summarize(trades):
    ordered=sorted(trades,key=lambda x:(x["exit_t"],x.get("symbol","")))
    rs=[float(t["r"]) for t in ordered]
    pos=[r for r in rs if r>0];neg=[r for r in rs if r<0]
    eq=CAP;peak=CAP;mdd=0.0;streak=max_streak=0
    for t in ordered:
        eq+=t["pnl"];peak=max(peak,eq);mdd=max(mdd,(peak-eq)/peak if peak else 0.0)
        if t["pnl"]<0:streak+=1;max_streak=max(max_streak,streak)
        else:streak=0
    return {
      "trades":len(ordered),"wins":sum(t["pnl"]>0 for t in ordered),
      "losses":sum(t["pnl"]<0 for t in ordered),
      "win_rate":sum(t["pnl"]>0 for t in ordered)/len(ordered) if ordered else None,
      "net_r":sum(rs),"avg_r":statistics.fmean(rs) if rs else None,
      "profit_factor":sum(pos)/abs(sum(neg)) if neg else None,
      "mdd_on_20k":mdd,"max_consecutive_losses":max_streak,
      "net_r_over_mdd":sum(rs)/(mdd*CAP/RISK) if mdd>0 else None,
    }

def evaluate(base,f1,f2):
    ts=[replay(t,f1,f2) for t in base]
    per={s:summarize([t for t in ts if t["symbol"]==s]) for s in SYMS}
    recent=[t for t in ts if t["entry_t"]>=RECENT_START_MS]
    return {
      "fractions":[f1,f2,1-f1-f2],
      "overall":summarize(ts),
      "recent_1y":summarize(recent),
      "symbols":per,
    }

def main():
    raw=load_market()
    cache={}
    for s in SYMS:
        D=w.enrich([dict(x) for x in raw[s]["1d"]])
        H=w.enrich([dict(x) for x in raw[s]["4h"]])
        M=[dict(x) for x in raw[s]["15m"]]
        cache[s]=(D,H,M)
    bt._CACHE.clear()
    bt.dataset=lambda sym:cache[sym]
    bt.symbol_filters=lambda sym:FUTURES_FILTERS[sym]
    old=bt.RISK;bt.RISK=RISK
    base=[]
    try:
        for s in SYMS:
            r=bt.simulate(s,A_OFF,{},EVAL_START_MS,EVAL_END_MS,FEE_BPS,SLIPPAGE_BPS,
                          a_mode="snapshot",b_runner_mode="pivot",b_scale_mode="30_30_40")
            ts=[{"symbol":s,**t} for t in r["trades"] if t["track"]=="B" and t["reason"]!="OPEN_MARK"]
            base+=ts
            print("BASE",s,json.dumps(summarize(ts)),flush=True)
    finally:
        bt.RISK=old
    base=sorted(base,key=lambda x:(x["entry_t"],x["symbol"]))

    # Validate replay reproduces corrected engine baseline.
    replay_base=evaluate(base,.30,.30)
    raw_base=summarize(base)
    parity={
      "raw_corrected_engine":raw_base,
      "replayed_30_30_40":replay_base["overall"],
      "trades_match":raw_base["trades"]==replay_base["overall"]["trades"],
      "net_r_abs_diff":abs(raw_base["net_r"]-replay_base["overall"]["net_r"]),
    }

    grid=[]
    for i in range(10,41,5):
        for j in range(10,41,5):
            r=100-i-j
            if 40<=r<=80:
                x=evaluate(base,i/100,j/100)
                x["name"]=f"{i}_{j}_{r}"
                grid.append(x)

    def rank(scope,symbol=None,key="net_r"):
        def val(x):
            z=x["symbols"][symbol] if symbol else x[scope]
            if key=="balanced":
                m=z["mdd_on_20k"]
                return z["net_r"]/(m*CAP/RISK) if m and m>0 else -1e9
            return z.get(key) if z.get(key) is not None else -1e9
        return sorted(grid,key=val,reverse=True)

    named={k:evaluate(base,*v) for k,v in NAMED.items()}
    best_by_symbol={}
    for s in SYMS:
        net=rank("overall",s,"net_r")[0]
        bal=rank("overall",s,"balanced")[0]
        best_by_symbol[s]={
          "max_net_r":{"name":net["name"],**net["symbols"][s]},
          "max_net_r_over_mdd":{"name":bal["name"],**bal["symbols"][s]},
          "baseline_30_30_40":named["30_30_40"]["symbols"][s],
          "15_15_70":named["15_15_70"]["symbols"][s],
          "10_15_75":named["10_15_75"]["symbols"][s],
        }

    top_net=rank("overall",None,"net_r")[:10]
    top_bal=rank("overall",None,"balanced")[:10]
    report={
      "market":"Binance USD-M perpetual",
      "strategy":"Track B current setup logic; EXACT 15m entry touch; conservative same-bar TP1=>BE and TP2=>TP1 ratchet; confirmed 4H pivot runner",
      "evaluation_period":{"start_ms":EVAL_START_MS,"end_ms":EVAL_END_MS},
      "costs":{"fee_bps_per_fill":FEE_BPS,"slippage_bps_per_fill":SLIPPAGE_BPS},
      "grid":{"tp1_pct":"10..40 step5","tp2_pct":"10..40 step5","runner_pct":"40..80","count":len(grid)},
      "parity":parity,
      "named":named,
      "best_by_symbol":best_by_symbol,
      "top10_overall_net_r":[{"name":x["name"],"fractions":x["fractions"],**x["overall"]} for x in top_net],
      "top10_overall_balanced":[{"name":x["name"],"fractions":x["fractions"],**x["overall"]} for x in top_bal],
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    TRADES_OUT.write_text(json.dumps({"base_corrected_trades":base},ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    print("PARITY",json.dumps(parity),flush=True)
    print("NAMED",json.dumps({k:v["overall"] for k,v in named.items()}),flush=True)
    print("BEST_SYMBOL",json.dumps(best_by_symbol),flush=True)
    print("TOP_NET",json.dumps(report["top10_overall_net_r"][:5]),flush=True)

if __name__=="__main__":main()
