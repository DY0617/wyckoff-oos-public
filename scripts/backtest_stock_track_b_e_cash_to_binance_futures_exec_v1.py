import csv, io, json, math, os, statistics, sys, time, urllib.error, urllib.parse, urllib.request
from bisect import bisect_left, bisect_right
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

sys.path.insert(0, str(Path(__file__).parent))
import backtest_stock9_spot_vs_binance_same_window as src
import backtest_stock50_track_b_hf_5y_exact_touch as cashhist
import backtest_wyckoff_stock_filter_engine as bt
import wyckoff_status as w

UTC=timezone.utc
NY=ZoneInfo("America/New_York")
TF15=15*60*1000
END_MS=int(datetime(2026,9,29,tzinfo=UTC).timestamp()*1000)-1
CASH_WARMUP_MONTHS=("2025-10","2025-11","2025-12","2026-01","2026-02","2026-03")
HF_BASE="https://huggingface.co/datasets/mito0o852/OHLCV-1m/resolve/main/data"
GETDATA_BASE="https://raw.githubusercontent.com/getdata-finance"
OUT=Path(os.environ.get("OUT","data/validation/stock_track_b_e_cash_to_binance_futures_exec_v1.json"))
TRADES_OUT=Path(os.environ.get("TRADES_OUT","data/validation/stock_track_b_e_cash_to_binance_futures_exec_v1_trades.json"))
REQUESTED=tuple(x for x in os.environ.get("TRADE_SYMS","").split(",") if x)
STOCK50=tuple(cashhist.SYMS)
DAILY_UNIVERSE=tuple(dict.fromkeys(STOCK50+("SPY",)))
DAILY_CACHE=Path("data/validation/stock50_e_daily_recent_cache.json")
A_OFF={"climax_spread_min":999.0,"climax_volume_min":999.0}
FEE_BPS=4.0
SLIP_BPS=2.0
COST_BPS=FEE_BPS+SLIP_BPS
CAP=20000.0
RISK=400.0

def floor_step(x,step):
    return math.floor((x+1e-12)/step)*step if step else x

def ceil_step(x,step):
    return math.ceil((x-1e-12)/step)*step if step else x

def get_json(path,params=None,tries=5):
    return src.get_json(path,params,tries)

def fetch_binance_15m(sym,start_ms):
    out=[];cursor=max(0,int(start_ms))
    while cursor<=END_MS:
        rows=get_json("/fapi/v1/klines",{"symbol":sym+"USDT","interval":"15m","startTime":cursor,"endTime":END_MS,"limit":1000})
        if not rows:break
        for x in rows:
            t=int(x[0]);ct=int(x[6])
            if ct>END_MS:continue
            out.append({"t":t,"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5]),"ct":ct})
        nxt=int(rows[-1][0])+TF15
        if nxt<=cursor:break
        cursor=nxt
        if len(rows)<1000:break
        time.sleep(.01)
    d={z["t"]:z for z in out}
    return [d[k] for k in sorted(d)]

def remote_hf_15m(symbols):
    by={s:[] for s in symbols}
    if not symbols:return by
    con=duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    try:
        for month in CASH_WARMUP_MONTHS:
            url=f"{HF_BASE}/ohlcv_{month}.parquet"
            ph=",".join(["?"]*len(symbols))
            q=f"""
            WITH src AS (
              SELECT ticker, timezone('America/New_York', timestamp) et,
                     open, high, low, close, volume
              FROM read_parquet('{url}')
              WHERE ticker IN ({ph})
            ), rth AS (
              SELECT * FROM src
              WHERE CAST(et AS TIME)>=TIME '09:30:00'
                AND CAST(et AS TIME)<TIME '16:00:00'
            ), agg AS (
              SELECT ticker,time_bucket(INTERVAL '15 minutes',et) b,
                     arg_min(open,et) o,max(high) h,min(low) l,arg_max(close,et) c,sum(volume) v
              FROM rth GROUP BY ticker,b
            )
            SELECT ticker,b,o,h,l,c,v FROM agg ORDER BY ticker,b
            """
            try:
                rows=con.execute(q,list(symbols)).fetchall()
                print("HF",month,"rows",len(rows),flush=True)
                for s,et,o,h,l,c,v in rows:
                    if et.tzinfo is None:et=et.replace(tzinfo=NY)
                    else:et=et.astimezone(NY)
                    t=int(et.astimezone(UTC).timestamp()*1000)
                    by[str(s)].append({"t":t,"o":float(o),"h":float(h),"l":float(l),"c":float(c),"v":float(v or 0),"ct":t+TF15-1})
            except Exception as e:
                print("HF_MONTH_ERROR",month,repr(e),flush=True)
    finally:
        con.close()
    for s in by:
        d={z["t"]:z for z in by[s]}
        by[s]=[d[k] for k in sorted(d)]
    return by

def fetch_getdata(sym,tries=3):
    repo=f"{sym.lower()}-15m-ohlcv-stocks-historical-data"
    url=f"{GETDATA_BASE}/{repo}/main/{sym}_15m.csv"
    last=None
    for n in range(tries):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"stock-futures-exec-v1"})
            with urllib.request.urlopen(req,timeout=45) as r:txt=r.read().decode("utf-8")
            out=[]
            for row in csv.DictReader(io.StringIO(txt)):
                dt=datetime.fromisoformat(row["datetime"].replace("Z","+00:00"))
                if dt.tzinfo is None:dt=dt.replace(tzinfo=UTC)
                t=int(dt.astimezone(UTC).timestamp()*1000)
                if t>END_MS:continue
                z={"t":t,"o":float(row["open"]),"h":float(row["high"]),"l":float(row["low"]),
                   "c":float(row["close"]),"v":float(row.get("volume") or 0),"ct":t+TF15-1}
                out.append(z)
            return src.rth_only(out)
        except urllib.error.HTTPError as e:
            if e.code==404:return []
            last=e
        except Exception as e:last=e
        time.sleep(1+n)
    print("GETDATA_ERROR",sym,repr(last),flush=True)
    return []

def merge_cash(a,b):
    d={z["t"]:z for z in a}
    for z in b:d[z["t"]]=z
    return [d[k] for k in sorted(d)]

def stooq_symbol(sym):
    # Stooq accepts most US equity / ETF tickers as lower-case <ticker>.us.
    return sym.lower().replace(".","-")+".us"

def fetch_stooq_daily(sym,tries=3):
    s=urllib.parse.quote(stooq_symbol(sym))
    url=f"https://stooq.com/q/d/l/?s={s}&d1=20250101&d2=20260928&i=d"
    last=None
    for n in range(tries):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"stock-futures-exec-v1"})
            with urllib.request.urlopen(req,timeout=30) as r:txt=r.read().decode("utf-8")
            rows=[]
            for row in csv.DictReader(io.StringIO(txt)):
                ds=row.get("Date")
                if not ds or not row.get("Close"):continue
                try:
                    d=date.fromisoformat(ds)
                    c=float(row["Close"])
                except Exception:
                    continue
                if c>0:rows.append({"date":d,"c":c})
            rows.sort(key=lambda x:x["date"])
            return enrich_daily(rows)
        except Exception as e:
            last=e;time.sleep(1+n)
    print("STOOQ_ERROR",sym,repr(last),flush=True)
    return []

def enrich_daily(rows):
    e20=e50=None; a20=2/21; a50=2/51
    closes=[]
    out=[]
    for z in rows:
        c=float(z["c"]);closes.append(c)
        e20=c if e20 is None else a20*c+(1-a20)*e20
        e50=c if e50 is None else a50*c+(1-a50)*e50
        q=dict(z);q["ema20"]=e20;q["ema50"]=e50
        q["ret20"]=c/closes[-21]-1 if len(closes)>=21 and closes[-21]>0 else None
        out.append(q)
    return out

def load_daily_universe():
    if DAILY_CACHE.exists():
        raw=json.loads(DAILY_CACHE.read_text(encoding="utf-8"))
        out={}
        for s,rows in raw.get("symbols",{}).items():
            q=[]
            for z in rows:
                x=dict(z);x["date"]=date.fromisoformat(x["date"]);q.append(x)
            if len(q)>=55:out[s]=q
        print("DAILY_CACHE_LOADED",len(out),flush=True)
        return out
    out={}
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs={ex.submit(fetch_stooq_daily,s):s for s in DAILY_UNIVERSE}
        for fut in as_completed(futs):
            s=futs[fut]
            try:
                rows=fut.result()
                if len(rows)>=55:out[s]=rows
                print("DAILY",s,len(rows),flush=True)
            except Exception as e:
                print("DAILY_ERROR",s,repr(e),flush=True)
    return out

def latest_daily_idx(rows,entry_t):
    if not rows:return -1
    local_day=datetime.fromtimestamp(entry_t/1000,UTC).astimezone(NY).date()
    ds=[x["date"] for x in rows]
    return bisect_left(ds,local_day)-1

def estate(sym,daily,ts):
    D=daily.get(sym);S=daily.get("SPY")
    if not D or not S:return None
    local_day=datetime.fromtimestamp(ts/1000,UTC).astimezone(NY).date()
    i=latest_daily_idx(D,ts);si=latest_daily_idx(S,ts)
    if i<50 or si<50:return None
    # Do not use stale series as if they were current breadth / RS data.
    if (local_day-D[i]["date"]).days>7 or (local_day-S[si]["date"]).days>7:return None
    rr=D[i].get("ret20");sr=S[si].get("ret20")
    if rr is None or sr is None:return None
    s=S[si]
    votes=int(s["c"]>s["ema50"])+int(s["ema20"]>s["ema50"])+int(sr>0)
    eligible=above=0
    for u,U in daily.items():
        if u=="SPY" and u not in STOCK50:continue
        ui=latest_daily_idx(U,ts)
        if ui>=50 and U[ui].get("ema50") is not None and (local_day-U[ui]["date"]).days<=7:
            eligible+=1;above+=int(U[ui]["c"]>U[ui]["ema50"])
    breadth=above/eligible if eligible else None
    return {"spy_regime":votes>=2,"rs_ok":rr>=sr,
            "breadth":breadth,"breadth_n":eligible,
            "breadth_ok":breadth is not None and breadth>=.50,
            "stock_ret20":rr,"spy_ret20":sr}

def eligible(sym,daily,ts,direction):
    if direction!="LONG":return False
    st=estate(sym,daily,ts)
    return bool(st and st["spy_regime"] and st["rs_ok"] and st["breadth_ok"])

def exchange_universe():
    ex=get_json("/fapi/v1/exchangeInfo")
    meta={x.get("symbol"):x for x in ex.get("symbols",[])}
    syms=[]
    for s in STOCK50:
        m=meta.get(s+"USDT")
        if not m:continue
        if m.get("status") not in (None,"TRADING"):continue
        syms.append(s)
    if REQUESTED:
        syms=[s for s in syms if s in set(REQUESTED)]
    return syms,meta

def cash_engine(sym,M,daily,eval_start,eval_end):
    bars=cashhist.apply_splits(M,cashhist.detect_splits(M))
    H=w.enrich(src.aggregate_4h(src.rth_only(bars)))
    D=w.enrich(src.aggregate_daily(src.rth_only(bars)))
    old_dataset,old_filters=bt.dataset,bt.symbol_filters
    old_cap,old_risk=bt.CAP,bt.RISK
    bt.CAP=CAP;bt.RISK=RISK
    try:
        bt._CACHE.clear()
        bt.dataset=lambda _s,D=D,H=H,M=bars:(D,H,M)
        bt.symbol_filters=lambda _s:(0.01,0.0,0.0)
        def trig_filter(_sym,p,trigger_open_ms):
            return eligible(sym,daily,trigger_open_ms,p["direction"])
        r=bt.simulate(sym,A_OFF,{},eval_start,eval_end,FEE_BPS,SLIP_BPS,
                      a_mode="snapshot",b_runner_mode="pivot",b_scale_mode="15_25_60",
                      trigger_filter=trig_filter)
        ts=[{"symbol":sym,**t} for t in r["trades"]
            if t["track"]=="B" and t["direction"]=="LONG" and t["reason"]!="OPEN_MARK"]
        return bars,H,D,ts,r
    finally:
        bt.dataset,bt.symbol_filters=old_dataset,old_filters
        bt.CAP,bt.RISK=old_cap,old_risk

def filters(meta):
    return src.filters(meta)

def latest_bar_before(bars,ts):
    tt=[z["t"] for z in bars]
    i=bisect_right(tt,ts)-1
    return bars[i] if i>=0 else None

def build_trail_events(H,cashM,futM,tick):
    cash_t=[z["t"] for z in cashM]; fut_by={z["t"]:z for z in futM}
    out=[]
    for i in range(1,len(H)-1):
        atr=H[i].get("atr")
        if not atr:continue
        if not (H[i]["l"]<H[i-1]["l"] and H[i]["l"]<H[i+1]["l"]):continue
        confirm_ct=H[i+1].get("ct",H[i+1]["t"]+4*60*60*1000-1)
        ci=bisect_right(cash_t,confirm_ct)-1
        if ci<0:continue
        cb=cashM[ci];fb=fut_by.get(cb["t"])
        if not fb or cb["c"]<=0:continue
        ratio=fb["c"]/cb["c"]
        px=(H[i]["l"]-.30*atr)*ratio
        px=floor_step(px,tick)
        out.append({"effective_after":confirm_ct,"price":px,"cash_price":H[i]["l"]-.30*atr,
                    "basis_ratio":ratio,"cash_ref_t":cb["t"]})
    return out

def is_rth_t(ts):
    dt=datetime.fromtimestamp(ts/1000,UTC).astimezone(NY)
    m=dt.hour*60+dt.minute
    return dt.weekday()<5 and 570<=m<960

def execution_reference(mode,trade,cashM,futM):
    cash_by={z["t"]:z for z in cashM}; fut_by={z["t"]:z for z in futM}
    t=trade["entry_t"]; cb=cash_by.get(t);fb=fut_by.get(t)
    if mode=="SAME_BAR_CLOSE":
        if not cb or not fb:return None
        return {"t":t,"cash_ref":cb["c"],"fut_entry":fb["c"],"fut_index":next((i for i,z in enumerate(futM) if z["t"]==t),None),"manage_from_next":True}
    # NEXT_BAR_OPEN: require next same-session RTH cash bar and matching futures bar.
    times=[z["t"] for z in cashM]
    i=bisect_right(times,t)
    if i>=len(cashM):return None
    nb=cashM[i]
    d0=datetime.fromtimestamp(t/1000,UTC).astimezone(NY).date()
    d1=datetime.fromtimestamp(nb["t"]/1000,UTC).astimezone(NY).date()
    if d1!=d0:return None
    nf=fut_by.get(nb["t"])
    if not nf:return None
    fi=next((j for j,z in enumerate(futM) if z["t"]==nb["t"]),None)
    return {"t":nb["t"],"cash_ref":nb["o"],"fut_entry":nf["o"],"fut_index":fi,"manage_from_next":False}

def simulate_future(mode,trade,cashM,H,futM,meta):
    ref=execution_reference(mode,trade,cashM,futM)
    if not ref or ref["fut_index"] is None or not ref["cash_ref"] or ref["cash_ref"]<=0:
        return {"status":"NO_MATCH"}
    tick,step,minqty=filters(meta)
    ratio=ref["fut_entry"]/ref["cash_ref"]
    entry=ref["fut_entry"]
    stop=floor_step(float(trade["stop"])*ratio,tick)
    tp1=floor_step(float(trade["tp1"])*ratio,tick) if trade.get("tp1") is not None else None
    tp2=floor_step(float(trade["target"])*ratio,tick)
    if tp1 is None or not (stop<entry<tp1<tp2):
        return {"status":"LATE_INVALID","entry_t":ref["t"],"entry":entry,"stop":stop,"tp1":tp1,"tp2":tp2,"basis_bps":(ratio-1)*10000}
    risk=entry-stop
    raw_size=RISK/risk
    size=floor_step(raw_size,step) if step else raw_size
    if size<=0 or (minqty and size<minqty):
        return {"status":"SIZE_INVALID"}
    trails=build_trail_events(H,cashM,futM,tick)
    ti=0
    while ti<len(trails) and trails[ti]["effective_after"]<ref["t"]:ti+=1
    remain=1.0;realized=-size*entry*COST_BPS/10000.0
    cur_stop=stop;tp1_done=False;tp2_done=False;events=[]
    start_i=ref["fut_index"]+(1 if ref["manage_from_next"] else 0)
    last=None
    for j in range(start_i,len(futM)):
        z=futM[j]
        if z["t"]>END_MS:break
        # Cash pivot trail becomes actionable only after it was fully confirmed.
        if tp2_done:
            while ti<len(trails) and trails[ti]["effective_after"]<z["t"]:
                px=trails[ti]["price"]
                if px>cur_stop:
                    cur_stop=px
                    events.append({"type":"TRAIL","t":z["t"],"price":cur_stop,"source_cash_t":trails[ti]["cash_ref_t"]})
                ti+=1
        last=z
        if z["l"]<=cur_stop:
            realized += remain*(cur_stop-entry)*size - remain*size*cur_stop*COST_BPS/10000.0
            events.append({"type":"BE" if abs(cur_stop-entry)<1e-12 else "STOP","t":z["t"],"price":cur_stop,"fraction":remain})
            remain=0;break
        if not tp1_done and z["h"]>=tp1:
            frac=.15
            realized += frac*(tp1-entry)*size - frac*size*tp1*COST_BPS/10000.0
            remain-=frac;tp1_done=True
            events.append({"type":"TP1","t":z["t"],"price":tp1,"fraction":frac})
            if cur_stop<entry:
                cur_stop=entry;events.append({"type":"BE_MOVE","t":z["t"],"price":entry})
        if not tp2_done and z["h"]>=tp2:
            frac=.25
            realized += frac*(tp2-entry)*size - frac*size*tp2*COST_BPS/10000.0
            remain-=frac;tp2_done=True
            events.append({"type":"TP2","t":z["t"],"price":tp2,"fraction":frac})
            if cur_stop<tp1:
                cur_stop=tp1;events.append({"type":"STOP_TO_TP1","t":z["t"],"price":tp1})
    if remain>1e-12:
        if not last:return {"status":"NO_MANAGEMENT_DATA"}
        mark=last["c"]
        realized += remain*(mark-entry)*size - remain*size*mark*COST_BPS/10000.0
        events.append({"type":"OPEN_MARK","t":last["t"],"price":mark,"fraction":remain})
        reason="OPEN_MARK"
    else:
        reason=events[-1]["type"]
    exit_t=events[-1]["t"] if events else ref["t"]
    return {
      "status":"EXECUTED","mode":mode,"entry_t":ref["t"],"exit_t":exit_t,
      "entry":entry,"stop":stop,"tp1":tp1,"tp2":tp2,"size":size,
      "basis_ratio":ratio,"basis_bps":(ratio-1)*10000,
      "reason":reason,"pnl":realized,"r":realized/RISK,"events":events,
      "outside_rth_exit":not is_rth_t(exit_t)
    }

def stats(ts):
    closed=[t for t in ts if t.get("status")=="EXECUTED" and t.get("reason")!="OPEN_MARK"]
    n=len(closed);wins=sum(t["pnl"]>0 for t in closed);neg=[t["r"] for t in closed if t["r"]<0];pos=[t["r"] for t in closed if t["r"]>0]
    eq=CAP;peak=CAP;mdd=0;st=mx=0
    for t in sorted(closed,key=lambda x:x["exit_t"]):
        eq+=t["pnl"];peak=max(peak,eq);mdd=max(mdd,(peak-eq)/peak if peak else 0)
        if t["pnl"]<0:st+=1;mx=max(mx,st)
        else:st=0
    return {
      "closed":n,"wins":wins,"losses":sum(t["pnl"]<0 for t in closed),
      "win_rate":wins/n if n else None,"net_r":sum(t["r"] for t in closed),
      "avg_r":statistics.fmean([t["r"] for t in closed]) if closed else None,
      "profit_factor":sum(pos)/abs(sum(neg)) if neg else None,
      "max_drawdown_fixed_20k":mdd,"max_consecutive_losses":mx,
      "outside_rth_exits":sum(t.get("outside_rth_exit") for t in closed),
      "outside_rth_exit_rate":sum(t.get("outside_rth_exit") for t in closed)/n if n else None
    }

def main():
    futures_syms,exmeta=exchange_universe()
    print("FUTURES_UNIVERSE",futures_syms,flush=True)
    # Recent cash sample availability is probed per futures-supported symbol.
    hf=remote_hf_15m(futures_syms)
    gd={}
    with ThreadPoolExecutor(max_workers=10) as ex:
        fs={ex.submit(fetch_getdata,s):s for s in futures_syms}
        for fut in as_completed(fs):
            s=fs[fut]
            gd[s]=fut.result()
            print("GETDATA",s,len(gd[s]),flush=True)
    cash={s:merge_cash(hf.get(s,[]),gd.get(s,[])) for s in futures_syms}
    daily=load_daily_universe()
    print("DAILY_AVAILABLE",len(daily),sorted(daily),flush=True)

    per={};all_modes={"SAME_BAR_CLOSE":[],"NEXT_BAR_OPEN":[]};cash_bench=[];errors={}
    for sym in futures_syms:
        try:
            M=cash.get(sym,[])
            if len(M)<500:
                print("SKIP_CASH",sym,len(M),flush=True);continue
            meta=exmeta[sym+"USDT"]
            onboard=int(meta.get("onboardDate") or datetime(2026,1,1,tzinfo=UTC).timestamp()*1000)
            fut=fetch_binance_15m(sym,onboard)
            if len(fut)<100:
                print("SKIP_FUT",sym,len(fut),flush=True);continue
            eval_start=max(onboard,fut[0]["t"],int(datetime(2026,1,1,tzinfo=UTC).timestamp()*1000))
            bars,H,D,trades,r=cash_engine(sym,M,daily,eval_start,END_MS)
            print("CASH_SIGNALS",sym,len(trades),"cash",len(M),"fut",len(fut),flush=True)
            symout={"cash_bars":len(M),"futures_bars":len(fut),"eval_start":eval_start,
                    "cash_signals":len(trades),"modes":{}}
            active_until={m:-1 for m in all_modes}
            for mode in all_modes:
                arr=[];sk_overlap=0
                for t in sorted(trades,key=lambda z:z["entry_t"]):
                    x=simulate_future(mode,t,bars,H,fut,meta)
                    x={"symbol":sym,"cash_entry_t":t["entry_t"],"cash_entry":t["entry"],"cash_stop":t["stop"],
                       "cash_tp1":t.get("tp1"),"cash_tp2":t["target"],"cash_r":t["r"],**x}
                    if x.get("status")=="EXECUTED":
                        if x["entry_t"]<=active_until[mode]:
                            x["status"]="OVERLAP_SKIPPED";sk_overlap+=1
                        else:
                            active_until[mode]=x["exit_t"]
                    arr.append(x)
                    if x.get("status")=="EXECUTED":all_modes[mode].append(x)
                symout["modes"][mode]={
                    "attempts":len(arr),"executed":sum(x.get("status")=="EXECUTED" for x in arr),
                    "no_match":sum(x.get("status")=="NO_MATCH" for x in arr),
                    "late_invalid":sum(x.get("status")=="LATE_INVALID" for x in arr),
                    "overlap_skipped":sk_overlap,"summary":stats(arr),"trades":arr}
            cash_bench += [{"symbol":sym,**t} for t in trades]
            per[sym]=symout
        except Exception as e:
            errors[sym]=repr(e);print("SYMBOL_ERROR",sym,repr(e),flush=True)

    # Matched-signal cash benchmark per mode and execution diagnostics.
    report_modes={}
    for mode,fts in all_modes.items():
        fts=[x for x in fts if x.get("status")=="EXECUTED"]
        keys={(x["symbol"],x["cash_entry_t"]) for x in fts}
        cb=[t for t in cash_bench if (t["symbol"],t["entry_t"]) in keys]
        closed_fts=[x for x in fts if x["reason"]!="OPEN_MARK"]
        closed_keys={(x["symbol"],x["cash_entry_t"]) for x in closed_fts}
        cb_closed=[t for t in cb if (t["symbol"],t["entry_t"]) in closed_keys]
        basis=[x["basis_bps"] for x in fts]
        diffs=[]
        signs=0
        bycash={(t["symbol"],t["entry_t"]):t for t in cb_closed}
        for x in closed_fts:
            c=bycash.get((x["symbol"],x["cash_entry_t"]))
            if c:
                diffs.append(x["r"]-c["r"])
                signs+=int((x["r"]>0)==(c["r"]>0))
        fs=stats(fts)
        report_modes[mode]={
          "futures":fs,
          "executed_total":len(fts),
          "closed_matched":len(closed_fts),
          "cash_benchmark_on_closed_matched":{
             "trades":len(cb_closed),"net_r":sum(t["r"] for t in cb_closed),
             "avg_r":statistics.fmean([t["r"] for t in cb_closed]) if cb_closed else None,
             "win_rate":sum(t["r"]>0 for t in cb_closed)/len(cb_closed) if cb_closed else None
          },
          "execution_delta_r":{"sum":sum(diffs),"mean":statistics.fmean(diffs) if diffs else None},
          "outcome_sign_match_rate":signs/len(diffs) if diffs else None,
          "entry_basis_bps":{
             "n":len(basis),"mean":statistics.fmean(basis) if basis else None,
             "median":statistics.median(basis) if basis else None,
             "mean_abs":statistics.fmean(abs(x) for x in basis) if basis else None,
             "median_abs":statistics.median(abs(x) for x in basis) if basis else None
          }
        }

    total_cash=len(cash_bench)
    report={
      "generated_at":datetime.now(UTC).isoformat(),
      "purpose":"Cash Track-B E signal -> Binance TradFi futures execution calibration",
      "period":{"end_exclusive":"2026-09-29T00:00:00Z"},
      "futures_supported_stock50":futures_syms,
      "cash_signals_total":total_cash,
      "daily_filter_symbols_available":len(daily),
      "rules":{
        "signal":"cash RTH Track B + E at trigger, LONG only",
        "management":"15/25/60; TP1=>BE; TP2=>TP1; cash confirmed 4H pivot trail mapped through contemporaneous basis",
        "entry_modes":["SAME_BAR_CLOSE","NEXT_BAR_OPEN"],
        "after_hours_management":True,
        "cost_bps_per_fill":COST_BPS,"fixed_risk_usd":RISK
      },
      "modes":report_modes,
      "per_symbol":{s:{k:v for k,v in x.items() if k!="modes"}|{"modes":{m:{k:v for k,v in z.items() if k!="trades"} for m,z in x["modes"].items()}} for s,x in per.items()},
      "errors":errors,
      "limitations":[
        "Binance TradFi futures history is short and differs by symbol; this is execution calibration, not long-horizon strategy validation.",
        "Recent cash intraday history stitches HF/Finnhub history to public getdata-finance 15m samples when available.",
        "E daily state uses Stooq daily data for the available breadth universe; small vendor-adjustment differences versus the long-horizon research source are possible.",
        "Cash entry touch is only timestamped to a 15m bar. SAME_BAR_CLOSE and NEXT_BAR_OPEN bracket practical alert/execution delay rather than reconstructing an unknown intrabar tick path."
      ]
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    TRADES_OUT.write_text(json.dumps({"report":report,"cash_trades":cash_bench,
                                     "futures_trades":all_modes},ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    print("FINAL",json.dumps(report,ensure_ascii=False,indent=2),flush=True)

if __name__=="__main__":
    main()
