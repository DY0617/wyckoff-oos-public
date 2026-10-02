import json
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import backtest_elliott_wave3_v0_crypto as core
import backtest_elliott_wave3_v1_53_crypto as v1

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc

GROUPS = {
    "DEV": ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"),
    "OOS1": ("XRPUSDT", "ADAUSDT", "DOGEUSDT", "LINKUSDT"),
    "OOS2": ("LTCUSDT", "BCHUSDT", "ETCUSDT", "DOTUSDT"),
}
STRUCTURE_TFS = (60, 240)
LOWER_TF = {60: 15, 240: 60}

PIVOT_REV_ATR = 1.50
SUB_W1_MIN_ATR = 1.00
SUB_W2_RET_MIN, SUB_W2_RET_MAX = 0.236, 0.786
SUB_W2_MAX_DUR_RATIO = 2.50
SUB_SETUP_MAX_BARS = 48
SL_BUFFER_ATR = 0.15
ENTRY_VALID_BARS = 12
MAX_HOLD_BARS = 48
TP1_EXT, TP2_EXT = 1.000, 1.618
TP1_FRAC = 0.50

core.PIVOT_REV_ATR = PIVOT_REV_ATR
v1.PIVOT_REV_ATR = PIVOT_REV_ATR


def build_tf(b15, minutes):
    if minutes == 15:
        return core.enrich_atr([dict(x) for x in b15])
    return core.enrich_atr(core.aggregate(b15, minutes))


def macro_patterns(d):
    ps = core.zigzag(d)
    out = []
    for k in range(8, len(ps)):
        win = ps[k - 8 : k + 1]
        sig = v1.pattern_53(d, win)
        if sig is None:
            continue
        c = win[8]
        out.append({
            "side": sig["side"],
            "known_i": sig["known_i"],
            "activation": d[sig["known_i"]]["ct"],
            "c_actual_t": d[c["idx"]]["t"],
            "c_price": c["price"],
            "macro": sig,
        })
    return out, ps


def macro_invalidated(lower, start_i, end_i, side, c_price):
    xs = lower[start_i : end_i + 1]
    if not xs:
        return False
    if side == "LONG":
        return min(x["l"] for x in xs) < c_price
    return max(x["h"] for x in xs) > c_price


def sub_pattern(lower, p0, p1, p2, side):
    types = p0["type"] + p1["type"] + p2["type"]
    if (side == "LONG" and types != "LHL") or (side == "SHORT" and types != "HLH"):
        return None

    sgn = 1.0 if side == "LONG" else -1.0
    u0, u1, u2 = sgn * p0["price"], sgn * p1["price"], sgn * p2["price"]
    w1 = u1 - u0
    if w1 <= 0:
        return None

    base_atr = max(lower[p0["idx"]]["atr14"], lower[p1["idx"]]["atr14"])
    if base_atr <= 0 or w1 < SUB_W1_MIN_ATR * base_atr:
        return None
    if not (u2 > u0):
        return None

    retr = (u1 - u2) / w1
    if not (SUB_W2_RET_MIN <= retr <= SUB_W2_RET_MAX):
        return None

    d1 = p1["idx"] - p0["idx"]
    d2 = p2["idx"] - p1["idx"]
    if d1 <= 0 or d2 <= 0 or d2 > SUB_W2_MAX_DUR_RATIO * d1:
        return None

    ki = p2["known"]
    atr = lower[ki]["atr14"]
    if atr is None or atr <= 0:
        return None

    entry = p1["price"]
    sl = p2["price"] - sgn * SL_BUFFER_ATR * atr
    tp1 = p2["price"] + sgn * TP1_EXT * w1
    tp2 = p2["price"] + sgn * TP2_EXT * w1
    risk = sgn * (entry - sl)

    if risk <= 0:
        return None
    if not (sgn * (tp1 - entry) > 0 and sgn * (tp2 - tp1) > 0):
        return None

    return {
        "side": side,
        "known_i": ki,
        "activation": lower[ki]["ct"],
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "risk": risk,
        "risk_atr": risk / atr,
        "sub_w1_atr": w1 / base_atr,
        "sub_w2_retracement": retr,
        "sub_w1_bars": d1,
        "sub_w2_bars": d2,
    }


def first_nested_setup(lower, lower_ps, macro):
    side = macro["side"]
    c_t = macro["c_actual_t"]
    activation = macro["activation"]
    lower_ms = (lower[0]["ct"] - lower[0]["t"]) if lower else 0
    deadline = activation + SUB_SETUP_MAX_BARS * lower_ms

    start_bar = bisect_left([x["t"] for x in lower], c_t)

    for k in range(2, len(lower_ps)):
        p0, p1, p2 = lower_ps[k - 2], lower_ps[k - 1], lower_ps[k]
        if lower[p0["idx"]]["t"] < c_t:
            continue
        known_t = lower[p2["known"]]["ct"]
        if known_t < activation:
            continue
        if known_t >= deadline:
            break

        sig = sub_pattern(lower, p0, p1, p2, side)
        if sig is None:
            continue

        if macro_invalidated(lower, start_bar, p2["known"], side, macro["c_price"]):
            return None, "macro_invalidated"

        sig["macro_activation"] = activation
        sig["macro_c_price"] = macro["c_price"]
        sig["macro_wave2_retracement"] = macro["macro"]["wave2_retracement"]
        sig["macro_abc_b_retracement"] = macro["macro"]["abc_b_retracement"]
        sig["macro_abc_c_to_a"] = macro["macro"]["abc_c_to_a"]
        sig["macro_impulse_atr"] = macro["macro"]["impulse_atr"]
        return sig, None

    return None, "no_sub_setup"


def execute_trade(sym, b15, sig, struct_tf, lower_tf, hi):
    t15 = [x["t"] for x in b15]
    side = sig["side"]
    entry, sl, tp1, tp2, risk = sig["entry"], sig["sl"], sig["tp1"], sig["tp2"], sig["risk"]
    lower_ms = lower_tf * 60_000
    start = bisect_left(t15, sig["activation"])
    valid_until = sig["activation"] + ENTRY_VALID_BARS * lower_ms

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
        return None, ("cancelled_before_entry" if cancelled else "entry_expired"), valid_until

    pnl = -core.cost(fill)
    rem = 1.0
    stop = sl
    hit1 = hit2 = False
    exit_t = b15[fill_i]["ct"]
    reason = "TIME"
    hold_until = b15[fill_i]["t"] + MAX_HOLD_BARS * lower_ms
    last_i = fill_i

    for j in range(fill_i, len(b15)):
        b = b15[j]
        if b["t"] >= hi or b["t"] >= hold_until:
            break
        last_i = j

        if side == "LONG":
            if b["o"] <= stop:
                pnl += rem * (b["o"] - fill) - core.cost(b["o"], rem)
                rem = 0.0; exit_t = b["ct"]; reason = "GAP_STOP"; break
            if b["l"] <= stop:
                pnl += rem * (stop - fill) - core.cost(stop, rem)
                rem = 0.0; exit_t = b["ct"]; reason = "STOP"; break
            if not hit1:
                px = b["o"] if b["o"] >= tp1 else (tp1 if b["h"] >= tp1 else None)
                if px is not None:
                    f = min(TP1_FRAC, rem)
                    pnl += f * (px - fill) - core.cost(px, f)
                    rem -= f; hit1 = True; stop = max(stop, fill)
                    if rem > 0 and b["l"] <= stop:
                        pnl += rem * (stop - fill) - core.cost(stop, rem)
                        rem = 0.0; exit_t = b["ct"]; reason = "BE_AFTER_TP1"; break
            if rem > 0 and hit1 and (b["o"] >= tp2 or b["h"] >= tp2):
                px = b["o"] if b["o"] >= tp2 else tp2
                pnl += rem * (px - fill) - core.cost(px, rem)
                rem = 0.0; hit2 = True; exit_t = b["ct"]; reason = "TP2"; break
        else:
            if b["o"] >= stop:
                pnl += rem * (fill - b["o"]) - core.cost(b["o"], rem)
                rem = 0.0; exit_t = b["ct"]; reason = "GAP_STOP"; break
            if b["h"] >= stop:
                pnl += rem * (fill - stop) - core.cost(stop, rem)
                rem = 0.0; exit_t = b["ct"]; reason = "STOP"; break
            if not hit1:
                px = b["o"] if b["o"] <= tp1 else (tp1 if b["l"] <= tp1 else None)
                if px is not None:
                    f = min(TP1_FRAC, rem)
                    pnl += f * (fill - px) - core.cost(px, f)
                    rem -= f; hit1 = True; stop = min(stop, fill)
                    if rem > 0 and b["h"] >= stop:
                        pnl += rem * (fill - stop) - core.cost(stop, rem)
                        rem = 0.0; exit_t = b["ct"]; reason = "BE_AFTER_TP1"; break
            if rem > 0 and hit1 and (b["o"] <= tp2 or b["l"] <= tp2):
                px = b["o"] if b["o"] <= tp2 else tp2
                pnl += rem * (fill - px) - core.cost(px, rem)
                rem = 0.0; hit2 = True; exit_t = b["ct"]; reason = "TP2"; break

    if rem > 0:
        b = b15[last_i]
        px = b["c"]
        pnl += rem * ((px - fill) if side == "LONG" else (fill - px)) - core.cost(px, rem)
        rem = 0.0; exit_t = b["ct"]; reason = "TIME"

    rec = {
        "symbol": sym,
        "timeframe": f"{struct_tf // 60}H",
        "structure_tf": f"{struct_tf // 60}H",
        "lower_tf": "15m" if lower_tf == 15 else f"{lower_tf // 60}H",
        "direction": side,
        "signal_t": sig["activation"],
        "entry_t": b15[fill_i]["t"],
        "exit_t": exit_t,
        "entry": entry,
        "fill": fill,
        "initial_sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "risk": risk,
        "r": pnl / risk,
        "reason": reason,
        "tp1_hit": hit1,
        "tp2_hit": hit2,
        "hold_hours": max(0.0, (exit_t - b15[fill_i]["t"]) / 3_600_000),
    }
    for k, v in sig.items():
        if k not in rec and isinstance(v, (int, float, str, bool)):
            rec[k] = v
    return rec, None, exit_t


def simulate(sym, b15, struct_tf):
    lower_tf = LOWER_TF[struct_tf]
    high = build_tf(b15, struct_tf)
    lower = build_tf(b15, lower_tf)
    lower_ps = core.zigzag(lower)
    macros, high_ps = macro_patterns(high)

    lo = int(core.EVAL_START.timestamp() * 1000)
    hi = int(core.EVAL_END.timestamp() * 1000)
    signals = []
    st = defaultdict(int)

    for m in macros:
        if not (lo <= m["activation"] < hi):
            continue
        st["macro_patterns"] += 1
        s, why = first_nested_setup(lower, lower_ps, m)
        if s is None:
            st[why] += 1
            continue
        signals.append(s)
        st["nested_setups"] += 1

    signals.sort(key=lambda z: z["activation"])
    trades = []
    busy_until = -1
    for s in signals:
        if s["activation"] < busy_until:
            st["signal_while_busy"] += 1
            continue
        rec, why, until = execute_trade(sym, b15, s, struct_tf, lower_tf, hi)
        if rec is None:
            st[why] += 1
            busy_until = until
            continue
        st["filled"] += 1
        trades.append(rec)
        busy_until = until

    st = dict(st)
    st["setup_rate"] = st.get("nested_setups", 0) / st.get("macro_patterns", 1) if st.get("macro_patterns", 0) else None
    st["fill_rate"] = st.get("filled", 0) / st.get("nested_setups", 1) if st.get("nested_setups", 0) else None
    return trades, st, len(high_ps), len(lower_ps)


def group_metrics(trades, key):
    g = defaultdict(list)
    for t in trades:
        g[t[key]].append(t)
    return {k: core.metrics(v) for k, v in sorted(g.items())}


def run_group(group, symbols):
    alltr = []
    cells = {}
    for sym in symbols:
        print("LOAD", group, sym, flush=True)
        b15 = core.load_15m(sym)
        for tf in STRUCTURE_TFS:
            ts, st, nh, nl = simulate(sym, b15, tf)
            key = f"{sym}_{tf // 60}H"
            cells[key] = {"metrics": core.metrics(ts), "stats": st, "high_pivots": nh, "lower_pivots": nl}
            alltr += ts
            print("RESULT", group, key, json.dumps(cells[key]), flush=True)

    years = defaultdict(list)
    for t in alltr:
        years[str(datetime.fromtimestamp(t["entry_t"] / 1000, UTC).year)].append(t)

    out = {
        "strategy": "Elliott Wave 3 v2 nested 1-2 entry frozen",
        "group": group,
        "symbols": list(symbols),
        "summary": core.metrics(alltr),
        "timeframes": group_metrics(alltr, "timeframe"),
        "directions": group_metrics(alltr, "direction"),
        "symbols_metrics": group_metrics(alltr, "symbol"),
        "years": {k: core.metrics(v) for k, v in sorted(years.items())},
        "symbol_timeframes": cells,
        "trades": alltr,
    }
    path = ROOT / f"data/validation/elliott_wave3_v2_nested_{group.lower()}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def main():
    results = {}
    for group, symbols in GROUPS.items():
        results[group] = run_group(group, symbols)

    alltr = []
    for v in results.values():
        alltr += v["trades"]

    combined = {
        "strategy": "Elliott Wave 3 v2 nested 1-2 entry frozen",
        "purpose": "Predeclared development + two unseen-symbol holdouts using identical rules; no tuning between groups.",
        "rules": {
            "macro_structure": "v1 frozen 5-wave impulse + ABC zigzag",
            "structure_timeframes": ["1H", "4H"],
            "lower_timeframes": {"1H": "15m", "4H": "1H"},
            "pivot_reversal_atr": PIVOT_REV_ATR,
            "sub_wave1_min_atr": SUB_W1_MIN_ATR,
            "sub_wave2_retracement": [SUB_W2_RET_MIN, SUB_W2_RET_MAX],
            "sub_wave2_max_duration_ratio": SUB_W2_MAX_DUR_RATIO,
            "sub_setup_max_bars": SUB_SETUP_MAX_BARS,
            "macro_invalidation": "C extreme break before nested setup confirmation",
            "entry": "nested Wave 1 extreme breakout after nested Wave 2 confirmation",
            "sl": "nested Wave 2 extreme +/- 0.15 ATR",
            "tp1": "nested Wave 2 +/- 1.0 x nested Wave 1",
            "tp2": "nested Wave 2 +/- 1.618 x nested Wave 1",
            "tp1_fraction": TP1_FRAC,
            "after_tp1": "breakeven",
            "entry_valid_lower_bars": ENTRY_VALID_BARS,
            "max_hold_lower_bars": MAX_HOLD_BARS,
            "execution": "15m, stop-first conservative intrabar convention",
        },
        "costs": {
            "fee_bps": core.FEE_BPS,
            "slippage_bps": core.SLIP_BPS,
            "per_fill_total_bps": core.COST_BPS,
        },
        "groups": {k: {x: y for x, y in v.items() if x != "trades"} for k, v in results.items()},
        "combined_summary": core.metrics(alltr),
        "combined_timeframes": group_metrics(alltr, "timeframe"),
        "combined_directions": group_metrics(alltr, "direction"),
        "combined_symbols": group_metrics(alltr, "symbol"),
    }
    out = ROOT / "data/validation/elliott_wave3_v2_nested_all.json"
    out.write_text(json.dumps(combined, indent=2), encoding="utf-8")
    print("FINAL", json.dumps({
        "DEV": results["DEV"]["summary"],
        "OOS1": results["OOS1"]["summary"],
        "OOS2": results["OOS2"]["summary"],
        "ALL": combined["combined_summary"],
    }, indent=2), flush=True)


if __name__ == "__main__":
    main()
