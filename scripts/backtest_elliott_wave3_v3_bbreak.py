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
TIMEFRAMES = (60, 240)

PIVOT_REV_ATR = 1.50
SL_BUFFER_ATR = 0.15
ENTRY_VALID_BARS = 12
MAX_HOLD_BARS = 48
TP1_EXT, TP2_EXT = 1.000, 1.618
TP1_FRAC = 0.50

core.PIVOT_REV_ATR = PIVOT_REV_ATR
v1.PIVOT_REV_ATR = PIVOT_REV_ATR


def make_v3_signal(d, win):
    base = v1.pattern_53(d, win)
    if base is None:
        return None

    side = base["side"]
    sgn = 1.0 if side == "LONG" else -1.0
    b_price = win[7]["price"]
    c_price = win[8]["price"]
    ki = win[8]["known"]
    atr = d[ki]["atr14"]
    if atr is None or atr <= 0:
        return None

    # v3: enter on B-wave extreme breakout after C confirmation.
    entry = b_price
    sl = c_price - sgn * SL_BUFFER_ATR * atr

    # Keep the same macro-Wave-1 extension targets as v1 so only entry timing changes.
    impulse = base["impulse_atr"] * atr
    tp1 = c_price + sgn * TP1_EXT * impulse
    tp2 = c_price + sgn * TP2_EXT * impulse
    risk = sgn * (entry - sl)

    if risk <= 0:
        return None
    if not (sgn * (tp1 - entry) > 0 and sgn * (tp2 - tp1) > 0):
        return None

    sig = dict(base)
    sig.update({
        "known_i": ki,
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "risk": risk,
        "risk_atr": risk / atr,
        "b_price": b_price,
        "c_price": c_price,
        "entry_vs_wave1_terminal_r": (
            abs(base["entry"] - entry) / base["risk"] if base["risk"] > 0 else None
        ),
    })
    return sig


def simulate(sym, b15, tf):
    d = core.enrich_atr(core.aggregate(b15, tf))
    ps = core.zigzag(d)
    t15 = [x["t"] for x in b15]
    lo = int(core.EVAL_START.timestamp() * 1000)
    hi = int(core.EVAL_END.timestamp() * 1000)
    sig_ms = tf * 60_000

    by_known = defaultdict(list)
    for k in range(8, len(ps)):
        sig = make_v3_signal(d, ps[k - 8 : k + 1])
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
            rem = 0.0; exit_t = b["ct"]; reason = "TIME"

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
            "abc_c_to_a", "impulse_bars", "correction_bars", "w1_len", "w3_len",
            "w5_len", "b_price", "c_price", "entry_vs_wave1_terminal_r"
        ):
            rec[k] = sig.get(k)

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


def run_group(group, symbols):
    alltr = []
    cells = {}
    for sym in symbols:
        print("LOAD", group, sym, flush=True)
        b15 = core.load_15m(sym)
        for tf in TIMEFRAMES:
            ts, st, npiv = simulate(sym, b15, tf)
            key = f"{sym}_{tf // 60}H"
            cells[key] = {"metrics": core.metrics(ts), "stats": st, "pivots": npiv}
            alltr += ts
            print("RESULT", group, key, json.dumps(cells[key]), flush=True)

    years = defaultdict(list)
    for t in alltr:
        years[str(datetime.fromtimestamp(t["entry_t"] / 1000, UTC).year)].append(t)

    out = {
        "strategy": "Elliott Wave 3 v3 B-wave breakout frozen",
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

    p = ROOT / f"data/validation/elliott_wave3_v3_bbreak_{group.lower()}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def main():
    results = {}
    for group, symbols in GROUPS.items():
        results[group] = run_group(group, symbols)

    alltr = []
    for v in results.values():
        alltr += v["trades"]

    combined = {
        "strategy": "Elliott Wave 3 v3 B-wave breakout frozen",
        "purpose": "Predeclared DEV + two unseen-symbol holdouts with identical rules; only entry timing differs from v1.",
        "rules": {
            "macro_structure": "exact v1 frozen 5-wave impulse + ABC zigzag",
            "signal_timeframes": ["1H", "4H"],
            "pivot_reversal_atr": PIVOT_REV_ATR,
            "entry": "B-wave extreme breakout after C pivot confirmation",
            "sl": "C extreme +/- 0.15 ATR",
            "tp1": "C +/- 1.0 x macro Wave 1 impulse length",
            "tp2": "C +/- 1.618 x macro Wave 1 impulse length",
            "tp1_fraction": TP1_FRAC,
            "after_tp1": "breakeven",
            "entry_valid_signal_bars": ENTRY_VALID_BARS,
            "max_hold_signal_bars": MAX_HOLD_BARS,
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

    out = ROOT / "data/validation/elliott_wave3_v3_bbreak_all.json"
    out.write_text(json.dumps(combined, indent=2), encoding="utf-8")

    print("FINAL", json.dumps({
        "DEV": results["DEV"]["summary"],
        "OOS1": results["OOS1"]["summary"],
        "OOS2": results["OOS2"]["summary"],
        "ALL": combined["combined_summary"],
    }, indent=2), flush=True)


if __name__ == "__main__":
    main()
