import csv,io,json,statistics,urllib.request,urllib.error,zipfile
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
IN=ROOT/"data/validation/cat_core_v0_4_trail_sweep_crypto.json"
OUT=ROOT/"data/validation/cat_core_v0_4_trail25_funding.json"
UTC=timezone.utc
MODE="TRAIL_2.5"

def month_key(ms):
    d=datetime.fromtimestamp(ms/1000,UTC); return d.year,d.month
def months_between(a,b):
    y,m=month_key(a); ey,em=month_key(b); out=[]
    while (y,m)<=(ey,em):
        out.append((y,m)); m+=1
        if m==13: y,m=y+1,1
    return out
def fetch(url):
    try:
        req=urllib.request.Request(url,headers={"User-Agent":"cat-trail25-funding/1.0"})
        with urllib.request.urlopen(req,timeout=40) as r: raw=r.read()
    except urllib.error.HTTPError as e:
        if e.code==404:return None
        raise
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        return z.read(z.namelist()[0]).decode("utf-8-sig")
def parse(txt):
    if not txt:return []
    rows=list(csv.reader(io.StringIO(txt)))
    if not rows:return []
    hdr=[x.strip().lower() for x in rows[0]]
    has=not rows[0][0].strip().lstrip("-").isdigit()
    if has:
        ix={k:i for i,k in enumerate(hdr)}
        ti=ix.get("calc_time",ix.get("fundingtime",0))
        ri=ix.get("last_funding_rate",ix.get("funding_rate",ix.get("fundingrate",1)))
        rows=rows[1:]
    else: ti,ri=0,1
    out=[]
    for r in rows:
        try:
            t=int(float(r[ti])); rate=float(r[ri])
            if t<10_000_000_000:t*=1000
            out.append((t,rate))
        except: pass
    return out
def metrics(ts,key):
    rs=[x[key] for x in ts]; p=[r for r in rs if r>0]; n=[r for r in rs if r<0]
    eq=peak=0.; dd=0.; cur=mx=0
    for x in sorted(ts,key=lambda z:(z["exit_t"],z["symbol"])):
        r=x[key]; eq+=r; peak=max(peak,eq); dd=min(dd,eq-peak)
        if r<0:cur+=1;mx=max(mx,cur)
        else:cur=0
    return {"trades":len(ts),"total_r":sum(rs),"avg_r":statistics.fmean(rs),
            "profit_factor":sum(p)/abs(sum(n)) if n else None,
            "win_rate":len(p)/len(ts),"max_drawdown_r":dd,"max_losing_streak":mx}
def main():
    d=json.loads(IN.read_text())
    trades=d["modes"][MODE]["trades"]
    need=defaultdict(set)
    for t in trades:
        for ym in months_between(t["entry_t"],t["exit_t"]): need[t["symbol"]].add(ym)
    data={}; missing=[]
    for sym,months in need.items():
        fr=[]
        for y,m in sorted(months):
            url=f"https://data.binance.vision/data/futures/um/monthly/fundingRate/{sym}/{sym}-fundingRate-{y:04d}-{m:02d}.zip"
            txt=fetch(url)
            if txt is None:
                missing.append(f"{sym}:{y:04d}-{m:02d}");continue
            fr.extend(parse(txt))
        data[sym]=sorted(set(fr))
    out=[]; ps=defaultdict(lambda:{"funding_r":0.,"events":0,"trades":0})
    for t in trades:
        ev=[(ft,r) for ft,r in data[t["symbol"]] if t["entry_t"]<=ft<=t["exit_t"]]
        fund_r=-(t["entry"]/t["initial_risk"])*sum(r for _,r in ev)
        q=dict(t); q["funding_r"]=fund_r; q["r_adj"]=t["r"]+fund_r; q["funding_events"]=len(ev)
        out.append(q)
        ps[t["symbol"]]["funding_r"]+=fund_r
        ps[t["symbol"]]["events"]+=len(ev)
        ps[t["symbol"]]["trades"]+=1
    report={
      "strategy":"CAT-Core v0.4 initial 2.5 ATR / trail 2.5 ATR crypto funding audit",
      "method":"actual Binance Vision funding settlement rates; funding notional approximated by entry price / initial risk for R conversion",
      "missing_months":missing,
      "before":metrics(trades,"r"),
      "after":metrics(out,"r_adj"),
      "per_symbol":dict(ps),
      "total_funding_r":sum(x["funding_r"] for x in out),
      "avg_funding_r_per_trade":statistics.fmean(x["funding_r"] for x in out),
      "trades":out
    }
    OUT.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k!="trades"},indent=2))
if __name__=="__main__":main()
