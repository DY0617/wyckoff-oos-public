import json, math, os, time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import duckdb

UTC=timezone.utc
NY=ZoneInfo("America/New_York")
HF_BASE="https://huggingface.co/datasets/mito0o852/OHLCV-1m/resolve/main/data"
GLOBAL_START=datetime(2006,4,1,tzinfo=UTC)

SYMS=(
"AAPL","AMZN","AVGO","CRCL","DELL","MSFT","MU","SNDK","SNXX","SOXL","SPCX",
"AMD","BABA","INTC","JPM","KORU","MSTR","NFLX","SKHY","SMCI","SOXS","V",
"COST","GOOGL","LLY","META","NBIS","NVDA","QQQ","TSLA","UBER","WMT",
"AMAT","CAT","DRAM","EWY","HD","MRVL","MUU","ORCL","SPY","TSM",
"AAOI","AXTI","BE","COIN","CRM","CSCO","DIS","HOOD","IBM","LITE","TQQQ"
)
SOURCE=tuple(sorted(set(SYMS+("FB","GOOG"))))
NOT_BEFORE={
  "DELL":datetime(2018,12,28,tzinfo=UTC),
  "SNDK":datetime(2025,2,24,tzinfo=UTC),
}

FEE_BPS=4.0
SLIPPAGE_BPS=2.0
TOP_FRAC=.20
ENTRY_VALID_DAYS=3
TRAIL_ATR=3.0
STOP_ATR_PAD=.25
MAX_HOLD_DAYS=60
MIN_RISK_PCT=.005
MAX_RISK_PCT=.15
BREADTH_MIN=.50
MAX_POSITIONS=2
STATE_PREROLL_DAYS=140

def pd(s): return datetime.strptime(s,"%Y-%m-%d").replace(tzinfo=UTC)
EVAL_START=pd(os.environ["EVAL_START"])
EVAL_END=pd(os.environ["EVAL_END"])
SIM_START=GLOBAL_START if EVAL_START<=GLOBAL_START else EVAL_START-timedelta(days=STATE_PREROLL_DAYS)
DATA_END=min(pd(os.environ.get("DATA_END","2026-04-01")),EVAL_END+timedelta(days=120))
WARMUP_START=SIM_START-timedelta(days=420)
OUT=Path(os.environ["OUT"])

def month_iter(start,end):
    y,m=start.year,start.month
    while (y,m)<=(end.year,end.month):
        yield y,m
        m+=1
        if m==13:y,m=y+1,1

def canonical(ticker,d):
    if ticker=="FB":return "META" if d<datetime(2022,6,9).date() else None
    if ticker=="META":return "META" if d>=datetime(2022,6,9).date() else None
    if ticker=="GOOG":return "GOOGL" if d<datetime(2014,4,3).date() else None
    if ticker=="GOOGL":return "GOOGL" if d>=datetime(2014,4,3).date() else None
    return ticker if ticker in SYMS else None

def remote15(con,y,m):
    url=f"{HF_BASE}/ohlcv_{y:04d}-{m:02d}.parquet"
    ph=",".join(["?"]*len(SOURCE))
    q=f"""
    WITH src AS (
      SELECT ticker,timezone('America/New_York',timestamp) et,open,high,low,"close",volume
      FROM read_parquet('{url}') WHERE ticker IN ({ph})
    ),rth AS (
      SELECT * FROM src
      WHERE cast(et as time)>=time '09:30:00' and cast(et as time)<time '16:00:00'
    ),agg AS (
      SELECT ticker,time_bucket(interval '15 minutes',et) et_bucket,
             arg_min(open,et) o,max(high) h,min(low) l,arg_max("close",et) c,sum(volume) v
      FROM rth GROUP BY ticker,et_bucket
    )
    SELECT ticker,et_bucket,o,h,l,c,v FROM agg ORDER BY ticker,et_bucket
    """
    return con.execute(q,list(SOURCE)).fetchall()

def collect():
    con=duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    by={s:[] for s in SYMS};missing=[];months=0
    for y,m in month_iter(WARMUP_START,DATA_END-timedelta(days=1)):
        rows=None
        for a in range(6):
            try:
                t0=time.time();rows=remote15(con,y,m)
                print("MONTH",f"{y:04d}-{m:02d}",len(rows),round(time.time()-t0,2),flush=True)
                break
            except Exception as e:
                print("RETRY",y,m,a+1,repr(e),flush=True)
                time.sleep(min(30,4*(a+1)))
        if rows is None:
            missing.append(f"{y:04d}-{m:02d}");continue
        months+=1
        for ticker,et,o,h,l,c,v in rows:
            if et.tzinfo is None:et=et.replace(tzinfo=NY)
            else:et=et.astimezone(NY)
            sym=canonical(str(ticker),et.date())
            if not sym:continue
            utc=et.astimezone(UTC)
            nb=NOT_BEFORE.get(sym)
            if nb and utc<nb:continue
            if utc<WARMUP_START or utc>=DATA_END:continue
            tms=int(utc.timestamp()*1000)
            by[sym].append({"t":tms,"o":float(o),"h":float(h),"l":float(l),"c":float(c),
                            "v":float(v or 0),"ct":tms+15*60*1000-1})
    con.close()
    if missing:raise RuntimeError("missing months="+",".join(missing))
    for s in by:by[s].sort(key=lambda z:z["t"])
    return by,months

def day_key(z):
    return datetime.fromtimestamp(z["t"]/1000,UTC).astimezone(NY).date()

def detect_splits(bars):
    byday=defaultdict(list)
    for z in bars:byday[day_key(z)].append(z)
    days=sorted(byday);common=(1.5,2,3,4,5,7,10,15,20);ev=[]
    for i in range(1,len(days)):
        prev=byday[days[i-1]][-1]["c"];op=byday[days[i]][0]["o"]
        if prev<=0 or op<=0 or (days[i]-days[i-1]).days>14:continue
        ratio=prev/op;mag=ratio if ratio>=1 else 1/ratio
        if mag<1.35:continue
        f=min(common,key=lambda q:abs(mag/q-1.0))
        if abs(mag/f-1.0)<=.05:
            pm,vm=((1/f,f) if ratio>1 else (f,1/f));ev.append((days[i],pm,vm))
    return ev

def apply_splits(bars,ev):
    if not ev:return bars
    out=[]
    for z in bars:
        d=day_key(z);pm=vm=1.0
        for sd,p,v in ev:
            if d<sd:pm*=p;vm*=v
        q=z.copy()
        for k in ("o","h","l","c"):q[k]*=pm
        q["v"]*=vm;out.append(q)
    return out

def aggregate_daily(bars):
    g=defaultdict(list)
    for z in bars:g[day_key(z)].append(z)
    out=[]
    for d,a in sorted(g.items()):
        a.sort(key=lambda x:x["t"])
        out.append({"date":str(d),"t":a[0]["t"],"o":a[0]["o"],"h":max(x["h"] for x in a),
                    "l":min(x["l"] for x in a),"c":a[-1]["c"],"v":sum(x["v"] for x in a),
                    "ct":a[-1]["ct"]})
    return out

def ema(vals,n):
    k=2/(n+1);out=[];e=None
    for x in vals:
        e=x if e is None else e+k*(x-e);out.append(e)
    return out

def enrich_daily(D):
    if not D:return D
    cs=[x["c"] for x in D]
    e20=ema(cs,20);e50=ema(cs,50);e200=ema(cs,200)
    a=None;atr=[]
    for i,x in enumerate(D):
        prev=cs[i-1] if i else x["c"]
        tr=max(x["h"]-x["l"],abs(x["h"]-prev),abs(x["l"]-prev))
        a=tr if a is None else ((a*13)+tr)/14
        atr.append(a)
    for i,x in enumerate(D):
        x["ema20"]=e20[i];x["ema50"]=e50[i];x["ema200"]=e200[i];x["atr14"]=atr[i]
        x["ret60"]=x["c"]/D[i-60]["c"]-1 if i>=60 and D[i-60]["c"]>0 else None
        rng=x["h"]-x["l"];x["clv"]=(x["c"]-x["l"])/rng if rng>0 else .5
    return D

def build_indices(dailies):
    bydate=defaultdict(dict)
    for s,D in dailies.items():
        for i,x in enumerate(D):bydate[x["date"]][s]=i
    return bydate

def make_signals(dailies):
    bydate=build_indices(dailies);sigs=[]
    for ds,m in sorted(bydate.items()):
        day=datetime.fromisoformat(ds).replace(tzinfo=UTC)
        if day<SIM_START or day>=EVAL_END:continue
        spy_i=m.get("SPY")
        if spy_i is None:continue
        spy=dailies["SPY"][spy_i]
        if spy_i<200 or not (spy["c"]>spy["ema200"]):continue

        breadth_eligible=breadth_above=0
        eligible=[]
        for s,i in m.items():
            D=dailies[s]
            if i>=50:
                breadth_eligible+=1
                breadth_above+=int(D[i]["c"]>D[i]["ema50"])
            if i>=200 and D[i]["ret60"] is not None:
                eligible.append((s,D[i]["ret60"]))
        breadth=(breadth_above/breadth_eligible) if breadth_eligible else None
        if breadth is None or breadth<BREADTH_MIN:continue
        if len(eligible)<10:continue

        eligible.sort(key=lambda z:z[1],reverse=True)
        k=max(1,math.ceil(len(eligible)*TOP_FRAC))
        top=set(s for s,_ in eligible[:k])

        for s in top:
            if s=="SOXS":continue
            i=m[s];D=dailies[s]
            if i<200 or i<5:continue
            x=D[i];prev=D[i-1]
            if x["ret60"] is None or x["ret60"]<=0:continue
            if not (x["c"]>x["ema50"]>x["ema200"]):continue
            win=D[i-4:i+1]
            if not any(z["l"]<=z["ema20"] for z in win):continue
            if not all(z["c"]>z["ema50"] for z in win):continue
            if not (x["c"]>x["ema20"] and x["c"]>prev["c"] and x["clv"]>=.60):continue
            entry=x["h"]
            stop=min(z["l"] for z in win)-STOP_ATR_PAD*x["atr14"]
            if stop<=0 or entry<=stop:continue
            risk_pct=(entry-stop)/entry
            if risk_pct<MIN_RISK_PCT or risk_pct>MAX_RISK_PCT:continue
            sigs.append({
              "symbol":s,"signal_date":ds,"signal_i":i,"signal_t":x["ct"],
              "entry_stop":entry,"initial_stop":stop,"risk_pct":risk_pct,
              "ret60":x["ret60"],"breadth":breadth,
              "breadth_above":breadth_above,"breadth_eligible":breadth_eligible
            })
    return sigs

def prep_sessions(adj,dailies):
    sessions={}
    date_idx={}
    for s,bars in adj.items():
        g=defaultdict(list)
        for z in bars:g[day_key(z)].append(z)
        for d in g:g[d].sort(key=lambda x:x["t"])
        sessions[s]=g
        date_idx[s]={datetime.fromisoformat(x["date"]).date():i for i,x in enumerate(dailies[s])}
    return sessions,date_idx

def build_active_orders(signals,dailies,date_idx):
    # date -> symbol -> list of signals active on that session
    active=defaultdict(lambda:defaultdict(list))
    for sig in signals:
        s=sig["symbol"];D=dailies[s]
        sd=datetime.fromisoformat(sig["signal_date"]).date()
        si=date_idx[s].get(sd)
        if si is None:continue
        for di in range(si+1,min(len(D),si+1+ENTRY_VALID_DAYS)):
            d=datetime.fromisoformat(D[di]["date"]).date()
            active[d][s].append(sig)
            # Original semantics: after a completed non-fill session below EMA50, order dies.
            if D[di]["c"]<D[di]["ema50"]:break
    for d in active:
        for s in active[d]:
            active[d][s].sort(key=lambda q:(q["signal_t"],-q["ret60"]))
    return active

def close_trade(pos,exit_t,exit_fill,reason):
    fee_entry=pos["entry"]*FEE_BPS/10000
    fee_exit=exit_fill*FEE_BPS/10000
    pnl_per_share=(exit_fill-pos["entry"])-fee_entry-fee_exit
    r=pnl_per_share/pos["initial_risk"]
    return {
      "symbol":pos["symbol"],"direction":"LONG","signal_t":pos["signal_t"],
      "entry_t":pos["entry_t"],"exit_t":exit_t,"entry":pos["entry"],
      "initial_stop":pos["initial_stop"],"exit":exit_fill,"reason":reason,
      "initial_risk":pos["initial_risk"],"r":r,"pnl":r*400.0,
      "signal_ret60":pos["signal_ret60"],"signal_risk_pct":pos["signal_risk_pct"],
      "signal_breadth":pos["signal_breadth"],"hold_days":pos["hold_days"]
    }

def trading_dates(dailies):
    return sorted(set(datetime.fromisoformat(x["date"]).date() for D in dailies.values() for x in D))

def build_session_index(dates):
    return {d:i for i,d in enumerate(dates)}

def breadth_series(dailies):
    bydate=build_indices(dailies)
    out={}
    for ds,m in sorted(bydate.items()):
        e=a=0
        for s,i in m.items():
            D=dailies[s]
            if i<50:continue
            e+=1;a+=int(D[i]["c"]>D[i]["ema50"])
        out[datetime.fromisoformat(ds).date()]=(a/e if e else None)
    return out

def simulate_portfolio(adj,dailies,signals,policy):
    sessions,date_idx=prep_sessions(adj,dailies)
    active_orders=build_active_orders(signals,dailies,date_idx)
    all_dates=trading_dates(dailies)
    sess_idx=build_session_index(all_dates)
    bseries=breadth_series(dailies)

    openpos={}
    used_signals=set()
    last_exit_date={}
    last_symbol_loss_idx={}
    closed_results=[]  # tuples (exit_session_idx, r)
    trades=[]
    skipped_cap=0
    skipped_global_cd=0
    skipped_symbol_cd=0
    skipped_breadth_slope=0

    def recent_consecutive_losses(now_idx):
        n=0
        for exit_idx,r in reversed(closed_results):
            if exit_idx>now_idx:continue
            if r<0:n+=1
            else:break
        return n

    for d in all_dates:
        day_utc=datetime(d.year,d.month,d.day,tzinfo=UTC)
        if day_utc<SIM_START or day_utc>=DATA_END:continue
        di_global=sess_idx[d]

        timeline=defaultdict(list)
        for s,g in sessions.items():
            for bar in g.get(d,[]):timeline[bar["t"]].append((s,bar))

        for ts,items in sorted(timeline.items()):
            bar_by={s:b for s,b in items}

            # 1) Existing-position stops first.
            exiting=[]
            for s,pos in list(openpos.items()):
                bar=bar_by.get(s)
                if not bar:continue
                if bar["l"]<=pos["stop"]:
                    raw=bar["o"] if bar["o"]<pos["stop"] else pos["stop"]
                    exit_fill=raw*(1-SLIPPAGE_BPS/10000)
                    tr=close_trade(pos,bar["t"],exit_fill,"STOP")
                    exiting.append((s,tr))
            for s,tr in exiting:
                trades.append(tr);del openpos[s];last_exit_date[s]=d
                closed_results.append((di_global,tr["r"]))
                if tr["r"]<0:last_symbol_loss_idx[s]=di_global

            candidates=[]
            for s,bar in items:
                if s in openpos:continue
                orders=active_orders.get(d,{}).get(s,[])
                chosen=None
                for sig in orders:
                    sid=(s,sig["signal_t"])
                    if sid in used_signals:continue
                    led=last_exit_date.get(s)
                    if led is not None and datetime.fromisoformat(sig["signal_date"]).date()<=led:
                        used_signals.add(sid);continue
                    if bar["o"]>=sig["entry_stop"] or bar["h"]>=sig["entry_stop"]:
                        chosen=sig;break
                if chosen is None:continue

                # Global loss cooldown: after the Nth consecutive losing exit,
                # block new admissions for the next K completed market sessions.
                if policy.get("loss_streak_n"):
                    streak=recent_consecutive_losses(di_global)
                    if streak>=policy["loss_streak_n"]:
                        # locate most recent exit session
                        last_loss_idx=closed_results[-1][0] if closed_results else -10**9
                        if di_global-last_loss_idx<=policy["global_cd_sessions"]:
                            skipped_global_cd+=1
                            continue

                # Same-symbol cooldown after a losing exit.
                if policy.get("symbol_cd_sessions"):
                    li=last_symbol_loss_idx.get(s)
                    if li is not None and di_global-li<=policy["symbol_cd_sessions"]:
                        skipped_symbol_cd+=1
                        continue

                # Breadth slope filter uses only the completed SIGNAL day.
                # This avoids looking at the entry day's still-forming RTH session.
                if policy.get("breadth_slope_pp") is not None:
                    look=policy.get("breadth_slope_sessions",5)
                    sd=datetime.fromisoformat(chosen["signal_date"]).date()
                    si_global=sess_idx.get(sd)
                    if si_global is not None and si_global>=look:
                        d0=all_dates[si_global-look]
                        b0=bseries.get(d0);b1=bseries.get(sd)
                        if b0 is not None and b1 is not None and (b1-b0)<=-policy["breadth_slope_pp"]:
                            skipped_breadth_slope+=1
                            continue

                raw=bar["o"] if bar["o"]>=chosen["entry_stop"] else chosen["entry_stop"]
                fill=raw*(1+SLIPPAGE_BPS/10000)
                risk=fill-chosen["initial_stop"]
                if risk<=0:
                    used_signals.add((s,chosen["signal_t"]));continue
                candidates.append((chosen["ret60"],s,bar,chosen,fill,risk))

            slots=max(0,MAX_POSITIONS-len(openpos))
            candidates.sort(key=lambda x:(-x[0],x[1]))
            admitted=candidates[:slots]
            blocked=candidates[slots:]
            skipped_cap+=len(blocked)

            for _,s,bar,sig,fill,risk in admitted:
                used_signals.add((s,sig["signal_t"]))
                di=date_idx[s].get(d)
                if di is None:continue
                prev_close=dailies[s][di-1]["c"] if di>0 else fill
                pos={
                  "symbol":s,"signal_t":sig["signal_t"],"entry_t":bar["t"],"entry":fill,
                  "initial_stop":sig["initial_stop"],"stop":sig["initial_stop"],
                  "initial_risk":risk,"signal_ret60":sig["ret60"],
                  "signal_risk_pct":sig["risk_pct"],"signal_breadth":sig["breadth"],
                  "highest_close":prev_close,"hold_days":0
                }
                openpos[s]=pos

                if bar["l"]<=pos["stop"]:
                    raw_exit=bar["o"] if bar["o"]<pos["stop"] else pos["stop"]
                    exit_fill=raw_exit*(1-SLIPPAGE_BPS/10000)
                    tr=close_trade(pos,bar["t"],exit_fill,"STOP")
                    trades.append(tr);del openpos[s];last_exit_date[s]=d
                    closed_results.append((di_global,tr["r"]))
                    if tr["r"]<0:last_symbol_loss_idx[s]=di_global

        # 3) EOD trailing/time exits.
        for s,pos in list(openpos.items()):
            di=date_idx[s].get(d)
            if di is None:continue
            D=dailies[s];x=D[di]
            pos["hold_days"]+=1
            pos["highest_close"]=max(pos["highest_close"],x["c"])
            pos["stop"]=max(pos["stop"],pos["highest_close"]-TRAIL_ATR*x["atr14"])
            if pos["hold_days"]>=MAX_HOLD_DAYS:
                exit_fill=x["c"]*(1-SLIPPAGE_BPS/10000)
                tr=close_trade(pos,x["ct"],exit_fill,"TIME")
                trades.append(tr);del openpos[s];last_exit_date[s]=d
                closed_results.append((di_global,tr["r"]))
                if tr["r"]<0:last_symbol_loss_idx[s]=di_global

    return trades,{
      "cap":skipped_cap,
      "global_cooldown":skipped_global_cd,
      "symbol_cooldown":skipped_symbol_cd,
      "breadth_slope":skipped_breadth_slope
    }

def stats(ts):
    n=len(ts);w=sum(t["r"]>0 for t in ts);l=sum(t["r"]<0 for t in ts)
    net=sum(t["r"] for t in ts);gp=sum(t["r"] for t in ts if t["r"]>0);gl=sum(t["r"] for t in ts if t["r"]<0)
    return {"closed":n,"wins":w,"losses":l,"win_rate":w/n if n else None,
            "net_r":net,"avg_r":net/n if n else None,"profit_factor":gp/abs(gl) if gl<0 else None}

def main():
    by,months=collect()
    adj={};dailies={}
    for s,bars in by.items():
        if not bars:continue
        a=apply_splits(bars,detect_splits(bars));adj[s]=a
        D=enrich_daily(aggregate_daily(a))
        if D:dailies[s]=D

    signals=make_signals(dailies)
    policies={
      "baseline":{},
      "loss2_cd3":{"loss_streak_n":2,"global_cd_sessions":3},
      "symbol_loss_cd5":{"symbol_cd_sessions":5},
      "breadth_drop10pp_5d":{"breadth_slope_pp":0.10,"breadth_slope_sessions":5},
      "combo_loss2cd3_symbol5_breadthdrop10":{
        "loss_streak_n":2,"global_cd_sessions":3,
        "symbol_cd_sessions":5,
        "breadth_slope_pp":0.10,"breadth_slope_sessions":5
      }
    }

    lo=int(EVAL_START.timestamp()*1000);hi=int(EVAL_END.timestamp()*1000)
    results={}
    for name,policy in policies.items():
        alltrades,skips=simulate_portfolio(adj,dailies,signals,policy)
        trades=[t for t in alltrades if lo<=t["entry_t"]<hi]
        trades.sort(key=lambda x:(x["entry_t"],x["symbol"]))
        results[name]={
          "policy":policy,
          "skip_events":skips,
          "totals":stats(trades),
          "trades":trades
        }
        print("POLICY",name,"trades",len(trades),"R",round(sum(t["r"] for t in trades),4),"skips",skips,flush=True)

    report={
      "generated_at":datetime.now(UTC).isoformat(),
      "strategy":"M1_B2_loss_streak_controls",
      "rules":{
        "base":"same locked M1-B2 state machine: breadth>=50%, max 2 positions",
        "loss2_cd3":"after 2 consecutive losing exits, reject new admissions for 3 market sessions from the latest losing exit",
        "symbol_loss_cd5":"after a losing exit in a symbol, reject that symbol for 5 market sessions",
        "breadth_drop10pp_5d":"reject new admission if current breadth is at least 10 percentage points below breadth 5 market sessions earlier",
        "combo":"all three controls simultaneously"
      },
      "shard":{"eval_start":EVAL_START.isoformat(),"eval_end_exclusive":EVAL_END.isoformat(),
               "sim_start":SIM_START.isoformat(),"warmup_start":WARMUP_START.isoformat(),"data_end":DATA_END.isoformat()},
      "months_loaded":months,"signals":len(signals),"results":results
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("FINAL",json.dumps({k:v["totals"] for k,v in results.items()}),flush=True)
if __name__=="__main__":main()
