import csv, io, json, statistics, sys, time, urllib.error, urllib.request, zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).parent))
import backtest_wyckoff_runner_sweep_engine as bt
import wyckoff_status as w

SYMS=("XRPUSDT","ADAUSDT","DOGEUSDT","LINKUSDT")
TFS=("1d","4h","15m")
DATA_START=(2020,9)
EVAL_START_MS=1632355200000
EVAL_END_MS=1790020800000
FEE_BPS=4.0
SLIPPAGE_BPS=2.0
RISK=400.0
CAP=20000.0
A_OFF={"climax_spread_min":999.0,"climax_volume_min":999.0}
OUT=Path("data/validation/wyckoff_track_b_15_25_60_alt_oos_v1.json")
TRADES_OUT=Path("data/validation/wyckoff_track_b_15_25_60_alt_oos_v1_trades.json")

FALLBACK_FILTERS={
    "XRPUSDT":(0.0001,0.1,0.1),
    "ADAUSDT":(0.0001,0.1,0.1),
    "DOGEUSDT":(0.00001,1.0,1.0),
    "LINKUSDT":(0.001,0.01,0.01),
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
            req=urllib.request.Request(url,headers={"User-Agent":"wyckoff-alt-oos","Accept":"application/zip"})
            with urllib.request.urlopen(req,timeout=40) as r:blob=r.read()
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                text=z.read(z.namelist()[0]).decode("utf-8")
            out=[]
            for row in csv.reader(io.StringIO(text)):
                if not row or not row[0].isdigit():continue
                out.append({"t":int(row[0]),"o":float(row[1]),"h":float(row[2]),"l":float(row[3]),"c":float(row[4]),"v":float(row[5])})
            return out
        except urllib.error.HTTPError as e:
            if e.code==404:return []
            last=e
        except Exception as e:
            last=e
        time.sleep(1.5*(n+1))
    raise RuntimeError(f"archive fetch failed: {url}: {type(last).__name__}: {last}")

def fetch_filters():
    out=dict(FALLBACK_FILTERS)
    try:
        req=urllib.request.Request("https://fapi.binance.com/fapi/v1/exchangeInfo",headers={"User-Agent":"wyckoff-alt-oos"})
        with urllib.request.urlopen(req,timeout=20) as r:
            data=json.loads(r.read().decode("utf-8"))
        for s in data.get("symbols",[]):
            sym=s.get("symbol")
            if sym not in SYMS:continue
            fs={f.get("filterType"):f for f in s.get("filters",[])}
            pf=fs.get("PRICE_FILTER",{}); lf=fs.get("LOT_SIZE",{})
            out[sym]=(float(pf.get("tickSize") or 0),float(lf.get("stepSize") or 0),float(lf.get("minQty") or 0))
    except Exception as e:
        print("exchangeInfo fallback",repr(e),flush=True)
    print("FILTERS",json.dumps(out),flush=True)
    return out

def load_market():
    months=list(month_iter(DATA_START[0],DATA_START[1],2026,8))
    market={s:{tf:{} for tf in TFS} for s in SYMS}
    tasks=[]
    with ThreadPoolExecutor(max_workers=16) as ex:
        for s in SYMS:
            for tf in TFS:
                for y,m in months:
                    tasks.append((ex.submit(fetch_zip,archive_url(s,tf,y,m)),s,tf,y,m))
        for n,(fut,s,tf,y,m) in enumerate(tasks,1):
            rows=fut.result()
            if not rows:
                print("MISSING_OR_EMPTY",s,tf,f"{y:04d}-{m:02d}",flush=True)
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
            if not rows: raise RuntimeError(f"no data {s} {tf}")
            out[s][tf]=rows
            print(s,tf,len(rows),rows[0]["t"],rows[-1]["t"],flush=True)
    return out

def summarize(trades):
    ordered=sorted([t for t in trades if t["reason"]!="OPEN_MARK"],key=lambda x:(x["exit_t"],x.get("symbol","")))
    rs=[t["r"] for t in ordered];pos=[r for r in rs if r>0];neg=[r for r in rs if r<0]
    eq=CAP;peak=CAP;mdd=0.0;streak=0;max_streak=0;holds=[];tp1=tp2=0
    for t in ordered:
        eq+=t["pnl"];peak=max(peak,eq);mdd=max(mdd,(peak-eq)/peak if peak else 0.0)
        if t["pnl"]<0:streak+=1;max_streak=max(max_streak,streak)
        else:streak=0
        holds.append((t["exit_t"]-t["entry_t"])/3_600_000)
        ev=t.get("events") or []
        tp1+=any(e.get("type")=="TP1" for e in ev)
        tp2+=any(e.get("type")=="TP2" for e in ev)
    pnl=sum(t["pnl"] for t in ordered)
    return {
        "trades":len(ordered),"wins":sum(t["pnl"]>0 for t in ordered),"losses":sum(t["pnl"]<0 for t in ordered),
        "win_rate":sum(t["pnl"]>0 for t in ordered)/len(ordered) if ordered else None,
        "net_pnl_usd":pnl,"net_r":sum(rs),"avg_r":statistics.fmean(rs) if rs else None,
        "profit_factor":sum(pos)/abs(sum(neg)) if neg else None,
        "return_on_20k":pnl/CAP,"ending_equity_usd":CAP+pnl,
        "max_drawdown":mdd,"max_consecutive_losses":max_streak,
        "tp1_hit_rate":tp1/len(ordered) if ordered else None,"tp2_hit_rate":tp2/len(ordered) if ordered else None,
        "avg_hold_hours":statistics.fmean(holds) if holds else None,
        "median_hold_hours":statistics.median(holds) if holds else None,
    }

def main():
    raw=load_market(); filters=fetch_filters()
    cache={}
    for s in SYMS:
        D=w.enrich([dict(x) for x in raw[s]["1d"]])
        H=w.enrich([dict(x) for x in raw[s]["4h"]])
        M=[dict(x) for x in raw[s]["15m"]]
        cache[s]=(D,H,M)

    bt._CACHE.clear()
    bt.dataset=lambda sym:cache[sym]
    bt.symbol_filters=lambda sym:filters[sym]
    old=bt.RISK;bt.RISK=RISK
    try:
        alltr=[];symbols={}
        for s in SYMS:
            r=bt.simulate(s,A_OFF,{},EVAL_START_MS,EVAL_END_MS,FEE_BPS,SLIPPAGE_BPS,
                          a_mode="snapshot",b_runner_mode="pivot",b_scale_mode="15_25_60")
            ts=[{"symbol":s,**t} for t in r["trades"] if t["track"]=="B" and t["reason"]!="OPEN_MARK"]
            alltr+=ts;symbols[s]=summarize(ts)
            print("SYMBOL",s,json.dumps(symbols[s]),flush=True)

        years=defaultdict(list);dirs=defaultdict(list)
        for t in alltr:
            years[str(datetime.fromtimestamp(t["entry_t"]/1000,timezone.utc).year)].append(t)
            dirs[t["direction"]].append(t)
        sm=summarize(alltr)
        positive_symbols=sum(v["net_r"]>0 for v in symbols.values())
        pass_flags={
            "combined_net_r_positive":sm["net_r"]>0,
            "combined_pf_gt_1_30":(sm["profit_factor"] or 0)>1.30,
            "at_least_3_of_4_symbols_positive":positive_symbols>=3,
        }
        out={
            "strategy":"TRACK_B_V1_0_FROZEN + 15/25/60 + 4H pivot runner",
            "test_type":"untuned alt-coin OOS robustness",
            "universe":list(SYMS),
            "evaluation_period":{"start":"2021-09-23T00:00:00Z","end":"2026-09-21T20:00:00Z"},
            "costs":{"fee_bps_per_fill":FEE_BPS,"slippage_bps_per_fill":SLIPPAGE_BPS},
            "capital_usd":CAP,"risk_usd":RISK,
            "summary":sm,"symbols":symbols,
            "directions":{k:summarize(v) for k,v in sorted(dirs.items())},
            "years":{k:summarize(v) for k,v in sorted(years.items())},
            "pass_criteria":{
                "required":{"combined_net_r":">0","combined_profit_factor":">1.30","positive_symbols":">=3/4"},
                "observed_positive_symbols":positive_symbols,
                "flags":pass_flags,
                "passed_all":all(pass_flags.values()),
            }
        }
        OUT.parent.mkdir(parents=True,exist_ok=True)
        OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
        TRADES_OUT.write_text(json.dumps({"summary":out,"trades":sorted(alltr,key=lambda x:x["entry_t"])},ensure_ascii=False,separators=(",",":")),encoding="utf-8")
        print("FINAL",json.dumps(out,ensure_ascii=False,indent=2),flush=True)
    finally:
        bt.RISK=old

if __name__=="__main__":main()
