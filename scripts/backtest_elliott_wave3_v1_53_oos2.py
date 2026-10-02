import json
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import backtest_elliott_wave3_v0_crypto as core

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/validation/elliott_wave3_v1_53_oos2.json"
UTC = timezone.utc

SYMBOLS = ("LTCUSDT", "BCHUSDT", "ETCUSDT", "DOTUSDT")
TIMEFRAMES = (60, 240)

PIVOT_REV_ATR = 1.50
W2_RET_MIN, W2_RET_MAX = 0.382, 0.786
ABC_B_RET_MIN, ABC_B_RET_MAX = 0.236, 0.886
ABC_C_A_MIN, ABC_C_A_MAX = 0.618, 1.618
CORR_MAX_DUR_RATIO = 2.50
SL_BUFFER_ATR = 0.15
ENTRY_VALID_BARS = 12
MAX_HOLD_BARS = 48
TP1_EXT, TP2_EXT = 1.000, 1.618
TP1_FRAC = 0.50

# Preserve the same execution/cost model as v0.
core.PIVOT_REV_ATR = PIVOT_REV_ATR


def pattern_53(d, ps):
    if len(ps) != 9:
        return None
    types = "".join(p["type"] for p in ps)
    if types == "LHLHLHLHL":
        side, sgn = "LONG", 1.0
    elif types == "HLHLHLHLH":
        side, sgn = "SHORT", -1.0
    else:
        return None

    # Transform SHORT by multiplying prices by -1 so the same LONG inequalities apply.
    u = [sgn * p["price"] for p in ps]

    # Larger Wave 1 = five-wave impulse: 0-1-2-3-4-5.
    w1 = u[1] - u[0]
    w3 = u[3] - u[2]
    w5 = u[5] - u[4]
    if min(w1, w3, w5) <= 0:
        return None

    # Elliott hard rules for a standard impulse (diagonals/truncations excluded in v1).
    if not (u[2] > u[0]):          # Wave 2 cannot retrace beyond Wave 1 origin.
        return None
    if not (u[3] > u[1]):          # Wave 3 must make a new extreme.
        return None
    if not (u[4] > u[1]):          # Wave 4 may not overlap Wave 1 territory.
        return None
    if not (u[5] > u[3]):          # Truncated fifth excluded.
        return None
    if w3 + 1e-12 < min(w1, w5):   # Wave 3 may never be the shortest motive wave.
        return None

    impulse = u[5] - u[0]
    if impulse <= 0:
        return None

    # Larger Wave 2 = A-B-C zigzag: 5-A(6)-B(7)-C(8).
    a_len = u[5] - u[6]
    b_len = u[7] - u[6]
    c_len = u[7] - u[8]
    if min(a_len, b_len, c_len) <= 0:
        return None
    if not (u[7] < u[5]):          # B does not exceed Wave 1 termination in v1.
        return None
    if not (u[8] < u[6]):          # C extends beyond A (simple zigzag only).
        return None
    if not (u[8] > u[0]):          # Larger Wave 2 cannot break Larger Wave 1 origin.
        return None

    b_ret = b_len / a_len
    c_a = c_len / a_len
    if not (ABC_B_RET_MIN <= b_ret <= ABC_B_RET_MAX):
        return None
    if not (ABC_C_A_MIN <= c_a <= ABC_C_A_MAX):
        return None

    retr = (u[5] - u[8]) / impulse
    if not (W2_RET_MIN <= retr <= W2_RET_MAX):
        return None

    impulse_bars = ps[5]["idx"] - ps[0]["idx"]
    corr_bars = ps[8]["idx"] - ps[5]["idx"]
    if impulse_bars <= 0 or corr_bars <= 0 or corr_bars > CORR_MAX_DUR_RATIO * impulse_bars:
        return None

    ki = ps[8]["known"]
    if ki >= len(d):
        return None
    atr = d[ki]["atr14"]
    if atr is None or atr <= 0:
        return None

    entry = ps[5]["price"]
    c_price = ps[8]["price"]
    sl = c_price - sgn * SL_BUFFER_ATR * atr
    tp1 = c_price + sgn * TP1_EXT * impulse
    tp2 = c_price + sgn * TP2_EXT * impulse
    risk = sgn * (entry - sl)
    if risk <= 0:
        return None
    if not (sgn * (tp1 - entry) > 0 and sgn * (tp2 - tp1) > 0):
        return None

    return {
        "side": side,
        "known_i": ki,
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "risk": risk,
        "risk_atr": risk / atr,
        "impulse_atr": impulse / atr,
        "wave2_retracement": retr,
        "abc_b_retracement": b_ret,
        "abc_c_to_a": c_a,
        "impulse_bars": impulse_bars,
        "correction_bars": corr_bars,
        "w1_len": w1,
        "w3_len": w3,
        "w5_len": w5,
    }


def simulate(sym, b15, tf, direction_filter=None):
    d = core.enrich_atr(core.aggregate(b15, tf))
    ps = core.zigzag(d)
    t15 = [x["t"] for x in b15]
    lo = int(core.EVAL_START.timestamp() * 1000)
    hi = int(core.EVAL_END.timestamp() * 1000)
    sig_ms = tf * 60_000

    by_known = defaultdict(list)
    for k in range(8, len(ps)):
        sig = pattern_53(d, ps[k - 8 : k + 1])
        if sig and (direction_filter is None or sig["side"] == direction_filter):
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
        valid_until = activation + ENTRY_VALID_BARS * sig_ms
        fill_i = None
        fill = None
        cancelled = False

        for j in range(start, len(b15)):
            b = b15[j]
            if b["t"] >= hi or b["t"] >= valid_until:
                break
            if side == "LONG":
                if b["o"] >= entry:
                    fill_i, fill = j, b["o"]
                    break
                if b["l"] <= sl:
                    cancelled = True
                    break
                if b["h"] >= entry:
                    fill_i, fill = j, entry
                    break
            else:
                if b["o"] <= entry:
                    fill_i, fill = j, b["o"]
                    break
                if b["h"] >= sl:
                    cancelled = True
                    break
                if b["l"] <= entry:
                    fill_i, fill = j, entry
                    break

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
        hold_until = b15[fill_i]["t"] + MAX_HOLD_BARS * sig_ms
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
            rem = 0.0
            exit_t = b["ct"]
            reason = "TIME"

        rec = {
            "symbol": sym,
            "timeframe": f"{tf // 60}H",
            "direction": side,
            "signal_t": activation,
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
        for k in (
            "risk_atr", "impulse_atr", "wave2_retracement", "abc_b_retracement",
            "abc_c_to_a", "impulse_bars", "correction_bars", "w1_len", "w3_len", "w5_len"
        ):
            rec[k] = sig[k]
        trades.append(rec)
        busy_until = exit_t

    st = dict(st)
    st["fill_rate"] = st.get("filled", 0) / st.get("patterns", 1) if st.get("patterns", 0) else None
    return trades, st, len(ps)


def group_metrics(trades, key):
    g = defaultdict(list)
    for t in trades:
        g[t[key]].append(t)
    return {k: core.metrics(v) for k, v in sorted(g.items())}


def main():
    alltr = []
    cells = {}

    for sym in SYMBOLS:
        b15 = core.load_15m(sym)
        for tf in TIMEFRAMES:
            ts, st, npiv = simulate(sym, b15, tf)
            name = f"{sym}_{tf // 60}H"
            cells[name] = {"metrics": core.metrics(ts), "stats": st, "pivots": npiv}
            alltr += ts
            print("RESULT", name, json.dumps(cells[name]), flush=True)

    by_year = defaultdict(list)
    for t in alltr:
        y = str(datetime.fromtimestamp(t["entry_t"] / 1000, UTC).year)
        by_year[y].append(t)

    out = {
        "strategy": "Elliott Wave 3 v1 5-3 OOS2 unseen symbols",
        "purpose": "Second unseen-symbol holdout using the exact frozen v1 rules; no tuning.",
        "asset_class": "Binance USDT-M perpetual",
        "period": {
            "fetch_start": core.FETCH_START.isoformat(),
            "eval_start": core.EVAL_START.isoformat(),
            "eval_end_exclusive": core.EVAL_END.isoformat(),
        },
        "rules": {
            "pivot_reversal_atr": PIVOT_REV_ATR,
            "impulse": "5-wave standard impulse; W2 origin intact, W3 new extreme and not shortest, W4 no W1 overlap, W5 new extreme",
            "correction": "ABC zigzag; B below/above impulse termination, C extends beyond A",
            "larger_wave2_retracement": [W2_RET_MIN, W2_RET_MAX],
            "abc_b_retracement": [ABC_B_RET_MIN, ABC_B_RET_MAX],
            "abc_c_to_a": [ABC_C_A_MIN, ABC_C_A_MAX],
            "correction_max_duration_ratio": CORR_MAX_DUR_RATIO,
            "entry": "breakout of larger Wave 1 termination after C pivot confirmation",
            "sl_buffer_atr": SL_BUFFER_ATR,
            "entry_valid_signal_bars": ENTRY_VALID_BARS,
            "max_hold_signal_bars": MAX_HOLD_BARS,
            "tp1_extension": TP1_EXT,
            "tp2_extension": TP2_EXT,
            "tp1_fraction": TP1_FRAC,
            "after_tp1": "breakeven",
            "execution": "15m, stop-first conservative intrabar convention",
        },
        "costs": {
            "fee_bps": core.FEE_BPS,
            "slippage_bps": core.SLIP_BPS,
            "per_fill_total_bps": core.COST_BPS,
        },
        "summary": core.metrics(alltr),
        "timeframes": group_metrics(alltr, "timeframe"),
        "directions": group_metrics(alltr, "direction"),
        "symbols": group_metrics(alltr, "symbol"),
        "years": {k: core.metrics(v) for k, v in sorted(by_year.items())},
        "symbol_timeframes": cells,
        "trades": alltr,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("FINAL", json.dumps({k: v for k, v in out.items() if k != "trades"}, indent=2), flush=True)


if __name__ == "__main__":
    main()
