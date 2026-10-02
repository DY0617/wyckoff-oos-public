import json
import statistics
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import backtest_trend_structure_v0_1_crypto as base

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/validation/elliott_wave3_v0_crypto_5y.json"
UTC = timezone.utc
SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT")
TIMEFRAMES = (60, 240)
FETCH_START = datetime(2021, 8, 1, tzinfo=UTC)
EVAL_START = datetime(2021, 10, 1, tzinfo=UTC)
EVAL_END = datetime(2026, 10, 1, tzinfo=UTC)

ATR_N = 14
PIVOT_REV_ATR = 1.50
W1_MIN_ATR = 2.00
W2_RET_MIN, W2_RET_MAX = 0.382, 0.786
W2_MAX_DUR_RATIO = 2.50
SL_BUFFER_ATR = 0.15
ENTRY_VALID_BARS = 12
MAX_HOLD_BARS = 48
TP1_EXT, TP2_EXT = 1.000, 1.618
TP1_FRAC = 0.50
FEE_BPS, SLIP_BPS = 4.0, 2.0
COST_BPS = FEE_BPS + SLIP_BPS


def load_15m(sym):
    base.FETCH_START = FETCH_START
    base.EVAL_END = EVAL_END
    return base.load_15m(sym)


def aggregate(xs, minutes):
    return base.aggregate(xs, minutes)


def enrich_atr(d):
    atr = None
    for i, x in enumerate(d):
        pc = d[i - 1]["c"] if i else x["c"]
        tr = max(x["h"] - x["l"], abs(x["h"] - pc), abs(x["l"] - pc))
        atr = tr if atr is None else ((ATR_N - 1) * atr + tr) / ATR_N
        x["atr14"] = atr
    return d


def zigzag(d):
    """ATR reversal ZigZag. A pivot is usable only from its known bar onward."""
    if len(d) <= ATR_N:
        return []
    ps = []
    s = ATR_N
    direction = 0
    hi, hi_i = d[s]["h"], s
    lo, lo_i = d[s]["l"], s
    for i in range(s + 1, len(d)):
        x, a = d[i], d[i]["atr14"]
        rev = PIVOT_REV_ATR * a
        if direction == 0:
            if x["h"] >= hi:
                hi, hi_i = x["h"], i
            if x["l"] <= lo:
                lo, lo_i = x["l"], i
            if lo_i < hi_i and hi - lo >= rev:
                ps.append({"type": "L", "idx": lo_i, "price": lo, "known": i})
                direction = 1
            elif hi_i < lo_i and hi - lo >= rev:
                ps.append({"type": "H", "idx": hi_i, "price": hi, "known": i})
                direction = -1
            continue
        if direction == 1:
            if x["h"] >= hi:
                hi, hi_i = x["h"], i
            if hi - x["l"] >= rev and hi_i < i:
                ps.append({"type": "H", "idx": hi_i, "price": hi, "known": i})
                direction = -1
                lo, lo_i = x["l"], i
        else:
            if x["l"] <= lo:
                lo, lo_i = x["l"], i
            if x["h"] - lo >= rev and lo_i < i:
                ps.append({"type": "L", "idx": lo_i, "price": lo, "known": i})
                direction = 1
                hi, hi_i = x["h"], i
    return ps


def bucket(r):
    if r < 0.500:
        return "0.382-0.500"
    if r < 0.618:
        return "0.500-0.618"
    return "0.618-0.786"


def wave3_pattern(d, p0, p1, p2):
    types = p0["type"] + p1["type"] + p2["type"]
    if types not in ("LHL", "HLH"):
        return None
    side = "LONG" if types == "LHL" else "SHORT"
    w1 = p1["price"] - p0["price"] if side == "LONG" else p0["price"] - p1["price"]
    if w1 <= 0:
        return None
    base_atr = max(d[p0["idx"]]["atr14"], d[p1["idx"]]["atr14"])
    if w1 < W1_MIN_ATR * base_atr:
        return None
    if side == "LONG":
        if p2["price"] <= p0["price"]:
            return None
        retr = (p1["price"] - p2["price"]) / w1
    else:
        if p2["price"] >= p0["price"]:
            return None
        retr = (p2["price"] - p1["price"]) / w1
    if not (W2_RET_MIN <= retr <= W2_RET_MAX):
        return None
    d1, d2 = p1["idx"] - p0["idx"], p2["idx"] - p1["idx"]
    if d1 <= 0 or d2 <= 0 or d2 > W2_MAX_DUR_RATIO * d1:
        return None
    ki = p2["known"]
    a = d[ki]["atr14"]
    if side == "LONG":
        entry, sl = p1["price"], p2["price"] - SL_BUFFER_ATR * a
        tp1, tp2 = p2["price"] + TP1_EXT * w1, p2["price"] + TP2_EXT * w1
        if not (sl < entry < tp1 < tp2):
            return None
    else:
        entry, sl = p1["price"], p2["price"] + SL_BUFFER_ATR * a
        tp1, tp2 = p2["price"] - TP1_EXT * w1, p2["price"] - TP2_EXT * w1
        if not (sl > entry > tp1 > tp2):
            return None
    risk = abs(entry - sl)
    return {
        "side": side, "known_i": ki, "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2,
        "risk": risk, "risk_atr": risk / a, "wave1_atr": w1 / base_atr,
        "retracement": retr, "retracement_bucket": bucket(retr),
        "wave1_bars": d1, "wave2_bars": d2,
    }


def cost(px, frac=1.0):
    return frac * px * COST_BPS / 10000.0


def metrics(ts):
    o = sorted(ts, key=lambda z: (z["exit_t"], z["symbol"], z["timeframe"]))
    rs = [x["r"] for x in o]
    pos, neg = [r for r in rs if r > 0], [r for r in rs if r < 0]
    eq = peak = 0.0
    dd = 0.0
    cur = streak = 0
    for r in rs:
        eq += r
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
        if r < 0:
            cur += 1
            streak = max(streak, cur)
        else:
            cur = 0
    return {
        "trades": len(o), "long": sum(x["direction"] == "LONG" for x in o),
        "short": sum(x["direction"] == "SHORT" for x in o),
        "win_rate": len(pos) / len(o) if o else None, "total_r": sum(rs),
        "avg_r": statistics.fmean(rs) if rs else None,
        "profit_factor": sum(pos) / abs(sum(neg)) if neg else None,
        "max_drawdown_r": dd, "max_losing_streak": streak,
        "tp1_hit_rate": sum(x["tp1_hit"] for x in o) / len(o) if o else None,
        "tp2_hit_rate": sum(x["tp2_hit"] for x in o) / len(o) if o else None,
        "avg_hold_hours": statistics.fmean(x["hold_hours"] for x in o) if o else None,
    }


def simulate(sym, b15, tf, direction_filter=None):
    d = enrich_atr(aggregate(b15, tf))
    ps = zigzag(d)
    t15 = [x["t"] for x in b15]
    lo, hi = int(EVAL_START.timestamp() * 1000), int(EVAL_END.timestamp() * 1000)
    sig_ms = tf * 60_000
    by_known = defaultdict(list)
    for k in range(2, len(ps)):
        s = wave3_pattern(d, ps[k - 2], ps[k - 1], ps[k])
        if s and (direction_filter is None or s["side"] == direction_filter):
            by_known[s["known_i"]].append(s)
    trades, st = [], defaultdict(int)
    busy_until = -1
    for ki in sorted(by_known):
        activation = d[ki]["ct"]
        if not (lo <= activation < hi):
            continue
        if activation < busy_until:
            st["signal_while_busy"] += 1
            continue
        s = by_known[ki][-1]
        st["patterns"] += 1
        side, entry, sl, tp1, tp2, risk = s["side"], s["entry"], s["sl"], s["tp1"], s["tp2"], s["risk"]
        start = bisect_left(t15, activation)
        valid_until = activation + ENTRY_VALID_BARS * sig_ms
        fill_i = fill = None
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
        pnl, rem, stop = -cost(fill), 1.0, sl
        hit1 = hit2 = False
        exit_t, reason = b15[fill_i]["ct"], "TIME"
        hold_until = b15[fill_i]["t"] + MAX_HOLD_BARS * sig_ms
        last_i = fill_i
        for j in range(fill_i, len(b15)):
            b = b15[j]
            if b["t"] >= hi or b["t"] >= hold_until:
                break
            last_i = j
            if side == "LONG":
                if b["o"] <= stop:
                    pnl += rem * (b["o"] - fill) - cost(b["o"], rem); rem = 0; exit_t = b["ct"]; reason = "GAP_STOP"; break
                if b["l"] <= stop:
                    pnl += rem * (stop - fill) - cost(stop, rem); rem = 0; exit_t = b["ct"]; reason = "STOP"; break
                if not hit1:
                    px = b["o"] if b["o"] >= tp1 else (tp1 if b["h"] >= tp1 else None)
                    if px is not None:
                        f = min(TP1_FRAC, rem); pnl += f * (px - fill) - cost(px, f); rem -= f; hit1 = True; stop = max(stop, fill)
                        if rem > 0 and b["l"] <= stop:
                            pnl += rem * (stop - fill) - cost(stop, rem); rem = 0; exit_t = b["ct"]; reason = "BE_AFTER_TP1"; break
                if rem > 0 and hit1 and (b["o"] >= tp2 or b["h"] >= tp2):
                    px = b["o"] if b["o"] >= tp2 else tp2
                    pnl += rem * (px - fill) - cost(px, rem); rem = 0; hit2 = True; exit_t = b["ct"]; reason = "TP2"; break
            else:
                if b["o"] >= stop:
                    pnl += rem * (fill - b["o"]) - cost(b["o"], rem); rem = 0; exit_t = b["ct"]; reason = "GAP_STOP"; break
                if b["h"] >= stop:
                    pnl += rem * (fill - stop) - cost(stop, rem); rem = 0; exit_t = b["ct"]; reason = "STOP"; break
                if not hit1:
                    px = b["o"] if b["o"] <= tp1 else (tp1 if b["l"] <= tp1 else None)
                    if px is not None:
                        f = min(TP1_FRAC, rem); pnl += f * (fill - px) - cost(px, f); rem -= f; hit1 = True; stop = min(stop, fill)
                        if rem > 0 and b["h"] >= stop:
                            pnl += rem * (fill - stop) - cost(stop, rem); rem = 0; exit_t = b["ct"]; reason = "BE_AFTER_TP1"; break
                if rem > 0 and hit1 and (b["o"] <= tp2 or b["l"] <= tp2):
                    px = b["o"] if b["o"] <= tp2 else tp2
                    pnl += rem * (fill - px) - cost(px, rem); rem = 0; hit2 = True; exit_t = b["ct"]; reason = "TP2"; break
        if rem > 0:
            b = b15[last_i]; px = b["c"]
            pnl += rem * ((px - fill) if side == "LONG" else (fill - px)) - cost(px, rem)
            rem = 0; exit_t = b["ct"]; reason = "TIME"
        trades.append({
            "symbol": sym, "timeframe": f"{tf // 60}H", "direction": side,
            "signal_t": activation, "entry_t": b15[fill_i]["t"], "exit_t": exit_t,
            "entry": entry, "fill": fill, "initial_sl": sl, "tp1": tp1, "tp2": tp2,
            "risk": risk, "risk_atr": s["risk_atr"], "wave1_atr": s["wave1_atr"],
            "retracement": s["retracement"], "retracement_bucket": s["retracement_bucket"],
            "wave1_bars": s["wave1_bars"], "wave2_bars": s["wave2_bars"],
            "r": pnl / risk, "reason": reason, "tp1_hit": hit1, "tp2_hit": hit2,
            "hold_hours": max(0.0, (exit_t - b15[fill_i]["t"]) / 3_600_000),
        })
        busy_until = exit_t
    st = dict(st)
    st["fill_rate"] = st.get("filled", 0) / st.get("patterns", 1) if st.get("patterns", 0) else None
    return trades, st, len(ps)


def grouped_metrics(alltr, key):
    g = defaultdict(list)
    for t in alltr:
        g[t[key]].append(t)
    return {k: metrics(v) for k, v in sorted(g.items())}


def main():
    alltr, cells = [], {}
    for sym in SYMBOLS:
        b15 = load_15m(sym)
        for tf in TIMEFRAMES:
            ts, st, npiv = simulate(sym, b15, tf)
            k = f"{sym}_{tf // 60}H"
            cells[k] = {"metrics": metrics(ts), "stats": st, "pivots": npiv}
            alltr += ts
            print("RESULT", k, json.dumps(cells[k]), flush=True)
    years = defaultdict(list)
    for t in alltr:
        years[str(datetime.fromtimestamp(t["entry_t"] / 1000, UTC).year)].append(t)
    out = {
        "strategy": "Elliott Wave 3 v0 frozen", "asset_class": "Binance USDT-M perpetual",
        "period": {"fetch_start": FETCH_START.isoformat(), "eval_start": EVAL_START.isoformat(), "eval_end_exclusive": EVAL_END.isoformat()},
        "rules": {
            "signal_timeframes": ["1H", "4H"], "execution_timeframe": "15m",
            "pivot_reversal_atr": PIVOT_REV_ATR, "wave1_min_atr": W1_MIN_ATR,
            "wave2_retrace": [W2_RET_MIN, W2_RET_MAX], "wave2_max_duration_ratio": W2_MAX_DUR_RATIO,
            "entry": "Wave1 extreme breakout only after Wave2 pivot confirmation",
            "sl_buffer_atr": SL_BUFFER_ATR, "entry_valid_signal_bars": ENTRY_VALID_BARS,
            "max_hold_signal_bars": MAX_HOLD_BARS, "tp1_extension": TP1_EXT, "tp2_extension": TP2_EXT,
            "tp1_fraction": TP1_FRAC, "after_tp1": "breakeven", "intrabar": "15m stop-first conservative",
        },
        "costs": {"fee_bps": FEE_BPS, "slippage_bps": SLIP_BPS, "per_fill_total_bps": COST_BPS},
        "summary": metrics(alltr), "timeframes": grouped_metrics(alltr, "timeframe"),
        "directions": grouped_metrics(alltr, "direction"), "symbols": grouped_metrics(alltr, "symbol"),
        "retracement_buckets": grouped_metrics(alltr, "retracement_bucket"),
        "years": {k: metrics(v) for k, v in sorted(years.items())}, "symbol_timeframes": cells, "trades": alltr,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("FINAL", json.dumps({k: v for k, v in out.items() if k != "trades"}, indent=2), flush=True)


if __name__ == "__main__":
    main()
