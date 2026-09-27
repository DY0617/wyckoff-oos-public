import bisect,json,time
from datetime import datetime,timezone,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import duckdb
import sys
sys.path.insert(0,str(Path(__file__).parent))
import wyckoff_status as w

BASE50=Path("data/validation/stock50_track_b_hf_5y_exact_touch.json")
ADD20=Path("data/validation/stock20_added_track_b_hf_5y_exact_touch.json")
OUT=Path("data/validation/stock70_e_vs_stock53_e_5y.json")
UTC=timezone.utc; NY=ZoneInfo("America/New_York")
START=datetime(2021,4,1,tzinfo=UTC); END=datetime(2026,4,1,tzinfo=UTC)
WARMUP=START-timedelta(days=390)
HF_BASE="https://huggingface.co/datasets/mito0o852/OHLCV-1m/resolve/main/data"

BASE50_SYMS=(
"AAPL","AMZN","AVGO","CRCL","MSFT","MU","SNDK","SNXX","SOXL","SPCX",
"AMD","BABA","INTC","JPM","KORU","MSTR","NFLX","SKHY","SOXS","V",
"COST","GOOGL","LLY","META","NBIS","NVDA","QQQ","TSLA","UBER","WMT",
"AMAT","CAT","DRAM","EWY","HD","MRVL","MUU","ORCL","SPY","TSM",
"AAOI","BE","COIN","CRM","CSCO","DIS","HOOD","IBM","LITE","TQQQ"
)
ADD20_SYMS=("ARM","AXTI","BMNR","CBRS","COHR","CRDO","CRWD","CRWV","DELL","EWJ",
"GME","HPE","IREN","IWM","PLTR","QCOM","RKLB","SMCI","WDC","ZM")
SYMS70=tuple(BASE50_SYMS+ADD20_SYMS)
SYMS53=tuple(BASE50_SYMS+("DELL","SMCI","AXTI"))
SOURCE=tuple(sorted(set(SYMS70+("FB","GOOG"))))

def month_iter(start,end):
    y,m=start.year,start.month
    while (y,m)<=(end.year,end.month):
        yield y,m
        m+=1
        if m==13:y,m=y+1,1

def canonical(ticker,d):
    if ticker=="FB": return "META" if d<datetime(2022,6,9).date() else None
    if ticker=="META": return "META" if d>=datetime(2022,6,9).date() else None
    if ticker=="GOOG": return "GOOGL" if d<datetime(2014,4,3).date() else None
    if ticker=="GOOGL": return "GOOGL" if d>=datetime(2014,4,3).date() else None
    return ticker if ticker in SYMS70 else None

def remote_daily(con,y,m):
    url=f"{HF_BASE}/ohlcv_{y:04d}-{m:02d}.parquet"
    ph=",".join(["?"]*len(SOURCE))
    q=f"""
    WITH src AS (
      SELECT ticker,timezone('America/New_York',timestamp) et,open,high,low,"close",volume
      FROM read_parquet('{url}') WHERE ticker IN ({ph})
    ),rth AS (
      SELECT * FROM src WHERE cast(et as time)>=time '09:30:00' and cast(et as time)<time '16:00:00'
    )
    SELECT ticker,cast(et as date) d,min(et) first_et,max(et) last_et,
           arg_min(open,et) o,max(high) h,min(low) l,arg_max("close",et) c,sum(volume) v
    FROM rth GROUP BY ticker,cast(et as date) ORDER BY ticker,d
    """
    return con.execute(q,list(SOURCE)).fetchall()

def collect():
    con=duckdb.connect();con.execute("INSTALL httpfs; LOAD httpfs;")
    by={s:[] for s in SYMS70};missing=[]
    for y,m in month_iter(WARMUP,END-timedelta(days=1)):
        rows=None
        for a in range(5):
            try:
                t=time.time();rows=remote_daily(con,y,m)
                print("MONTH",f"{y:04d}-{m:02d}",len(rows),round(time.time()-t,2),flush=True);break
            except Exception as e:
                print("RETRY",y,m,a+1,repr(e),flush=True);time.sleep(3*(a+1))
        if rows is None:missing.append(f"{y:04d}-{m:02d}");continue
        for ticker,d,first_et,last_et,o,h,l,c,v in rows:
            s=canonical(str(ticker),d)
            if not s:continue
            f=first_et.replace(tzinfo=NY) if first_et.tzinfo is None else first_et.astimezone(NY)
            z=last_et.replace(tzinfo=NY) if last_et.tzinfo is None else last_et.astimezone(NY)
            tms=int(f.astimezone(UTC).timestamp()*1000)
            ct=int(z.astimezone(UTC).timestamp()*1000)+60_000-1
            if tms<int(WARMUP.timestamp()*1000) or tms>=int(END.timestamp()*1000):continue
            by[s].append({"t":tms,"o":float(o),"h":float(h),"l":float(l),"c":float(c),"v":float(v or 0),"ct":ct})
    con.close()
    if missing:raise RuntimeError("missing months "+",".join(missing))
    return {s:w.enrich(sorted(v,key=lambda x:x["t"])) for s,v in by.items() if v}

def idx(D,t):
    return bisect.bisect_left([x["ct"] for x in D],t)-1
def ret20(D,i):
    return D[i]["c"]/D[i-20]["c"]-1 if i>=20 and D[i-20]["c"]>0 else None

def e_pass(t,dailies,universe):
    if t["direction"]!="LONG":return (False,None)
    spy=dailies.get("SPY"); D=dailies.get(t["symbol"])
    if not spy or not D:return (False,None)
    si=idx(spy,t["entry_t"]); i=idx(D,t["entry_t"])
    if si<50 or i<50:return (False,None)
    sr=ret20(spy,si); rr=ret20(D,i)
    if sr is None or rr is None:return (False,None)
    s=spy[si]
    votes=int(s["c"]>s["ema50"])+int(s["ema20"]>s["ema50"])+int(sr>0)
    above=eligible=0
    for sym in universe:
        U=dailies.get(sym)
        if not U:continue
        ui=idx(U,t["entry_t"])
        if ui>=50 and U[ui].get("ema50") is not None:
            eligible+=1; above+=int(U[ui]["c"]>U[ui]["ema50"])
    breadth=above/eligible if eligible else None
    ok=votes>=2 and rr>=sr and breadth is not None and breadth>=.50
    return ok,{"spy_votes":votes,"stock_ret20":rr,"spy_ret20":sr,"breadth":breadth,"above":above,"eligible":eligible}

def stats(ts):
    n=len(ts);w=sum(x["pnl"]>0 for x in ts);l=sum(x["pnl"]<0 for x in ts)
    net=sum(x["r"] for x in ts);gp=sum(x["r"] for x in ts if x["r"]>0);gl=sum(x["r"] for x in ts if x["r"]<0)
    cr=pr=mdd=0.0;st=best=0
    for x in sorted(ts,key=lambda z:(z["exit_t"],z["symbol"])):
        cr+=x["r"];pr=max(pr,cr);mdd=max(mdd,pr-cr)
        if x["r"]<0:st+=1;best=max(best,st)
        else:st=0
    return {"trades":n,"wins":w,"losses":l,"win_rate":w/n if n else None,
            "net_r":net,"avg_r":net/n if n else None,"profit_factor":gp/abs(gl) if gl<0 else None,
            "max_drawdown_r":mdd,"max_consecutive_losses":best}

def main():
    b50=json.loads(BASE50.read_text()); a20=json.loads(ADD20.read_text())
    trades50=b50["trades"]; trades20=a20["trades"]
    # These sets are disjoint by design (original 50 + added 20).
    all70=sorted(trades50+trades20,key=lambda x:(x["entry_t"],x["symbol"]))
    set53=set(SYMS53)
    all53=[x for x in all70 if x["symbol"] in set53]
    dailies=collect()
    out={}
    audits={}
    for name,trades,universe in [("E53",all53,SYMS53),("E70",all70,SYMS70)]:
        kept=[]; audit=[]
        for t in trades:
            ok,ctx=e_pass(t,dailies,universe)
            if ok:kept.append(t)
            audit.append({"symbol":t["symbol"],"entry_t":t["entry_t"],"r":t["r"],"pass":ok,"ctx":ctx})
        out[name]={"base":stats(trades),"e":stats(kept)}
        audits[name]=audit
    extra17=set(SYMS70)-set(SYMS53)
    e70_extra=[x for x in all70 if x["symbol"] in extra17 and e_pass(x,dailies,SYMS70)[0]]
    out["E70_extra17_contribution"]=stats(e70_extra)
    out["E70_extra17_by_symbol"]={}
    for s in sorted(extra17):
        xs=[x for x in e70_extra if x["symbol"]==s]
        if xs:out["E70_extra17_by_symbol"][s]=stats(xs)
    report={"generated_at":datetime.now(UTC).isoformat(),"period":{"start":START.isoformat(),"end_exclusive":END.isoformat()},
            "symbols":{"E53":list(SYMS53),"E70":list(SYMS70)},"definitions":{"E":"LONG + SPY bull >=2/3 + stock 20d return >= SPY 20d return + breadth >=50%"},
            "results":out,"audits":audits,
            "note":"Same existing exact-touch 5y trades; only universe/breadth and eligibility differ. E70 breadth denominator uses available symbols with >=51 completed daily bars at each entry."}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=="__main__":main()
