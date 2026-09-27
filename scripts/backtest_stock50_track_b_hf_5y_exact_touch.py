import json, math, sys, time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

sys.path.insert(0, str(Path(__file__).parent))
import backtest_wyckoff_5y_exact_touch as bt
import wyckoff_status as w

SYMS=(
    "AAPL","AMZN","AVGO","CRCL","MSFT","MU","SNDK","SNXX","SOXL","SPCX",
    "AMD","BABA","INTC","JPM","KORU","MSTR","NFLX","SKHY","SOXS","V",
    "COST","GOOGL","LLY","META","NBIS","NVDA","QQQ","TSLA","UBER","WMT",
    "AMAT","CAT","DRAM","EWY","HD","MRVL","MUU","ORCL","SPY","TSM",
    "AAOI","BE","COIN","CRM","CSCO","DIS","HOOD","IBM","LITE","TQQQ"
)

# Hugging Face source is complete through 2026-03. Use the latest exact continuous five-year window.
EVAL_START=datetime(2021,4,1,tzinfo=timezone.utc)
EVAL_END=datetime(2026,4,1,tzinfo=timezone.utc)  # exclusive
WARMUP_START=datetime(2020,10,1,tzinfo=timezone.utc)
HF_BASE="https://huggingface.co/datasets/mito0o852/OHLCV-1m/resolve/main/data"
OUT=Path("data/validation/stock50_track_b_hf_5y_exact_touch.json")
NY=ZoneInfo("America/New_York")
UTC=timezone.utc

# Same conservative transaction-cost assumption used in the crypto robustness work.
FEE_BPS=4.0
SLIPPAGE_BPS=2.0
A_OFF={"climax_spread_min":999.0,"climax_volume_min":999.0}

def month_iter(start,end):
    y,m=start.year,start.month
    while (y,m)<(end.year,end.month):
        yield y,m
        m+=1
        if m==13: y,m=y+1,1

def remote_15m(con, y, m):
    url=f"{HF_BASE}/ohlcv_{y:04d}-{m:02d}.parquet"
    placeholders=",".join(["?"]*len(SYMS))
    # The source timestamp is UTC. Convert to NY time before RTH filtering and 15m bucketing.
    q=f"""
    WITH src AS (
      SELECT
        ticker,
        timezone('America/New_York', timestamp) AS et,
        open, high, low, close, volume
      FROM read_parquet('{url}')
      WHERE ticker IN ({placeholders})
    ),
    rth AS (
      SELECT *
      FROM src
      WHERE CAST(et AS TIME) >= TIME '09:30:00'
        AND CAST(et AS TIME) <  TIME '16:00:00'
    ),
    agg AS (
      SELECT
        ticker,
        time_bucket(INTERVAL '15 minutes', et) AS et_bucket,
        arg_min(open, et) AS open,
        max(high) AS high,
        min(low) AS low,
        arg_max(close, et) AS close,
        sum(volume) AS volume
      FROM rth
      GROUP BY ticker, et_bucket
    )
    SELECT ticker, et_bucket, open, high, low, close, volume
    FROM agg
    ORDER BY ticker, et_bucket
    """
    t0=time.time()
    rows=con.execute(q,list(SYMS)).fetchall()
    print(f"month {y:04d}-{m:02d} rows15={len(rows)} sec={time.time()-t0:.1f}",flush=True)
    return rows

def collect():
    con=duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    bysym={s:[] for s in SYMS}
    missing_months=[]
    months=0
    for y,m in month_iter(WARMUP_START,EVAL_END):
        try:
            rows=remote_15m(con,y,m)
            months+=1
            for ticker,et,o,h,l,c,v in rows:
                if ticker not in bysym:
                    continue
                if et.tzinfo is None:
                    et=et.replace(tzinfo=NY)
                else:
                    et=et.astimezone(NY)
                utc=et.astimezone(UTC)
                bysym[ticker].append({
                    "t":int(utc.timestamp()*1000),
                    "o":float(o),"h":float(h),"l":float(l),"c":float(c),
                    "v":float(v or 0.0)
                })
        except Exception as e:
            print("MONTH_ERROR",y,m,repr(e),flush=True)
            missing_months.append(f"{y:04d}-{m:02d}")
    con.close()
    for s in bysym:
        bysym[s].sort(key=lambda z:z["t"])
    return bysym,months,missing_months

def day_key(bar):
    return datetime.fromtimestamp(bar["t"]/1000,UTC).astimezone(NY).date()

def detect_splits(bars):
    byday=defaultdict(list)
    for z in bars: byday[day_key(z)].append(z)
    days=sorted(byday)
    common=(2,3,4,5,7,10,15,20)
    events=[]
    for i in range(1,len(days)):
        prev=byday[days[i-1]][-1]["c"]
        op=byday[days[i]][0]["o"]
        if prev<=0 or op<=0: continue
        ratio=prev/op
        mag=ratio if ratio>=1 else 1/ratio
        if mag<1.7: continue
        f=min(common,key=lambda q:abs(mag/q))
        rel=abs(mag/f)
        if rel<=0.08:
            if ratio>1:
                pm,vm=1/f,f
            else:
                pm,vm=f,1/f
            events.append({
                "date":str(days[i]),"factor":f,"raw_prevclose_open_ratio":ratio,
                "price_mult_before":pm,"volume_mult_before":vm
            })
    return events

def apply_splits(bars,events):
    if not events: return bars
    parsed=[(datetime.fromisoformat(e["date"]).date(),e["price_mult_before"],e["volume_mult_before"]) for e in events]
    out=[]
    for z in bars:
        d=day_key(z); pm=1.0; vm=1.0
        for split_day,p,v in parsed:
            if d<split_day:
                pm*=p; vm*=v
        q=z.copy()
        q["o"]*=pm; q["h"]*=pm; q["l"]*=pm; q["c"]*=pm; q["v"]*=vm
        out.append(q)
    return out

def aggregate_4h(bars):
    groups=defaultdict(list)
    for z in bars:
        dt=datetime.fromtimestamp(z["t"]/1000,UTC).astimezone(NY)
        mins=(dt.hour*60+dt.minute)-(9*60+30)
        bucket=0 if mins<240 else 1
        groups[(dt.date(),bucket)].append(z)
    out=[]
    for _,g in sorted(groups.items()):
        g.sort(key=lambda x:x["t"])
        out.append({"t":g[0]["t"],"o":g[0]["o"],"h":max(x["h"] for x in g),
                    "l":min(x["l"] for x in g),"c":g[-1]["c"],"v":sum(x["v"] for x in g)})
    return out

def aggregate_daily(bars):
    groups=defaultdict(list)
    for z in bars: groups[day_key(z)].append(z)
    out=[]
    for _,g in sorted(groups.items()):
        g.sort(key=lambda x:x["t"])
        out.append({"t":g[0]["t"],"o":g[0]["o"],"h":max(x["h"] for x in g),
                    "l":min(x["l"] for x in g),"c":g[-1]["c"],"v":sum(x["v"] for x in g)})
    return out

def summarize(sym,r,splits,bars):
    ts=[t for t in r["trades"] if t["track"]=="B" and t["reason"]!="OPEN_MARK"]
    wins=sum(t["pnl"]>0 for t in ts)
    return {
      "symbol":sym,
      "setups":r.get("setups",{}).get("B",0),
      "closed":len(ts),"wins":wins,"losses":sum(t["pnl"]<0 for t in ts),
      "win_rate":wins/len(ts) if ts else None,
      "net_r":sum(t["r"] for t in ts),
      "avg_r":sum(t["r"] for t in ts)/len(ts) if ts else None,
      "max_drawdown_fixed_20k":r.get("max_drawdown"),
      "split_adjustments":splits,
      "bars":{"15m":len(bars)},
      "trades":ts
    }

def portfolio(results):
    trades=[]
    for s in results:
        for t in s["trades"]: trades.append({"symbol":s["symbol"],**t})
    trades.sort(key=lambda x:x["exit_t"])
    eq=bt.CAP; peak=eq; mdd=0.0
    for t in trades:
        eq+=t["pnl"]; peak=max(peak,eq)
        mdd=max(mdd,(peak-eq)/peak if peak else 0.0)
    n=len(trades); wins=sum(t["pnl"]>0 for t in trades)
    return {
      "closed_trades":n,"wins":wins,"losses":sum(t["pnl"]<0 for t in trades),
      "win_rate":wins/n if n else None,
      "net_r":sum(t["r"] for t in trades),
      "avg_r":sum(t["r"] for t in trades)/n if n else None,
      "max_drawdown_fixed_20k":mdd,
      "trades":trades
    }

def grouped_stats(trades,keyfn):
    out={}
    for t in trades:
        k=str(keyfn(t)); q=out.setdefault(k,{"trades":0,"wins":0,"losses":0,"net_r":0.0})
        q["trades"]+=1; q["wins"]+=int(t["pnl"]>0); q["losses"]+=int(t["pnl"]<0); q["net_r"]+=t["r"]
    for q in out.values():
        q["win_rate"]=q["wins"]/q["trades"] if q["trades"] else None
        q["avg_r"]=q["net_r"]/q["trades"] if q["trades"] else None
    return out

def main():
    bysym,months,missing=collect()
    results=[]; errors={}
    old_dataset,old_filters=bt.dataset,bt.symbol_filters
    old_cap,old_risk=bt.CAP,bt.RISK
    bt.CAP=20000.0; bt.RISK=400.0
    try:
        for sym in SYMS:
            try:
                bars=bysym[sym]
                if len(bars)<5000:
                    raise RuntimeError(f"insufficient 15m bars: {len(bars)}")
                splits=detect_splits(bars)
                bars=apply_splits(bars,splits)
                H=w.enrich(aggregate_4h(bars))
                D=w.enrich(aggregate_daily(bars))
                M=bars
                bt._CACHE.clear()
                bt.dataset=lambda _s,D=D,H=H,M=M:(D,H,M)
                bt.symbol_filters=lambda _s:(0.01,0.0,0.0)
                r=bt.simulate(
                    sym,a_params=A_OFF,b_params=None,
                    start_ms=int(EVAL_START.timestamp()*1000),
                    end_ms=int(EVAL_END.timestamp()*1000)-1,
                    fee_bps=FEE_BPS,slippage_bps=SLIPPAGE_BPS,
                    a_mode="snapshot",b_runner_mode="pivot",b_scale_mode="30_30_40"
                )
                sm=summarize(sym,r,splits,bars); results.append(sm)
                print("RESULT",sym,{k:v for k,v in sm.items() if k!="trades"},flush=True)
            except Exception as e:
                errors[sym]=repr(e); print("SYMBOL_ERROR",sym,repr(e),flush=True)
    finally:
        bt.dataset,bt.symbol_filters=old_dataset,old_filters
        bt.CAP,bt.RISK=old_cap,old_risk

    total=portfolio(results)
    trades=total["trades"]
    by_year=grouped_stats(trades,lambda t:datetime.fromtimestamp(t["exit_t"]/1000,UTC).year)
    by_symbol=grouped_stats(trades,lambda t:t["symbol"])

    positive=sum(v["net_r"]>0 for v in by_symbol.values())
    negative=sum(v["net_r"]<0 for v in by_symbol.values())
    flat=sum(v["net_r"]==0 for v in by_symbol.values())
    ranked=sorted(((s,v["net_r"]) for s,v in by_symbol.items()),key=lambda x:x[1],reverse=True)
    positive_total=sum(max(0,r) for _,r in ranked)
    top5_positive=sum(max(0,r) for _,r in ranked[:5])
    concentration=(top5_positive/positive_total if positive_total else None)

    report={
      "generated_at":datetime.now(UTC).isoformat(),
      "purpose":"Five-year exact-touch validation of frozen Track B on the original 50-stock Binance TradFi universe",
      "strategy":"Production Track B defaults frozen; original 50-stock universe; exact-touch entry; 30/30/40; TP1=>BE; TP2=>TP1; confirmed 4H pivot runner",
      "period":{"evaluation_start":EVAL_START.isoformat(),"evaluation_end_exclusive":EVAL_END.isoformat(),
                "warmup_start":WARMUP_START.isoformat()},
      "symbols":list(SYMS),
      "data":{"provider":"Hugging Face mito0o852/OHLCV-1m",
              "source":"monthly 1-minute US OHLCV parquet",
              "session":"09:30-16:00 America/New_York only",
              "aggregation":"remote 1m -> 15m; 15m -> 09:30-13:30 4h + 13:30-16:00 stub; RTH daily",
              "months_loaded":months,"missing_months":missing,
              "split_cleanup":"common-factor overnight split detection; pre-split OHLCV back-adjusted",\n              "entry_fill_model":"LIMIT_TOUCH: low <= planned_entry <= high",\n              "entry_pending":"4H directional cross without 15m exact touch remains pending until exact touch/invalidation/expiry"},
      "costs":{"fee_bps_per_fill":FEE_BPS,"slippage_bps_per_fill":SLIPPAGE_BPS},
      "totals":{k:v for k,v in total.items() if k!="trades"},
      "breadth":{"symbols_with_closed_trades":len(by_symbol),"positive_symbols":positive,
                 "negative_symbols":negative,"flat_symbols":flat,
                 "top5_share_of_positive_r":concentration},
      "by_year":by_year,
      "by_symbol":by_symbol,
      "per_symbol":[{k:v for k,v in s.items() if k!="trades"} for s in results],
      "errors":errors,
      "trades":trades
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("FINAL_SUMMARY",json.dumps({k:v for k,v in report.items() if k not in ("trades","per_symbol")},ensure_ascii=False),flush=True)

if __name__=="__main__":
    main()
