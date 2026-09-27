import json, sys, math, urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas_market_calendars as mcal

sys.path.insert(0,str(Path(__file__).parent))
import backtest_wyckoff_exact_touch_ct as bt
import wyckoff_status as w

ROOT=Path("data/validation/dukascopy_same_window_raw")
BASE=Path("data/validation/stock53_rth_entry_timing_abc.json")
OUT=Path("data/validation/stock32_dukascopy_vs_binance_same_window.json")
PROXY="https://zmbeamtclazjtfxyysre.supabase.co/functions/v1/stock-tradifi-history-export?kind=exchangeInfo"
UTC=timezone.utc
NY=ZoneInfo("America/New_York")
FEE_BPS=4.0
SLIPPAGE_BPS=2.0
CAP=20000.0
RISK=400.0
A_OFF={"climax_spread_min":999.0,"climax_volume_min":999.0}
SUPPORTED=("AAPL","AMZN","AVGO","DELL","MSFT","MU","AMD","BABA","INTC","JPM","NFLX","V",
           "COST","GOOGL","LLY","META","NVDA","QQQ","TSLA","UBER","WMT","AMAT","CAT","HD",
           "MRVL","ORCL","SPY","TSM","CRM","CSCO","DIS","IBM")

def exchange_filters():
    req=urllib.request.Request(PROXY,headers={"User-Agent":"wyckoff-dukascopy-compare/1.0"})
    with urllib.request.urlopen(req,timeout=60) as r:
        j=json.loads(r.read())
    out={}
    for m in j.get("symbols",[]):
        sym=str(m.get("symbol") or "")
        if not sym.endswith("USDT"): continue
        by={x.get("filterType"):x for x in m.get("filters",[])}
        pf=by.get("PRICE_FILTER",{}); lf=by.get("LOT_SIZE",{})
        out[sym[:-4]]=(float(pf.get("tickSize") or .01),float(lf.get("stepSize") or 0),float(lf.get("minQty") or 0))
    return out

def calendar_map(start_ms,end_ms):
    a=datetime.fromtimestamp(start_ms/1000,UTC).astimezone(NY).date()
    b=datetime.fromtimestamp(end_ms/1000,UTC).astimezone(NY).date()
    sch=mcal.get_calendar("NYSE").schedule(start_date=str(a),end_date=str(b))
    return {str(i.date()):(int(r["market_open"].to_pydatetime().timestamp()*1000),int(r["market_close"].to_pydatetime().timestamp()*1000)) for i,r in sch.iterrows()}

def clean_m15(rows,cal):
    out=[]
    for x in rows:
        try:
            t=int(x["timestamp"]); o=float(x["open"]); h=float(x["high"]); l=float(x["low"]); c=float(x["close"]); v=float(x.get("volume") or 0)
        except Exception:
            continue
        d=str(datetime.fromtimestamp(t/1000,UTC).astimezone(NY).date())
        oc=cal.get(d)
        if not oc or not (oc[0]<=t<oc[1]): continue
        out.append({"t":t,"o":o,"h":h,"l":l,"c":c,"v":v,"ct":t+15*60*1000-1})
    d={x["t"]:x for x in out}
    return [d[k] for k in sorted(d)]

def agg_4h(M,cal):
    mp=defaultdict(list)
    for z in M:
        dt=datetime.fromtimestamp(z["t"]/1000,UTC).astimezone(NY)
        day=str(dt.date()); oc=cal.get(day)
        if not oc: continue
        elapsed=(z["t"]-oc[0])//60000
        bucket=0 if elapsed<240 else 1
        mp[(day,bucket)].append(z)
    out=[]
    for _,g in sorted(mp.items()):
        g.sort(key=lambda x:x["t"]); last=g[-1]
        out.append({"t":g[0]["t"],"o":g[0]["o"],"h":max(x["h"] for x in g),"l":min(x["l"] for x in g),
                    "c":last["c"],"v":sum(x["v"] for x in g),"ct":last["ct"]})
    return out

def agg_d1(M,cal):
    mp=defaultdict(list)
    for z in M:
        day=str(datetime.fromtimestamp(z["t"]/1000,UTC).astimezone(NY).date())
        if day in cal: mp[day].append(z)
    out=[]
    for _,g in sorted(mp.items()):
        g.sort(key=lambda x:x["t"]); last=g[-1]
        out.append({"t":g[0]["t"],"o":g[0]["o"],"h":max(x["h"] for x in g),"l":min(x["l"] for x in g),
                    "c":last["c"],"v":sum(x["v"] for x in g),"ct":last["ct"]})
    return out

def stats(ts):
    n=len(ts); wins=sum(float(t["r"])>0 for t in ts); losses=sum(float(t["r"])<0 for t in ts)
    net=sum(float(t["r"]) for t in ts); gp=sum(float(t["r"]) for t in ts if float(t["r"])>0); gl=sum(float(t["r"]) for t in ts if float(t["r"])<0)
    return {"closed_trades":n,"wins":wins,"losses":losses,"win_rate":wins/n if n else None,
            "net_r":net,"avg_r":net/n if n else None,"profit_factor":gp/abs(gl) if gl<0 else None}

def dd(ts):
    q=sorted(ts,key=lambda t:t["exit_t"]); eq=CAP; peak=eq; m=0.0
    for t in q:
        eq+=float(t["pnl"]); peak=max(peak,eq); m=max(m,(peak-eq)/peak if peak else 0)
    return m

def main():
    base=json.loads(BASE.read_text())
    starts={x["symbol"]:int(x["eval_start_ms"]) for x in base["per_symbol"]}
    end_ms=int(datetime.fromisoformat(base["generated_at"]).timestamp()*1000)
    filt=exchange_filters()
    manifest=json.loads((ROOT/"manifest.json").read_text())
    results=[]; errors={}
    old_ds,old_sf=bt.dataset,bt.symbol_filters
    old_cap,old_risk=bt.CAP,bt.RISK; bt.CAP=CAP; bt.RISK=RISK
    try:
        for sym in SUPPORTED:
            try:
                p=ROOT/(sym+".json")
                if not p.exists(): raise RuntimeError("download missing")
                raw=json.loads(p.read_text())
                cal=calendar_map(int(datetime(2026,1,1,tzinfo=UTC).timestamp()*1000),end_ms)
                M=clean_m15(raw,cal)
                H=w.enrich(agg_4h(M,cal)); D=w.enrich(agg_d1(M,cal))
                if len(D)<60 or len(H)<60 or len(M)<500: raise RuntimeError(f"insufficient D={len(D)} H={len(H)} M={len(M)}")
                tick,step,minqty=filt.get(sym,(.01,0,0))
                bt._CACHE.clear(); bt.dataset=lambda _s,D=D,H=H,M=M:(D,H,M); bt.symbol_filters=lambda _s,t=tick,s=step,m=minqty:(t,s,m)
                r=bt.simulate(sym,a_params=A_OFF,b_params=None,start_ms=starts[sym],end_ms=end_ms,
                              fee_bps=FEE_BPS,slippage_bps=SLIPPAGE_BPS,a_mode="snapshot",b_runner_mode="pivot",b_scale_mode="30_30_40")
                ts=[t for t in r["trades"] if t["track"]=="B" and t["reason"]!="OPEN_MARK"]
                results.append({"symbol":sym,"eval_start_ms":starts[sym],"bars":{"m15":len(M),"h4":len(H),"d1":len(D)},
                                "dukascopy":stats(ts),"trades":ts})
                print("RESULT",sym,stats(ts),flush=True)
            except Exception as e:
                errors[sym]=repr(e); print("ERROR",sym,repr(e),flush=True)
    finally:
        bt.dataset,bt.symbol_filters=old_ds,old_sf; bt.CAP,bt.RISK=old_cap,old_risk

    good=[x["symbol"] for x in results]
    spot=[{"symbol":x["symbol"],**t} for x in results for t in x["trades"]]
    binance=[t for t in base["trades"]["RTH"] if t.get("symbol") in good]
    report={
      "generated_at":datetime.now(UTC).isoformat(),
      "purpose":"Same-window comparison: Dukascopy US stock CFD bid proxy vs Binance TradFi futures RTH signal backtest",
      "window":{"source_binance_result":str(BASE),"common_end_ms":end_ms,
                "per_symbol_eval_start_ms":{s:starts[s] for s in good}},
      "assumptions":{
        "strategy":"Track B frozen; exact planned-entry touch",
        "structure":"NYSE RTH 15m -> RTH 4H/stub -> RTH daily",
        "management":"TP1 30%->BE; TP2 30%->TP1; runner 40% confirmed RTH 4H pivot",
        "fees_bps_per_fill":FEE_BPS,"slippage_bps_per_fill":SLIPPAGE_BPS,
        "dukascopy_note":"Free Dukascopy stock CFD BID candles; not consolidated SIP cash prints.",
        "binance_note":"Binance TradFi perpetual candles, restricted here to the same supported symbols and same per-symbol evaluation starts."
      },
      "requested_current53":base["symbols"],
      "dukascopy_supported_requested":list(SUPPORTED),
      "common_symbols":good,
      "unsupported_or_failed":[s for s in base["symbols"] if s not in good],
      "totals":{
        "DUKASCOPY_CFD_PROXY":{**stats(spot),"max_drawdown_fixed_20k":dd(spot)},
        "BINANCE_RTH_SAME_SYMBOLS":{**stats(binance),"max_drawdown_fixed_20k":dd(binance)}
      },
      "per_symbol":[{"symbol":x["symbol"],"eval_start_ms":x["eval_start_ms"],"bars":x["bars"],
                     "DUKASCOPY":x["dukascopy"],
                     "BINANCE":stats([t for t in binance if t.get("symbol")==x["symbol"]])} for x in results],
      "download_manifest":manifest,
      "errors":errors,
      "trades":{"DUKASCOPY":spot,"BINANCE":binance}
    }
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print("FINAL",json.dumps({"common":len(good),"totals":report["totals"],"errors":errors},ensure_ascii=False),flush=True)

if __name__=="__main__": main()
