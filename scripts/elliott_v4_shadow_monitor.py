import json, math, os, statistics, time
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, time as dtime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import backtest_elliott_wave3_v0_crypto as core
import backtest_elliott_wave3_v3_bbreak as v3

ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/"data/forward/elliott_v4_shadow_journal.json"

UTC=timezone.utc
NY=ZoneInfo("America/New_York")

# Existing Stock53 monitored universe. Forward validation stats use plain-equity names only;
# ETFs/leveraged/crypto proxies remain observable but are tagged ineligible.
SYMS=(
"AAPL","AMZN","AVGO","CRCL","DELL","MSFT","MU","SNDK","SNXX","SOXL","SPCX",
"AMD","BABA","INTC","JPM","KORU","MSTR","NFLX","SKHY","SMCI","SOXS","V",
"COST","GOOGL","LLY","META","NBIS","NVDA","QQQ","TSLA","UBER","WMT",
"AMAT","CAT","DRAM","EWY","HD","MRVL","MUU","ORCL","SPY","TSM",
"AAOI","AXTI","BE","COIN","CRM","CSCO","DIS","HOOD","IBM","LITE","TQQQ"
)

NON_VALIDATION=set(("SOXL","SOXS","TQQQ","QQQ","SPY","EWY","KORU","MSTR","COIN",
                    "SPCX","SKHY","DRAM","MUU"))
VALIDATION_SYMS=tuple(s for s in SYMS if s not in NON_VALIDATION)

ENTRY_VALID_SIGNAL_BARS=12
MAX_HOLD_SIGNAL_BARS=48
TP1_FRAC=0.50

def now_ms():
    return int(datetime.now(UTC).timestamp()*1000)

def iso(ms):
    return datetime.fromtimestamp(ms/1000,UTC).isoformat()

def fetch_yahoo_15m(sym):
    url=("https://query1.finance.yahoo.com/v8/finance/chart/"
         +quote(sym,safe="")+"?range=60d&interval=15m&includePrePost=false&events=div%2Csplits")
    req=Request(url,headers={"User-Agent":"Mozilla/5.0"})
    last=None
    for attempt in range(4):
        try:
            with urlopen(req,timeout=25) as resp:
                obj=json.loads(resp.read().decode("utf-8"))
            result=obj.get("chart",{}).get("result")
            if not result:
                raise RuntimeError(str(obj.get("chart",{}).get("error")))
            r=result[0];ts=r.get("timestamp") or []
            q=(r.get("indicators",{}).get("quote") or [{}])[0]
            out=[]
            for i,sec in enumerate(ts):
                vals=[]
                for k in ("open","high","low","close"):
                    a=q.get(k) or []
                    vals.append(a[i] if i<len(a) else None)
                if any(x is None for x in vals):
                    continue
                dt=datetime.fromtimestamp(sec,UTC).astimezone(NY)
                if not(dtime(9,30)<=dt.time()<dtime(16,0)):
                    continue
                t=int(sec*1000)
                v=(q.get("volume") or [])
                out.append({"t":t,"ct":t+15*60_000,"o":float(vals[0]),"h":float(vals[1]),
                            "l":float(vals[2]),"c":float(vals[3]),
                            "v":float(v[i] if i<len(v) and v[i] is not None else 0)})
            out.sort(key=lambda z:z["t"])
            # Yahoo can occasionally duplicate bars around corrections.
            ded={x["t"]:x for x in out}
            return [ded[k] for k in sorted(ded)]
        except Exception as e:
            last=e
            time.sleep(2*(attempt+1))
    raise RuntimeError(f"Yahoo fetch failed {sym}: {last!r}")

def aggregate_1h(b15):
    by=defaultdict(list)
    for b in b15:
        dt=datetime.fromtimestamp(b["t"]/1000,UTC).astimezone(NY)
        by[dt.date()].append(b)
    out=[]
    for d in sorted(by):
        xs=sorted(by[d],key=lambda z:z["t"])
        # Exact research convention: six complete 60m bars 09:30-15:30.
        # 15:30-16:00 remains execution-only.
        by_clock={datetime.fromtimestamp(x["t"]/1000,UTC).astimezone(NY).strftime("%H:%M"):x for x in xs}
        starts=("09:30","10:30","11:30","12:30","13:30","14:30")
        for st in starts:
            hh,mm=map(int,st.split(":"))
            keys=[]
            for k in range(4):
                mins=hh*60+mm+15*k
                keys.append(f"{mins//60:02d}:{mins%60:02d}")
            part=[by_clock[k] for k in keys if k in by_clock]
            if len(part)!=4:
                continue
            out.append({"t":part[0]["t"],"ct":part[-1]["ct"],"o":part[0]["o"],
                        "h":max(x["h"] for x in part),"l":min(x["l"] for x in part),
                        "c":part[-1]["c"],"v":sum(x["v"] for x in part)})
    return out

def signal_id(sym,activation,sig):
    return f"{sym}:{activation}:{sig['side']}:{sig['entry']:.8f}:{sig['sl']:.8f}"

def all_signals(sym,b15):
    d=core.enrich_atr(aggregate_1h(b15))
    ps=core.zigzag(d)
    out=[]
    for k in range(8,len(ps)):
        sig=v3.make_v3_signal(d,ps[k-8:k+1])
        if not sig or sig["side"]!="LONG":
            continue
        act=d[sig["known_i"]]["ct"]
        out.append({
          "id":signal_id(sym,act,sig),"symbol":sym,"activation":act,
          "entry":sig["entry"],"sl":sig["sl"],"tp1":sig["tp1"],"tp2":sig["tp2"],"risk":sig["risk"],
          "wave2_retracement":sig.get("wave2_retracement"),
          "abc_b_retracement":sig.get("abc_b_retracement"),
          "abc_c_to_a":sig.get("abc_c_to_a"),
          "validation_eligible":sym in VALIDATION_SYMS,
        })
    return d,out

def signal_bar_expiry(d,activation,n):
    closes=[x["ct"] for x in d]
    i=bisect_left(closes,activation)
    if i>=len(d):
        return activation
    return d[min(i+n,len(d)-1)]["ct"]

def hold_expiry(d,fill_t,n):
    closes=[x["ct"] for x in d]
    i=bisect_left(closes,fill_t)
    if i>=len(d):
        return fill_t
    return d[min(i+n,len(d)-1)]["ct"]

def evaluate(sig,d,b15):
    t15=[x["t"] for x in b15]
    start=bisect_left(t15,sig["activation"])
    valid=signal_bar_expiry(d,sig["activation"],ENTRY_VALID_SIGNAL_BARS)
    latest=b15[-1]["ct"] if b15 else 0
    fill_i=None;fill=None
    for j in range(start,len(b15)):
        b=b15[j]
        if b["t"]>=valid:
            break
        if b["o"]>=sig["entry"]:
            fill_i,fill=j,b["o"];break
        if b["l"]<=sig["sl"]:
            return {"status":"CANCELLED","reason":"C_LOW_BROKEN_BEFORE_ENTRY","valid_until":valid}
        if b["h"]>=sig["entry"]:
            fill_i,fill=j,sig["entry"];break
    if fill_i is None:
        if latest>=valid:
            return {"status":"EXPIRED","reason":"ENTRY_NOT_TOUCHED","valid_until":valid}
        return {"status":"PENDING","valid_until":valid}

    pnl=-core.cost(fill);rem=1.0;stop=sig["sl"];hit1=hit2=False
    exit_t=None;reason=None;last_i=fill_i
    hold_until=hold_expiry(d,b15[fill_i]["t"],MAX_HOLD_SIGNAL_BARS)
    for j in range(fill_i,len(b15)):
        b=b15[j]
        if b["t"]>=hold_until:
            break
        last_i=j
        if b["o"]<=stop:
            pnl+=rem*(b["o"]-fill)-core.cost(b["o"],rem);rem=0;exit_t=b["ct"];reason="GAP_STOP";break
        if b["l"]<=stop:
            pnl+=rem*(stop-fill)-core.cost(stop,rem);rem=0;exit_t=b["ct"];reason="STOP";break
        if not hit1:
            px=b["o"] if b["o"]>=sig["tp1"] else (sig["tp1"] if b["h"]>=sig["tp1"] else None)
            if px is not None:
                f=min(TP1_FRAC,rem)
                pnl+=f*(px-fill)-core.cost(px,f);rem-=f;hit1=True;stop=max(stop,fill)
                if rem>0 and b["l"]<=stop:
                    pnl+=rem*(stop-fill)-core.cost(stop,rem);rem=0;exit_t=b["ct"];reason="BE_AFTER_TP1";break
        if rem>0 and hit1 and (b["o"]>=sig["tp2"] or b["h"]>=sig["tp2"]):
            px=b["o"] if b["o"]>=sig["tp2"] else sig["tp2"]
            pnl+=rem*(px-fill)-core.cost(px,rem);rem=0;hit2=True;exit_t=b["ct"];reason="TP2";break

    if rem>0 and latest>=hold_until:
        b=b15[last_i];px=b["c"]
        pnl+=rem*(px-fill)-core.cost(px,rem);rem=0;exit_t=b["ct"];reason="TIME"

    base={"entry_t":b15[fill_i]["t"],"fill":fill,"tp1_hit":hit1,"tp2_hit":hit2,
          "current_stop":stop,"hold_until":hold_until}
    if rem==0:
        base.update({"status":"CLOSED","exit_t":exit_t,"reason":reason,"r":pnl/sig["risk"]})
    else:
        last=b15[-1]["c"]
        unreal=pnl+rem*(last-fill)-core.cost(last,rem)
        base.update({"status":"OPEN","remaining":rem,"unrealized_r":unreal/sig["risk"]})
    return base

def empty_state(start_ms,seen):
    return {
      "strategy":"Elliott Wave 3 v4 shadow forward",
      "mode":"SHADOW_ONLY_NO_ORDERS",
      "started_at":iso(start_ms),"started_ms":start_ms,
      "universe":list(SYMS),"validation_universe":list(VALIDATION_SYMS),
      "seen_signal_ids":sorted(seen),"tracked":{},"events":[],
      "summary":{"signals":0,"entries":0,"closed":0,"total_r":0.0,"avg_r":None,"profit_factor":None}
    }

def calc_summary(st):
    xs=[x for x in st["tracked"].values() if x.get("validation_eligible") and x.get("status")=="CLOSED"]
    rs=[x["r"] for x in xs]
    pos=[r for r in rs if r>0];neg=[r for r in rs if r<0]
    return {
      "signals":sum(1 for x in st["tracked"].values() if x.get("validation_eligible")),
      "entries":sum(1 for x in st["tracked"].values() if x.get("validation_eligible") and x.get("entry_t") is not None),
      "closed":len(xs),"total_r":sum(rs),
      "avg_r":statistics.fmean(rs) if rs else None,
      "profit_factor":sum(pos)/abs(sum(neg)) if neg else None,
    }

def append_event(st,typ,sig,extra=None):
    e={"time":iso(now_ms()),"type":typ,"signal_id":sig["id"],"symbol":sig["symbol"],
       "validation_eligible":sig["validation_eligible"]}
    if extra:e.update(extra)
    st["events"].append(e)

def main():
    stamp=now_ms();market={}
    failures={}
    current_ids=set()
    signal_map={}
    dmap={}

    for sym in SYMS:
        try:
            bars=fetch_yahoo_15m(sym)
            if len(bars)<300:
                raise RuntimeError(f"insufficient 15m bars {len(bars)}")
            d,sigs=all_signals(sym,bars)
            market[sym]=bars;dmap[sym]=d
            for s in sigs:
                current_ids.add(s["id"]);signal_map[s["id"]]=s
        except Exception as e:
            failures[sym]=repr(e)
            print("FETCH_ERROR",sym,repr(e),flush=True)

    if not STATE.exists():
        st=empty_state(stamp,current_ids)
        STATE.parent.mkdir(parents=True,exist_ok=True)
        STATE.write_text(json.dumps(st,indent=2),encoding="utf-8")
        print("BOOTSTRAP",json.dumps({"started_at":st["started_at"],"baseline_seen":len(current_ids),
                                      "fetch_failures":failures},indent=2),flush=True)
        return

    st=json.loads(STATE.read_text(encoding="utf-8"))
    changed=False
    seen=set(st.get("seen_signal_ids",[]))

    # New signals are strictly forward: activation must be after monitor start.
    new=[s for sid,s in signal_map.items() if sid not in seen and s["activation"]>st["started_ms"]]
    new.sort(key=lambda s:(s["activation"],s["symbol"]))
    for sig in new:
        # Preserve one-position/pending-order semantics per symbol in the shadow book.
        active=any(x["symbol"]==sig["symbol"] and x.get("status") in ("PENDING","OPEN")
                   for x in st["tracked"].values())
        seen.add(sig["id"])
        if active:
            append_event(st,"SIGNAL_IGNORED_BUSY",sig,{"activation":iso(sig["activation"])})
            changed=True
            continue
        rec=dict(sig);rec.update({"status":"NEW","entry_t":None,"r":None})
        st["tracked"][sig["id"]]=rec
        append_event(st,"SIGNAL_NEW",sig,{
            "activation":iso(sig["activation"]),"entry":sig["entry"],"sl":sig["sl"],
            "tp1":sig["tp1"],"tp2":sig["tp2"]})
        changed=True

    # Re-evaluate tracked forward setups against the latest 15m tape.
    for sid,rec in list(st["tracked"].items()):
        if rec.get("status") in ("CLOSED","CANCELLED","EXPIRED"):
            continue
        sym=rec["symbol"]
        if sym not in market:
            continue
        prev_status=rec.get("status")
        prev_tp1=bool(rec.get("tp1_hit"))
        ev=evaluate(rec,dmap[sym],market[sym])
        rec.update(ev)
        if prev_status!=rec["status"]:
            append_event(st,rec["status"],rec,{
                "entry_t":iso(rec["entry_t"]) if rec.get("entry_t") else None,
                "fill":rec.get("fill"),"exit_t":iso(rec["exit_t"]) if rec.get("exit_t") else None,
                "reason":rec.get("reason"),"r":rec.get("r")})
            changed=True
        elif not prev_tp1 and rec.get("tp1_hit"):
            append_event(st,"TP1_HIT",rec,{"entry_t":iso(rec["entry_t"]),"current_stop":rec.get("current_stop")})
            changed=True

    st["seen_signal_ids"]=sorted(seen|current_ids)
    new_summary=calc_summary(st)
    if new_summary!=st.get("summary"):
        st["summary"]=new_summary;changed=True

    if changed:
        STATE.write_text(json.dumps(st,indent=2),encoding="utf-8")

    print("SHADOW_STATUS",json.dumps({
      "changed":changed,"new_signals":len(new),"tracked":len(st["tracked"]),
      "summary":st["summary"],"fetch_failures":failures
    },indent=2),flush=True)

if __name__=="__main__":
    main()
