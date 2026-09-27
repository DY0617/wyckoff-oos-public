import json, math, sys, time, urllib.parse, urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal

sys.path.insert(0, str(Path(__file__).parent))
import backtest_wyckoff_entry_timing as bt
import wyckoff_status as w

PROXY="https://zmbeamtclazjtfxyysre.supabase.co/functions/v1/stock-tradifi-history-export"
OUT=Path("data/validation/stock53_rth_entry_timing_abc.json")
SYMS=(
"AAPL","AMZN","AVGO","CRCL","DELL","MSFT","MU","SNDK","SNXX","SOXL","SPCX",
"AMD","BABA","INTC","JPM","KORU","MSTR","NFLX","SKHY","SMCI","SOXS","V",
"COST","GOOGL","LLY","META","NBIS","NVDA","QQQ","TSLA","UBER","WMT",
"AMAT","CAT","DRAM","EWY","HD","MRVL","MUU","ORCL","SPY","TSM",
"AAOI","AXTI","BE","COIN","CRM","CSCO","DIS","HOOD","IBM","LITE","TQQQ"
)
FEE_BPS=4.0
SLIPPAGE_BPS=2.0
CAP=20000.0
RISK=400.0
A_OFF={"climax_spread_min":999.0,"climax_volume_min":999.0}
TF15=15*60*1000
TF4H=4*60*60*1000
TFD=24*60*60*1000
UTC=timezone.utc
NY=ZoneInfo("America/New_York")

def get_json(path, params=None, tries=6):
    kind={"/fapi/v1/exchangeInfo":"exchangeInfo","/fapi/v1/time":"time","/fapi/v1/klines":"klines"}[path]
    p={"kind":kind}
    if params: p.update(params)
    url=PROXY+"?"+urllib.parse.urlencode(p)
    last=None
    for n in range(tries):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"wyckoff-rth-compare/1.0"})
            with urllib.request.urlopen(req,timeout=60) as r:
                return json.loads(r.read())
        except Exception as e:
            last=e
            if n+1>=tries: raise
            time.sleep(min(10,1.5*(n+1)))
    raise last

def fetch_15m(symbol,start_ms,end_ms):
    out=[]; cursor=int(start_ms); calls=0
    while cursor<=end_ms:
        rows=get_json("/fapi/v1/klines",{"symbol":symbol+"USDT","interval":"15m","startTime":cursor,"endTime":end_ms,"limit":1000})
        calls+=1
        if not rows: break
        for x in rows:
            ct=int(x[6])
            if ct>end_ms: continue
            out.append({"t":int(x[0]),"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5]),"ct":ct})
        nxt=int(rows[-1][0])+TF15
        if nxt<=cursor: break
        cursor=nxt
        if len(rows)<1000: break
        time.sleep(.025)
    d={x["t"]:x for x in out}
    return [d[k] for k in sorted(d)],calls

def filters(meta):
    by={x.get("filterType"):x for x in meta.get("filters",[])}
    pf=by.get("PRICE_FILTER",{}); lf=by.get("LOT_SIZE",{})
    return float(pf.get("tickSize") or 0.01),float(lf.get("stepSize") or 0),float(lf.get("minQty") or 0)

def agg_utc(bars,step):
    mp=defaultdict(list)
    for z in bars:
        k=(z["t"]//step)*step
        mp[k].append(z)
    out=[]
    for k,g in sorted(mp.items()):
        g.sort(key=lambda x:x["t"]); last=g[-1]
        out.append({"t":k,"o":g[0]["o"],"h":max(x["h"] for x in g),"l":min(x["l"] for x in g),
                    "c":last["c"],"v":sum(x["v"] for x in g),"ct":last["ct"]})
    return out

def calendar_map(start_ms,end_ms):
    start=datetime.fromtimestamp(start_ms/1000,UTC).astimezone(NY).date()
    end=datetime.fromtimestamp(end_ms/1000,UTC).astimezone(NY).date()
    sch=mcal.get_calendar("NYSE").schedule(start_date=str(start),end_date=str(end))
    out={}
    for idx,row in sch.iterrows():
        o=row["market_open"].to_pydatetime()
        c=row["market_close"].to_pydatetime()
        out[str(idx.date())]=(int(o.timestamp()*1000),int(c.timestamp()*1000))
    return out

def rth_bars(bars,cal):
    out=[]
    for z in bars:
        d=str(datetime.fromtimestamp(z["t"]/1000,UTC).astimezone(NY).date())
        oc=cal.get(d)
        if oc and oc[0]<=z["t"]<oc[1]:
            out.append(z)
    return out

def agg_rth_4h(bars,cal):
    mp=defaultdict(list)
    for z in bars:
        dt=datetime.fromtimestamp(z["t"]/1000,UTC).astimezone(NY)
        d=str(dt.date()); oc=cal.get(d)
        if not oc or not (oc[0]<=z["t"]<oc[1]): continue
        elapsed=(z["t"]-oc[0])//60000
        bucket=0 if elapsed<240 else 1
        mp[(d,bucket)].append(z)
    out=[]
    for _,g in sorted(mp.items()):
        g.sort(key=lambda x:x["t"]); last=g[-1]
        out.append({"t":g[0]["t"],"o":g[0]["o"],"h":max(x["h"] for x in g),"l":min(x["l"] for x in g),
                    "c":last["c"],"v":sum(x["v"] for x in g),"ct":last["ct"]})
    return out

def agg_rth_daily(bars,cal):
    mp=defaultdict(list)
    for z in bars:
        dt=datetime.fromtimestamp(z["t"]/1000,UTC).astimezone(NY)
        d=str(dt.date()); oc=cal.get(d)
        if oc and oc[0]<=z["t"]<oc[1]:
            mp[d].append(z)
    out=[]
    for _,g in sorted(mp.items()):
        g.sort(key=lambda x:x["t"]); last=g[-1]
        out.append({"t":g[0]["t"],"o":g[0]["o"],"h":max(x["h"] for x in g),"l":min(x["l"] for x in g),
                    "c":last["c"],"v":sum(x["v"] for x in g),"ct":last["ct"]})
    return out

def run_mode(sym,D,H,M,tick,step,minqty,start_ms,end_ms,entry_mode):
    if len(D)<60 or len(H)<60 or len(M)<500:
        return {"ok":False,"reason":f"insufficient D={len(D)} H={len(H)} M={len(M)}","trades":[]}
    old_dataset,old_filters=bt.dataset,bt.symbol_filters
    try:
        bt._CACHE.clear()
        bt.dataset=lambda _s,D=D,H=H,M=M:(D,H,M)
        bt.symbol_filters=lambda _s:(tick,step,minqty)
        r=bt.simulate(sym,a_params=A_OFF,b_params=None,start_ms=start_ms,end_ms=end_ms,
                      fee_bps=FEE_BPS,slippage_bps=SLIPPAGE_BPS,
                      a_mode="snapshot",b_runner_mode="pivot",b_scale_mode="30_30_40",entry_mode=entry_mode)
        ts=[t for t in r["trades"] if t["track"]=="B" and t["reason"]!="OPEN_MARK"]
        return {"ok":True,"trades":ts,"setups":r.get("setups",{}).get("B",0)}
    finally:
        bt.dataset,bt.symbol_filters=old_dataset,old_filters

def stats(trades):
    n=len(trades); wins=sum(t["pnl"]>0 for t in trades); losses=sum(t["pnl"]<0 for t in trades)
    net=sum(t["r"] for t in trades)
    gp=sum(t["r"] for t in trades if t["r"]>0); gl=sum(t["r"] for t in trades if t["r"]<0)
    return {"closed_trades":n,"wins":wins,"losses":losses,
            "win_rate":wins/n if n else None,"net_r":net,"avg_r":net/n if n else None,
            "profit_factor":gp/abs(gl) if gl<0 else None}

def dd_stats(trades):
    q=sorted(trades,key=lambda t:t["exit_t"])
    eq=CAP; peak=eq; mdd=0.0
    for t in q:
        eq+=t["pnl"]; peak=max(peak,eq); mdd=max(mdd,(peak-eq)/peak if peak else 0)
    return mdd

def direction_stats(trades):
    return {d:stats([t for t in trades if t["direction"]==d]) for d in ("LONG","SHORT")}

def entry_extra(trades):
    preopen=0; confirmed_close=0
    for t in trades:
        et=datetime.fromtimestamp(t["entry_t"]/1000,UTC).astimezone(NY)
        if et.hour==9 and et.minute<30:
            preopen+=1
        if abs(float(t.get("actual_entry",t["entry"]))-float(t.get("planned_entry",t["entry"])))>1e-12:
            confirmed_close+=1
    return {"preopen_fills":preopen,"confirmation_close_entries":confirmed_close}

def main():
    ex=get_json("/fapi/v1/exchangeInfo"); meta={x["symbol"]:x for x in ex.get("symbols",[])}
    end_ms=int(get_json("/fapi/v1/time")["serverTime"])-1
    all_results=[]; errors={}
    old_cap,old_risk=bt.CAP,bt.RISK; bt.CAP=CAP;bt.RISK=RISK

    def fetch_one(sym):
        m=meta[sym+"USDT"]
        onboard=int(m.get("onboardDate") or 0)
        M,calls=fetch_15m(sym,onboard,end_ms)
        return sym,m,onboard,M,calls

    fetched={}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futs={pool.submit(fetch_one,s):s for s in SYMS}
        for fut in as_completed(futs):
            sym=futs[fut]
            try:
                sym,m,onboard,M,calls=fut.result()
                fetched[sym]=(m,onboard,M,calls)
                print("FETCHED",sym,len(M),"calls",calls,flush=True)
            except Exception as e:
                errors[sym]=repr(e); print("FETCH_ERROR",sym,repr(e),flush=True)

    try:
        for idx,sym in enumerate(SYMS,1):
            if sym not in fetched: continue
            try:
                m,onboard,M,calls=fetched[sym]
                cal=calendar_map(onboard,end_ms)
                R_M=rth_bars(M,cal)
                R_H=w.enrich(agg_rth_4h(M,cal))
                R_D=w.enrich(agg_rth_daily(M,cal))
                tick,step,minqty=filters(m)
                if len(R_D)<60 or len(R_H)<60:
                    raise RuntimeError(f"insufficient RTH warmup D={len(R_D)} H={len(R_H)}")
                eval_start=R_D[59]["ct"]+1
                modes={}
                for mode in ("RTH","PRE15","PRE15_CONFIRM"):
                    modes[mode]=run_mode(sym,R_D,R_H,M,tick,step,minqty,eval_start,end_ms,mode)
                all_results.append({
                    "symbol":sym,"onboard_ms":onboard,"eval_start_ms":eval_start,"end_ms":end_ms,
                    "bars":{"m15_all":len(M),"m15_rth":len(R_M),"rth_h4":len(R_H),"rth_d1":len(R_D)},
                    "api_calls":calls,**modes
                })
                print("RESULT",idx,len(SYMS),sym,
                      *(f"{m0} {stats(modes[m0]['trades'])}" for m0 in ("RTH","PRE15","PRE15_CONFIRM")),flush=True)
            except Exception as e:
                errors[sym]=repr(e); print("ERROR",sym,repr(e),flush=True)
    finally:
        bt.CAP,bt.RISK=old_cap,old_risk

    eligible=[x for x in all_results if all(x[m]["ok"] for m in ("RTH","PRE15","PRE15_CONFIRM"))]
    agg={}
    for mode in ("RTH","PRE15","PRE15_CONFIRM"):
        ts=[]
        for x in eligible:
            ts += [{"symbol":x["symbol"],**t} for t in x[mode]["trades"]]
        agg[mode]={
            **stats(ts),
            "max_drawdown_fixed_20k":dd_stats(ts),
            "by_direction":direction_stats(ts),
            **entry_extra(ts)
        }

    report={
        "generated_at":datetime.now(UTC).isoformat(),
        "purpose":"Current 53-stock Binance TradFi RTH entry timing A/B/C comparison",
        "symbols":list(SYMS),
        "comparison":{
            "shared_structure":"NYSE official calendar RTH 15m -> RTH 4H/stub + RTH daily",
            "A_RTH":"Current production behavior: exact-touch entry from 09:30 ET onward.",
            "B_PRE15":"Allow exact-touch from 09:15 ET. A pre-open touch fills immediately at planned entry.",
            "C_PRE15_CONFIRM":"If 09:15-09:30 touches first, wait for the 09:30-09:45 RTH candle to close on the favorable side and enter at that close; if confirmation fails, later RTH exact-touch remains eligible.",
            "entry_fill":"Exact touch low <= planned_entry <= high for limit-style fills; C confirmation entry uses the confirming RTH 15m close as actual entry.",
            "evaluation_start":"per symbol after 60 completed RTH daily bars",
            "costs":{"fee_bps_per_fill":FEE_BPS,"slippage_bps_per_fill":SLIPPAGE_BPS},
            "management":"TP1 30% -> BE; TP2 30% -> TP1; runner 40% confirmed RTH 4H pivot; after entry management observes all Binance 15m"
        },
        "eligible_symbols":[x["symbol"] for x in eligible],
        "totals":agg,
        "per_symbol":[{
            "symbol":x["symbol"],
            **{m:stats(x[m]["trades"]) for m in ("RTH","PRE15","PRE15_CONFIRM")},
            "bars":x["bars"],"eval_start_ms":x["eval_start_ms"]
        } for x in all_results],
        "errors":errors,
        "trades":{
            m:[{"symbol":x["symbol"],**t} for x in eligible for t in x[m]["trades"]]
            for m in ("RTH","PRE15","PRE15_CONFIRM")
        }
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("FINAL",json.dumps({"eligible":len(eligible),"totals":agg,"errors":errors},ensure_ascii=False),flush=True)

if __name__=="__main__":
    main()
