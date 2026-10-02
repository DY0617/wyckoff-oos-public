import json
import statistics
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

import backtest_elliott_wave3_v0_crypto as core
import backtest_elliott_wave3_v3_bbreak as v3

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/cache/stock53_recent5y_15m.parquet"
OUT = ROOT / "data/validation/elliott_wave3_v3_stock30_1h_vs_1d_cross_asset_oos.json"

UTC = timezone.utc
NY = ZoneInfo("America/New_York")

SYMS = (
    "AAPL","AMZN","AVGO","MSFT","MU","AMD","INTC","JPM","NFLX","V",
    "COST","GOOGL","META","NVDA","QQQ","TSLA","UBER","WMT","AMAT","CAT",
    "HD","ORCL","SPY","TSM","CRM","CSCO","DIS","IBM","COIN","MSTR"
)

EVAL_START = datetime(2021, 4, 1, tzinfo=UTC)
EVAL_END = datetime(2026, 4, 1, tzinfo=UTC)

ENTRY_VALID_SIGNAL_BARS = 12
MAX_HOLD_SIGNAL_BARS = 48
TP1_FRAC = 0.50
SPLIT_FACTORS = (1.5, 2, 3, 4, 5, 7, 10, 15, 20)


def to_ms(ts):
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=NY)
    return int(ts.astimezone(UTC).timestamp() * 1000)


def load_symbol(con, sym):
    rows = con.execute(
        """
        SELECT b,o,h,l,c,v
        FROM read_parquet(?)
        WHERE symbol=?
        ORDER BY b
        """,
        [str(DATA), sym],
    ).fetchall()
    out = []
    for ts, o, h, l, c, v in rows:
        t = to_ms(ts)
        out.append({
            "t": t, "ct": t + 15*60_000,
            "o": float(o), "h": float(h), "l": float(l), "c": float(c), "v": float(v or 0),
        })
    return out


def ny_date(ms):
    return datetime.fromtimestamp(ms/1000, UTC).astimezone(NY).date()


def detect_splits_15m(bars):
    by_day = defaultdict(list)
    for b in bars:
        by_day[ny_date(b["t"])].append(b)
    events = []
    prev_close = None
    for d in sorted(by_day):
        xs = sorted(by_day[d], key=lambda z: z["t"])
        if not xs:
            continue
        op = xs[0]["o"]
        if prev_close and prev_close > 0 and op > 0:
            ratio = prev_close / op
            mag = ratio if ratio >= 1 else 1/ratio
            if mag >= 1.35:
                f = min(SPLIT_FACTORS, key=lambda q: abs(mag/q - 1.0))
                if abs(mag/f - 1.0) <= 0.05:
                    events.append((d, 1/f if ratio > 1 else f))
        prev_close = xs[-1]["c"]
    return events


def adjust_splits_15m(bars):
    events = detect_splits_15m(bars)
    if not events:
        return [dict(x) for x in bars], []
    out = []
    for b in bars:
        d = ny_date(b["t"])
        pm = 1.0
        for event_day, mult in events:
            if d < event_day:
                pm *= mult
        q = dict(b)
        for k in ("o","h","l","c"):
            q[k] *= pm
        out.append(q)
    return out, [(str(d), m) for d,m in events]


def rth_days(b15):
    by_day = defaultdict(list)
    for b in b15:
        dt = datetime.fromtimestamp(b["t"]/1000, UTC).astimezone(NY)
        if time(9,30) <= dt.time() < time(16,0):
            by_day[dt.date()].append(b)
    return by_day


def aggregate_rth_1h(b15):
    by_day = rth_days(b15)
    out = []
    for d in sorted(by_day):
        xs = sorted(by_day[d], key=lambda z: z["t"])
        # Six complete 60m bars 09:30-15:30. Final 15:30-16:00 is execution-only.
        for k in range(0, 24, 4):
            part = xs[k:k+4]
            if len(part) != 4:
                continue
            if part[-1]["ct"] - part[0]["t"] != 60*60_000:
                continue
            out.append({
                "t": part[0]["t"], "ct": part[-1]["ct"],
                "o": part[0]["o"], "h": max(x["h"] for x in part),
                "l": min(x["l"] for x in part), "c": part[-1]["c"],
                "v": sum(x["v"] for x in part),
            })
    return out


def aggregate_rth_daily(b15):
    by_day = rth_days(b15)
    out = []
    for d in sorted(by_day):
        xs = sorted(by_day[d], key=lambda z: z["t"])
        if len(xs) < 24:
            continue
        out.append({
            "t": xs[0]["t"], "ct": xs[-1]["ct"],
            "o": xs[0]["o"], "h": max(x["h"] for x in xs),
            "l": min(x["l"] for x in xs), "c": xs[-1]["c"],
            "v": sum(x["v"] for x in xs),
        })
    return out


def signal_expiry(d, ki, n):
    j = min(ki+n, len(d)-1)
    return d[j]["ct"]


def hold_expiry(d, fill_t, n):
    closes = [x["ct"] for x in d]
    i = bisect_left(closes, fill_t)
    j = min(i+n, len(d)-1)
    return d[j]["ct"]


def simulate_stock(sym, b15, signal_bars, label):
    d = core.enrich_atr(signal_bars)
    ps = core.zigzag(d)
    t15 = [x["t"] for x in b15]
    lo = int(EVAL_START.timestamp()*1000)
    hi = int(EVAL_END.timestamp()*1000)

    by_known = defaultdict(list)
    for k in range(8, len(ps)):
        sig = v3.make_v3_signal(d, ps[k-8:k+1])
        if sig:
            by_known[sig["known_i"]].append(sig)

    trades, st = [], defaultdict(int)
    busy_until = -1

    for ki in sorted(by_known):
        activation = d[ki]["ct"]
        if not (lo <= activation < hi):
            continue
        if activation < busy_until:
            st["signal_while_busy"] += 1
            continue

        sig = by_known[ki][-1]
        st["patterns"] += 1
        side = sig["side"]
        entry, sl, tp1, tp2, risk = sig["entry"], sig["sl"], sig["tp1"], sig["tp2"], sig["risk"]

        start = bisect_left(t15, activation)
        valid_until = signal_expiry(d, ki, ENTRY_VALID_SIGNAL_BARS)
        fill_i = None
        fill = None
        cancelled = False

        for j in range(start, len(b15)):
            b = b15[j]
            if b["t"] >= hi or b["t"] >= valid_until:
                break
            if side == "LONG":
                if b["o"] >= entry:
                    fill_i, fill = j, b["o"]; break
                if b["l"] <= sl:
                    cancelled = True; break
                if b["h"] >= entry:
                    fill_i, fill = j, entry; break
            else:
                if b["o"] <= entry:
                    fill_i, fill = j, b["o"]; break
                if b["h"] >= sl:
                    cancelled = True; break
                if b["l"] <= entry:
                    fill_i, fill = j, entry; break

        if fill_i is None:
            st["cancelled_before_entry" if cancelled else "entry_expired"] += 1
            busy_until = valid_until
            continue

        st["filled"] += 1
        pnl = -core.cost(fill)
        rem = 1.0
        stop = sl
        hit1 = hit2 = False
        exit_t = b15[fill_i]["ct"]
        reason = "TIME"
        hold_until = hold_expiry(d, b15[fill_i]["t"], MAX_HOLD_SIGNAL_BARS)
        last_i = fill_i

        for j in range(fill_i, len(b15)):
            b = b15[j]
            if b["t"] >= hi or b["t"] >= hold_until:
                break
            last_i = j

            if side == "LONG":
                if b["o"] <= stop:
                    pnl += rem*(b["o"]-fill) - core.cost(b["o"], rem)
                    rem = 0; exit_t = b["ct"]; reason = "GAP_STOP"; break
                if b["l"] <= stop:
                    pnl += rem*(stop-fill) - core.cost(stop, rem)
                    rem = 0; exit_t = b["ct"]; reason = "STOP"; break
                if not hit1:
                    px = b["o"] if b["o"] >= tp1 else (tp1 if b["h"] >= tp1 else None)
                    if px is not None:
                        f = min(TP1_FRAC, rem)
                        pnl += f*(px-fill) - core.cost(px, f)
                        rem -= f; hit1 = True; stop = max(stop, fill)
                        if rem > 0 and b["l"] <= stop:
                            pnl += rem*(stop-fill) - core.cost(stop, rem)
                            rem = 0; exit_t = b["ct"]; reason = "BE_AFTER_TP1"; break
                if rem > 0 and hit1 and (b["o"] >= tp2 or b["h"] >= tp2):
                    px = b["o"] if b["o"] >= tp2 else tp2
                    pnl += rem*(px-fill) - core.cost(px, rem)
                    rem = 0; hit2 = True; exit_t = b["ct"]; reason = "TP2"; break
            else:
                if b["o"] >= stop:
                    pnl += rem*(fill-b["o"]) - core.cost(b["o"], rem)
                    rem = 0; exit_t = b["ct"]; reason = "GAP_STOP"; break
                if b["h"] >= stop:
                    pnl += rem*(fill-stop) - core.cost(stop, rem)
                    rem = 0; exit_t = b["ct"]; reason = "STOP"; break
                if not hit1:
                    px = b["o"] if b["o"] <= tp1 else (tp1 if b["l"] <= tp1 else None)
                    if px is not None:
                        f = min(TP1_FRAC, rem)
                        pnl += f*(fill-px) - core.cost(px, f)
                        rem -= f; hit1 = True; stop = min(stop, fill)
                        if rem > 0 and b["h"] >= stop:
                            pnl += rem*(fill-stop) - core.cost(stop, rem)
                            rem = 0; exit_t = b["ct"]; reason = "BE_AFTER_TP1"; break
                if rem > 0 and hit1 and (b["o"] <= tp2 or b["l"] <= tp2):
                    px = b["o"] if b["o"] <= tp2 else tp2
                    pnl += rem*(fill-px) - core.cost(px, rem)
                    rem = 0; hit2 = True; exit_t = b["ct"]; reason = "TP2"; break

        if rem > 0:
            b = b15[last_i]
            px = b["c"]
            pnl += rem*((px-fill) if side == "LONG" else (fill-px)) - core.cost(px, rem)
            exit_t = b["ct"]; reason = "TIME"

        trades.append({
            "symbol": sym, "timeframe": label, "direction": side,
            "signal_t": activation, "entry_t": b15[fill_i]["t"], "exit_t": exit_t,
            "entry": entry, "fill": fill, "initial_sl": sl, "tp1": tp1, "tp2": tp2,
            "risk": risk, "r": pnl/risk, "reason": reason,
            "tp1_hit": hit1, "tp2_hit": hit2,
            "wave2_retracement": sig.get("wave2_retracement"),
            "abc_b_retracement": sig.get("abc_b_retracement"),
            "abc_c_to_a": sig.get("abc_c_to_a"),
            "impulse_atr": sig.get("impulse_atr"),
            "risk_atr": sig.get("risk_atr"),
        })
        busy_until = exit_t

    st = dict(st)
    st["fill_rate"] = st.get("filled",0)/st.get("patterns",1) if st.get("patterns",0) else None
    st["signal_bars"] = len(d)
    st["pivots"] = len(ps)
    return trades, st


def metrics(ts):
    o = sorted(ts, key=lambda z:(z["exit_t"],z["symbol"],z["timeframe"]))
    rs = [x["r"] for x in o]
    pos = [r for r in rs if r>0]
    neg = [r for r in rs if r<0]
    eq=peak=0.0; dd=0.0; cur=streak=0
    for r in rs:
        eq += r; peak=max(peak,eq); dd=min(dd,eq-peak)
        if r<0:
            cur += 1; streak=max(streak,cur)
        else:
            cur=0
    return {
        "trades":len(o),
        "long":sum(t["direction"]=="LONG" for t in o),
        "short":sum(t["direction"]=="SHORT" for t in o),
        "win_rate":len(pos)/len(o) if o else None,
        "total_r":sum(rs),
        "avg_r":statistics.fmean(rs) if rs else None,
        "profit_factor":sum(pos)/abs(sum(neg)) if neg else None,
        "max_drawdown_r":dd,
        "max_losing_streak":streak,
        "tp1_hit_rate":sum(t["tp1_hit"] for t in o)/len(o) if o else None,
        "tp2_hit_rate":sum(t["tp2_hit"] for t in o)/len(o) if o else None,
    }


def grouped(ts,key):
    g=defaultdict(list)
    for t in ts:g[t[key]].append(t)
    return {k:metrics(v) for k,v in sorted(g.items())}


def main():
    if not DATA.exists():
        raise FileNotFoundError(DATA)
    con=duckdb.connect()

    alltr=[]
    cells={}
    for i,sym in enumerate(SYMS,1):
        raw=load_symbol(con,sym)
        adj,splits=adjust_splits_15m(raw)
        if len(adj)<500:
            continue

        h1=aggregate_rth_1h(adj)
        d1=aggregate_rth_daily(adj)

        t1,s1=simulate_stock(sym,adj,h1,"1H_RTH")
        td,sd=simulate_stock(sym,adj,d1,"1D_RTH")
        cells[sym]={
            "1H":{"metrics":metrics(t1),"stats":s1},
            "1D":{"metrics":metrics(td),"stats":sd},
            "splits":splits,
        }
        alltr += t1 + td
        print("RESULT",i,len(SYMS),sym,"1H",json.dumps(cells[sym]["1H"]),"1D",json.dumps(cells[sym]["1D"]),flush=True)

    con.close()

    years=defaultdict(list)
    for t in alltr:
        years[str(datetime.fromtimestamp(t["entry_t"]/1000,UTC).year)].append(t)

    by_tf=grouped(alltr,"timeframe")
    by_dir_tf={}
    for tf in ("1H_RTH","1D_RTH"):
        q=[t for t in alltr if t["timeframe"]==tf]
        by_dir_tf[tf]=grouped(q,"direction")

    out={
        "strategy":"Elliott Wave 3 v3 B-wave breakout — Stock30 1H vs 1D cross-asset OOS",
        "purpose":"Compare natural US RTH 1H and RTH daily signal clocks using exact frozen v3 logic; no stock tuning.",
        "asset_class":"US equities/ETFs RTH cash chart research proxy",
        "universe":list(SYMS),
        "period":{"eval_start":EVAL_START.isoformat(),"eval_end_exclusive":EVAL_END.isoformat()},
        "clock":{
            "1H":"six complete 60m RTH bars 09:30-15:30 ET; final 15:30-16:00 execution-only",
            "1D":"full RTH daily 09:30-16:00 ET",
            "execution":"15m RTH only",
            "entry_validity":"12 signal bars of each timeframe",
            "max_hold":"48 signal bars of each timeframe",
        },
        "costs":{"fee_bps":core.FEE_BPS,"slippage_bps":core.SLIP_BPS,"per_fill_total_bps":core.COST_BPS},
        "timeframes":by_tf,
        "timeframe_directions":by_dir_tf,
        "years":{k:metrics(v) for k,v in sorted(years.items())},
        "symbols":cells,
        "trades":alltr,
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2),encoding="utf-8")
    print("FINAL",json.dumps({"timeframes":by_tf,"timeframe_directions":by_dir_tf},indent=2),flush=True)


if __name__=="__main__":
    main()
