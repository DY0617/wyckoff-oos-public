import csv, io, json, math, statistics, urllib.request, urllib.error, zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))

import backtest_cat_core_v0_4_er20_crypto_5y as cb
import backtest_cat_core_v0_4_er20_stock30_5y as sb

UTC=timezone.utc
CRYPTO_PATH=ROOT/"data/validation/cat_core_v0_4_stop_e_breakout_clamp_crypto.json"
STOCK_PATH=ROOT/"data/validation/cat_core_v0_4_stop_e_breakout_clamp_stock30.json"
OUT=ROOT/"data/validation/cat_core_v0_4_stop_e_realism.json"

TARGET_RISK=.0035
CLASS_CAP=.015
TOTAL_CAP=.025
CORR_LOOKBACK=60
CORR_THRESHOLD=.80

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def month_iter(start_ms,end_ms):
    a=datetime.fromtimestamp(start_ms/1000,UTC); b=datetime.fromtimestamp(end_ms/1000,UTC)
    y,m=a.year,a.month
    while (y,m)<=(b.year,b.month):
        yield y,m
        m+=1
        if m==13:y,m=y+1,1

def fetch_zip_csv(url):
    try:
        req=urllib.request.Request(url,headers={"User-Agent":"cat-realism/1.0"})
        with urllib.request.urlopen(req,timeout=45) as r: raw=r.read()
    except urllib.error.HTTPError as e:
        if e.code==404:return None
        raise
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        return z.read(z.namelist()[0]).decode("utf-8-sig")

def parse_funding(txt):
    if not txt:return []
    rows=list(csv.reader(io.StringIO(txt)))
    if not rows:return []
    header=[x.strip().lower() for x in rows[0]]
    has_header=not rows[0][0].strip().lstrip("-").isdigit()
    out=[]
    if has_header:
        idx={k:i for i,k in enumerate(header)}
        ti=idx.get("calc_time",idx.get("fundingtime",idx.get("funding_time",0)))
        ri=idx.get("last_funding_rate",idx.get("funding_rate",idx.get("fundingrate",1)))
        data=rows[1:]
    else:
        ti,ri=0,1;data=rows
    for row in data:
        try:
            t=int(float(row[ti]));r=float(row[ri])
            if t<10_000_000_000:t*=1000
            out.append((t,r))
        except Exception:
            continue
    return out

def fetch_funding(symbol,start_ms,end_ms):
    out=[]
    for y,m in month_iter(start_ms,end_ms):
        url=f"https://data.binance.vision/data/futures/um/monthly/fundingRate/{symbol}/{symbol}-fundingRate-{y:04d}-{m:02d}.zip"
        txt=fetch_zip_csv(url)
        if txt is None:
            print("FUNDING_MISSING",symbol,y,m,flush=True)
            continue
        q=parse_funding(txt)
        out.extend((t,r) for t,r in q if start_ms<=t<=end_ms)
        print("FUNDING",symbol,y,m,len(q),flush=True)
    out=sorted(set(out))
    return out

def metrics(trades,r_key="r"):
    rs=[x[r_key] for x in trades]
    pos=[r for r in rs if r>0];neg=[r for r in rs if r<0]
    eq=peak=0.;dd=0.;cur=mx=0
    for x in sorted(trades,key=lambda z:(z["exit_t"],z["symbol"])):
        r=x[r_key];eq+=r;peak=max(peak,eq);dd=min(dd,eq-peak)
        if r<0:cur+=1;mx=max(mx,cur)
        else:cur=0
    return {"trades":len(trades),"wins":len(pos),"losses":len(neg),
            "win_rate":len(pos)/len(trades) if trades else None,
            "total_r":sum(rs),"avg_r":statistics.fmean(rs) if rs else None,
            "profit_factor":sum(pos)/abs(sum(neg)) if neg else None,
            "max_drawdown_r":dd,"max_losing_streak":mx}

def funding_adjust(crypto):
    bysym=defaultdict(list)
    for t in crypto:bysym[t["symbol"]].append(t)
    funding={}
    adjusted=[]
    per_symbol={}
    for sym,ts in bysym.items():
        start=min(x["entry_t"] for x in ts);end=max(x["exit_t"] for x in ts)
        fr=fetch_funding(sym,start,end);funding[sym]=fr
        fund_total=0.
        adjts=[]
        for t in ts:
            rates=[r for ft,r in fr if t["entry_t"]<=ft<=t["exit_t"]]
            # Binance Vision funding archive contains settlement rates but not mark price.
            # Long funding is approximated using entry notional / initial risk.
            funding_r=-(t["entry"]/t["initial_risk"])*sum(rates)
            q=dict(t);q["funding_r_entry_notional_proxy"]=funding_r;q["r_funding_adj"]=t["r"]+funding_r
            q["funding_events"]=len(rates)
            adjusted.append(q);adjts.append(q);fund_total+=funding_r
        per_symbol[sym]={"funding_r":fund_total,"before":metrics(ts),"after":metrics(adjts,"r_funding_adj")}
    return adjusted,per_symbol

def load_daily():
    cdata={}
    for sym in cb.SYMBOLS:
        print("DAILY_CRYPTO",sym,flush=True)
        cdata[sym]=cb.enrich(cb.fetch1d(sym))
    print("DAILY_STOCK_COLLECT",flush=True)
    raw=sb.collect();sdata={}
    for sym,D in raw.items():
        D=sb.enrich(sb.adjust(D))
        if D:sdata[sym]=D
    return cdata,sdata

def date_key_ms(ms):
    return datetime.fromtimestamp(ms/1000,UTC).date().isoformat()

def bar_maps(cdata,sdata):
    low={};close={};rets={}
    for cls,data in (("crypto",cdata),("stock",sdata)):
        for sym,D in data.items():
            lm={};cm={};rr={}
            prev=None
            for x in D:
                k=x.get("date") or date_key_ms(x["t"])
                lm[k]=x["l"];cm[k]=x["c"]
                if prev and prev>0:rr[k]=x["c"]/prev-1
                prev=x["c"]
            low[(cls,sym)]=lm;close[(cls,sym)]=cm;rets[(cls,sym)]=rr
    return low,close,rets

def pearson(a,b):
    if len(a)<20:return None
    ma=statistics.fmean(a);mb=statistics.fmean(b)
    va=sum((x-ma)**2 for x in a);vb=sum((y-mb)**2 for y in b)
    if va<=0 or vb<=0:return None
    return sum((x-ma)*(y-mb) for x,y in zip(a,b))/math.sqrt(va*vb)

def corr_before(cls,s1,s2,entry_date,rets):
    r1=rets.get((cls,s1),{});r2=rets.get((cls,s2),{})
    keys=sorted(k for k in set(r1)&set(r2) if k<entry_date)
    keys=keys[-CORR_LOOKBACK:]
    return pearson([r1[k] for k in keys],[r2[k] for k in keys])

def allocate(crypto,stock,rets,corr_filter=False):
    trades=[]
    for i,x in enumerate(crypto):
        q=dict(x);q["asset_class"]="crypto";q["_id"]=f"c{i}";q["r_use"]=q.get("r_funding_adj",q["r"]);trades.append(q)
    for i,x in enumerate(stock):
        q=dict(x);q["asset_class"]="stock";q["_id"]=f"s{i}";q["r_use"]=q["r"];trades.append(q)
    trades.sort(key=lambda x:(x["entry_t"],x["asset_class"],x["symbol"]))
    groups=defaultdict(list)
    for t in trades:groups[t["entry_t"]].append(t)
    equity=1.;openp=[];accepted=[];skipped_budget=0;skipped_corr=0
    for et in sorted(groups):
        due=sorted([p for p in openp if p["exit_t"]<=et],key=lambda p:p["exit_t"])
        for p in due:equity+=p["risk_dollar"]*p["r_use"]
        openp=[p for p in openp if p["exit_t"]>et]
        for cls in ("crypto","stock"):
            g=[x for x in groups[et] if x["asset_class"]==cls]
            if not g:continue
            # Deterministic tie-break. Higher absolute average multi-horizon return first when present.
            g.sort(key=lambda x:(-abs(statistics.fmean([x.get("ret20",0),x.get("ret60",0),x.get("ret120",0)])),x["symbol"]))
            for t in g:
                if corr_filter:
                    d=date_key_ms(t["entry_t"])
                    bad=False
                    for p in openp:
                        if p["asset_class"]!=cls:continue
                        cr=corr_before(cls,t["symbol"],p["symbol"],d,rets)
                        if cr is not None and cr>=CORR_THRESHOLD:
                            bad=True;break
                    if bad:
                        skipped_corr+=1;continue
                open_class=sum(p["risk_dollar"] for p in openp if p["asset_class"]==cls)
                open_total=sum(p["risk_dollar"] for p in openp)
                avail=min(TARGET_RISK*equity,max(0.,CLASS_CAP*equity-open_class),max(0.,TOTAL_CAP*equity-open_total))
                if avail<=1e-12:
                    skipped_budget+=1;continue
                q=dict(t);q["risk_dollar"]=avail;openp.append(q);accepted.append(q)
    for p in sorted(openp,key=lambda p:p["exit_t"]):equity+=p["risk_dollar"]*p["r_use"]
    return accepted,{"final_equity":equity,"total_return":equity-1,"accepted":len(accepted),"skipped_budget":skipped_budget,"skipped_corr":skipped_corr}

def realized_dd(pos):
    eq=peak=1.;dd=0.
    for p in sorted(pos,key=lambda x:x["exit_t"]):
        eq+=p["risk_dollar"]*p["r_use"];peak=max(peak,eq);dd=min(dd,eq/peak-1)
    return dd

def stress_dd(pos,low,close):
    if not pos:return None
    all_dates=set()
    for p in pos:
        lm=low.get((p["asset_class"],p["symbol"]),{})
        a=date_key_ms(p["entry_t"]);b=date_key_ms(p["exit_t"])
        all_dates.update(k for k in lm if a<=k<=b)
    dates=sorted(all_dates)
    realized=0.;peak=1.;mdd=0.;worst=None
    for d in dates:
        # P/L of positions fully exited before this calendar date.
        realized=sum(p["risk_dollar"]*p["r_use"] for p in pos if date_key_ms(p["exit_t"])<d)
        unreal=0.
        for p in pos:
            a=date_key_ms(p["entry_t"]);b=date_key_ms(p["exit_t"])
            if not (a<=d<=b):continue
            if d==b and p["reason"] in ("STOP","GAP_STOP"):
                mark=p["exit"]
            else:
                lm=low.get((p["asset_class"],p["symbol"]),{})
                cm=close.get((p["asset_class"],p["symbol"]),{})
                mark=lm.get(d,cm.get(d))
                if mark is None:continue
            qty=p["risk_dollar"]/p["initial_risk"]
            unreal += qty*(mark-p["entry"])
        eq=1.+realized+unreal
        # Peak uses end-of-day realized+close-ish approximation through closed-equity only, intentionally conservative.
        peak=max(peak,1.+realized)
        cur=eq/peak-1
        if cur<mdd:mdd=cur;worst={"date":d,"equity_stress":eq,"peak_reference":peak}
    return {"max_daily_low_stress_drawdown":mdd,"worst":worst}

def main():
    cr=load(CRYPTO_PATH);sr=load(STOCK_PATH)
    cadj,fstats=funding_adjust(cr["trades"])
    print("FUNDING_DONE",json.dumps({k:v["funding_r"] for k,v in fstats.items()}),flush=True)

    cdata,sdata=load_daily()
    low,close,rets=bar_maps(cdata,sdata)

    base,base_meta=allocate(cadj,sr["trades"],rets,False)
    corr,corr_meta=allocate(cadj,sr["trades"],rets,True)

    report={
      "strategy":"CAT-Core v0.4 Stop E realism layer",
      "signal_rules_changed":False,
      "stop_rule":"breakout support - 0.5 ATR, clamped to 2-3 ATR from actual next-open entry",
      "funding":{
        "method":"actual Binance Vision settlement rates; long funding R approximated with entry notional because funding archive lacks settlement mark price",
        "crypto_before":metrics(cr["trades"]),
        "crypto_after":metrics(cadj,"r_funding_adj"),
        "per_symbol":fstats
      },
      "portfolio_config":{"target_risk":TARGET_RISK,"class_cap":CLASS_CAP,"total_cap":TOTAL_CAP},
      "base_portfolio":{**base_meta,"realized_dd":realized_dd(base),"stress":stress_dd(base,low,close)},
      "corr80_portfolio":{"rule":"skip new same-asset-class entry when trailing 60-session return correlation with any open position >= 0.80",
                          **corr_meta,"realized_dd":realized_dd(corr),"stress":stress_dd(corr,low,close)},
      "caveats":[
        "daily-low stress combines each symbol's session low on the same date, even if lows occurred at different intraday times; it is a conservative stress bound, not synchronized tick-level MDD",
        "stock history is cash RTH proxy; separate recent Binance TradFi comparison is used for execution-domain validation",
        "funding adjustment uses actual settlement rates but entry-price notional as the funding mark proxy"
      ]
    }
    OUT.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print("FINAL",json.dumps(report,indent=2),flush=True)

if __name__=="__main__":main()
