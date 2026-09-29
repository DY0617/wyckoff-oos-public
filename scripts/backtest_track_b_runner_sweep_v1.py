import csv, io, json, statistics, sys, time, zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0,str(Path(__file__).parent))
import backtest_wyckoff_runner_sweep_engine as bt
import wyckoff_status as w

SYMS=("BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT")
TFS=("1d","4h","15m")
DATA_START=(2020,9)
EVAL_START_MS=1632355200000
EVAL_END_MS=1790020800000
FEE_BPS=4.0
SLIPPAGE_BPS=2.0
RISK=400.0
CAP=20000.0
A_OFF={"climax_spread_min":999.0,"climax_volume_min":999.0}
OUT=Path("data/validation/wyckoff_track_b_runner_sweep_v1.json")
TRADES_OUT=Path("data/validation/wyckoff_track_b_runner_sweep_v1_trades.json")

FUTURES_FILTERS={
    "BTCUSDT":(0.1,0.001,0.001),
    "ETHUSDT":(0.01,0.001,0.001),
    "BNBUSDT":(0.01,0.01,0.01),
    "SOLUSDT":(0.01,0.01,0.01),
}

MODES={
    "30_30_40__PIVOT":{"scale":"30_30_40","runner":"pivot"},
    "30_30_40__FIB_FULL":{"scale":"30_30_40","runner":"fib1618_full"},
    "30_30_40__FIB_HALF":{"scale":"30_30_40","runner":"fib1618_half"},
    "20_30_50__PIVOT":{"scale":"20_30_50","runner":"pivot"},
    "20_30_50__FIB_FULL":{"scale":"20_30_50","runner":"fib1618_full"},
    "20_30_50__FIB_HALF":{"scale":"20_30_50","runner":"fib1618_half"},
    "25_25_50__PIVOT":{"scale":"25_25_50","runner":"pivot"},
    "25_25_50__FIB_FULL":{"scale":"25_25_50","runner":"fib1618_full"},
    "25_25_50__FIB_HALF":{"scale":"25_25_50","runner":"fib1618_half"},
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
            req=Request(url,headers={"User-Agent":"wyckoff-runner-sweep","Accept":"application/zip"})
            with urlopen(req,timeout=40) as r:blob=r.read()
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                text=z.read(z.namelist()[0]).decode("utf-8")
            out=[]
            for row in csv.reader(io.StringIO(text)):
                if not row or not row[0].isdigit():continue
                out.append({"t":int(row[0]),"o":float(row[1]),"h":float(row[2]),"l":float(row[3]),"c":float(row[4]),"v":float(row[5])})
            return out
        except Exception as e:
            last=e
            time.sleep(1.5*(n+1))
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
            rows=fut.result()
            for x in rows:market[s][tf][x["t"]]=x
    out={}
    for s in SYMS:
        out[s]={}
        for tf in TFS:
            rows=[market[s][tf][k] for k in sorted(market[s][tf])]
            out[s][tf]=rows
            print(s,tf,len(rows),rows[0]["t"],rows[-1]["t"],flush=True)
    return out

def summarize(trades, include_open_marks=False):
    src=list(trades) if include_open_marks else [t for t in trades if t["reason"]!="OPEN_MARK"]
    ordered=sorted(src,key=lambda x:(x["exit_t"],x.get("symbol","")))
    rs=[t["r"] for t in ordered]
    pos=[r for r in rs if r>0];neg=[r for r in rs if r<0]
    eq=CAP;peak=CAP;mdd=0.0;streak=0;max_streak=0;holds=[];tp1=tp2=0
    for t in ordered:
        eq+=t["pnl"];peak=max(peak,eq);mdd=max(mdd,(peak-eq)/peak if peak else 0.0)
        if t["pnl"]<0:streak+=1;max_streak=max(max_streak,streak)
        else:streak=0
        holds.append((t["exit_t"]-t["entry_t"])/3_600_000)
        ev=t.get("events") or []
        tp1+=any(e.get("type")=="TP1" and (e.get("fraction") or 0)>0 for e in ev)
        tp2+=any(e.get("type")=="TP2" and (e.get("fraction") or 0)>0 for e in ev)
    pnl=sum(t["pnl"] for t in ordered)
    return {
        "trades":len(ordered),
        "open_marks":sum(t["reason"]=="OPEN_MARK" for t in ordered),
        "long":sum(t["direction"]=="LONG" for t in ordered),
        "short":sum(t["direction"]=="SHORT" for t in ordered),
        "wins":sum(t["pnl"]>0 for t in ordered),
        "losses":sum(t["pnl"]<0 for t in ordered),
        "win_rate":sum(t["pnl"]>0 for t in ordered)/len(ordered) if ordered else None,
        "net_pnl_usd":pnl,
        "net_r":sum(rs),
        "avg_r":statistics.fmean(rs) if rs else None,
        "profit_factor":sum(pos)/abs(sum(neg)) if neg else None,
        "return_on_20k":pnl/CAP,
        "ending_equity_usd":CAP+pnl,
        "max_drawdown":mdd,
        "max_consecutive_losses":max_streak,
        "tp1_hit_rate":tp1/len(ordered) if ordered else None,
        "tp2_hit_rate":tp2/len(ordered) if ordered else None,
        "avg_hold_hours":statistics.fmean(holds) if holds else None,
        "median_hold_hours":statistics.median(holds) if holds else None,
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
    report={
        "market":"Binance USD-M perpetual",
        "strategy":"TRACK_B_V1_0_FROZEN setup logic; scale/runner sweep only",
        "evaluation_period":{"start":"2021-09-23T00:00:00Z","end":"2026-09-21T20:00:00Z"},
        "costs":{"fee_bps_per_fill":FEE_BPS,"slippage_bps_per_fill":SLIPPAGE_BPS},
        "capital_usd":CAP,"fixed_risk_usd":RISK,
        "modes":{}
    }
    all_modes={}
    try:
        for mode,cfg in MODES.items():
            alltr=[];symbols={}
            for s in SYMS:
                r=bt.simulate(s,A_OFF,{},EVAL_START_MS,EVAL_END_MS,FEE_BPS,SLIPPAGE_BPS,
                              a_mode="snapshot",b_runner_mode=cfg["runner"],b_scale_mode=cfg["scale"])
                ts=[{"symbol":s,**t} for t in r["trades"] if t["track"]=="B"]
                alltr+=ts
                symbols[s]={
                    "closed":summarize(ts,False),
                    "marked":summarize(ts,True),
                }
                print("MODE",mode,s,json.dumps(symbols[s]),flush=True)

            dirs={}
            for d in ("LONG","SHORT"):
                q=[t for t in alltr if t["direction"]==d]
                dirs[d]={"closed":summarize(q,False),"marked":summarize(q,True)}
            yrs=defaultdict(list)
            for t in alltr:
                yrs[str(datetime.fromtimestamp(t["entry_t"]/1000,timezone.utc).year)].append(t)

            report["modes"][mode]={
                "scale":cfg["scale"],"runner":cfg["runner"],
                "closed":summarize(alltr,False),
                "marked":summarize(alltr,True),
                "directions":dirs,
                "years":{k:{"closed":summarize(v,False),"marked":summarize(v,True)} for k,v in sorted(yrs.items())},
                "symbols":symbols,
            }
            all_modes[mode]=sorted(alltr,key=lambda x:x["entry_t"])
            print("TOTAL",mode,json.dumps(report["modes"][mode]),flush=True)

        b=report["modes"]["30_30_40__PIVOT"]["closed"]
        report["baseline_parity"]={
            "expected_closed_trades":146,"actual_closed_trades":b["trades"],
            "expected_net_r":49.71696111913852,"actual_net_r":b["net_r"],
            "trade_count_match":b["trades"]==146,
            "net_r_abs_diff":abs(b["net_r"]-49.71696111913852),
        }
        OUT.parent.mkdir(parents=True,exist_ok=True)
        OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        TRADES_OUT.write_text(json.dumps({"summary":report,"trades":all_modes},ensure_ascii=False,separators=(",",":")),encoding="utf-8")
        print("FINAL",json.dumps(report,ensure_ascii=False,indent=2),flush=True)
    finally:
        bt.RISK=old

if __name__=="__main__":
    main()
