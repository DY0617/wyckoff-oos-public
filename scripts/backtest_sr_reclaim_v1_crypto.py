import json
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import backtest_elliott_wave3_v0_crypto as core

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/validation/sr_reclaim_v1_crypto_5y.json"
UTC = timezone.utc

SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT")
SIGNAL_TF_MIN = 240
ZONE_TFS = (240, 1440)

ZONE_MERGE_ATR = 0.45
ZONE_HALF_ATR = 0.30
ZONE_MAX_HALF_ATR = 0.65
ZONE_MIN_TOUCHES = 2
ZONE_MAX_AGE_DAYS = 365
MIN_TOUCH_SEP_HOURS = 12

CLV_LONG_MIN = 0.65
CLV_SHORT_MAX = 0.35
BOS_LOOKBACK = 2
EMA_FAST = 20
EMA_SLOW = 50
EMA_SLOPE_BARS = 6

SL_BUFFER_ATR = 0.15
MIN_RISK_ATR = 0.35
MAX_RISK_ATR = 2.00
MIN_TARGET_R = 2.00
TP1_R = 1.00
TP1_FRAC = 0.50
MAX_ENTRY_GAP_ATR = 0.25
MAX_HOLD_SIGNAL_BARS = 24
ZONE_SIGNAL_COOLDOWN_BARS = 6


def ema(xs, n):
    out = []
    a = 2.0 / (n + 1.0)
    cur = None
    for x in xs:
        cur = x if cur is None else a * x + (1.0 - a) * cur
        out.append(cur)
    return out


def zone_events(b15):
    ev = []
    for tf in ZONE_TFS:
        d = core.enrich_atr(core.aggregate(b15, tf))
        ps = core.zigzag(d)
        for p in ps:
            if p["known"] >= len(d):
                continue
            b = d[p["idx"]]
            atr = b.get("atr14") or d[p["known"]].get("atr14")
            if not atr or atr <= 0:
                continue
            level = min(b["o"], b["c"]) if p["type"] == "L" else max(b["o"], b["c"])
            ev.append({
                "level": level,
                "atr": atr,
                "pivot_type": p["type"],
                "source_tf": tf,
                "event_t": b["ct"],
                "known_t": d[p["known"]]["ct"],
            })
    ev.sort(key=lambda x: (x["known_t"], x["event_t"], x["source_tf"]))
    return ev


def _recalc_zone(z):
    pts = z["points"]
    z["center"] = sum(p["level"] for p in pts) / len(pts)
    z["avg_atr"] = sum(p["atr"] for p in pts) / len(pts)
    raw = max([ZONE_HALF_ATR * z["avg_atr"]] + [abs(p["level"] - z["center"]) for p in pts])
    half = min(raw, ZONE_MAX_HALF_ATR * z["avg_atr"])
    z["lo"] = z["center"] - half
    z["hi"] = z["center"] + half
    z["touches"] = len(pts)
    z["daily_touches"] = sum(p["source_tf"] == 1440 for p in pts)
    z["last_event_t"] = max(p["event_t"] for p in pts)
    z["last_known_t"] = max(p["known_t"] for p in pts)


def add_event(zones, e, next_id):
    best = None
    best_dist = None
    for z in zones:
        scale = max(e["atr"], z["avg_atr"])
        dist = abs(e["level"] - z["center"])
        if dist <= ZONE_MERGE_ATR * scale and (best_dist is None or dist < best_dist):
            best = z
            best_dist = dist
    if best is None:
        z = {"id": next_id, "points": [e.copy()]}
        _recalc_zone(z)
        zones.append(z)
        return next_id + 1

    sep_ms = MIN_TOUCH_SEP_HOURS * 3_600_000
    if all(abs(e["event_t"] - p["event_t"]) >= sep_ms for p in best["points"]):
        best["points"].append(e.copy())
        _recalc_zone(best)
    return next_id


def snapshot_active(zones, t):
    max_age_ms = ZONE_MAX_AGE_DAYS * 86_400_000
    out = []
    for z in zones:
        if z["touches"] < ZONE_MIN_TOUCHES:
            continue
        if t - z["last_event_t"] > max_age_ms:
            continue
        out.append({
            "id": z["id"],
            "center": z["center"],
            "lo": z["lo"],
            "hi": z["hi"],
            "touches": z["touches"],
            "daily_touches": z["daily_touches"],
            "last_event_t": z["last_event_t"],
        })
    return out


def find_signals(b15):
    d = core.enrich_atr(core.aggregate(b15, SIGNAL_TF_MIN))
    closes = [x["c"] for x in d]
    ef = ema(closes, EMA_FAST)
    es = ema(closes, EMA_SLOW)
    events = zone_events(b15)
    zones = []
    next_zone_id = 1
    eidx = 0
    signals = []
    stats = defaultdict(int)
    last_signal_i = {}

    warm = max(EMA_SLOW + EMA_SLOPE_BARS, BOS_LOOKBACK + 2)
    for i in range(warm, len(d)):
        x = d[i]
        prev = d[i - 1]

        while eidx < len(events) and events[eidx]["known_t"] <= x["t"]:
            next_zone_id = add_event(zones, events[eidx], next_zone_id)
            eidx += 1

        active = snapshot_active(zones, x["t"])
        if not active:
            continue

        atr = x["atr14"]
        if not atr or atr <= 0 or x["h"] <= x["l"]:
            continue
        clv = (x["c"] - x["l"]) / (x["h"] - x["l"])
        prior_hi = max(d[j]["h"] for j in range(i - BOS_LOOKBACK, i))
        prior_lo = min(d[j]["l"] for j in range(i - BOS_LOOKBACK, i))

        long_z = [
            z for z in active
            if prev["c"] > z["hi"]
            and x["l"] <= z["hi"]
            and x["l"] <= z["center"]
            and x["c"] > z["hi"]
            and clv >= CLV_LONG_MIN
            and x["c"] > prior_hi
            and ef[i] >= es[i]
            and es[i] > es[i - EMA_SLOPE_BARS]
        ]
        short_z = [
            z for z in active
            if prev["c"] < z["lo"]
            and x["h"] >= z["lo"]
            and x["h"] >= z["center"]
            and x["c"] < z["lo"]
            and clv <= CLV_SHORT_MAX
            and x["c"] < prior_lo
            and ef[i] <= es[i]
            and es[i] < es[i - EMA_SLOPE_BARS]
        ]

        candidates = []
        if long_z:
            candidates.append(("LONG", max(long_z, key=lambda z: z["center"])))
        if short_z:
            candidates.append(("SHORT", min(short_z, key=lambda z: z["center"])))

        for side, z in candidates:
            if i - last_signal_i.get(z["id"], -10**9) < ZONE_SIGNAL_COOLDOWN_BARS:
                stats["zone_cooldown"] += 1
                continue

            entry_ref = x["c"]
            if side == "LONG":
                stop = min(x["l"], z["lo"]) - SL_BUFFER_ATR * atr
                target_candidates = [q for q in active if q["id"] != z["id"] and q["lo"] > entry_ref]
                if not target_candidates:
                    stats["no_opposite_zone"] += 1
                    continue
                tz = min(target_candidates, key=lambda q: q["lo"])
                tp2 = tz["lo"]
                risk_ref = entry_ref - stop
                room = tp2 - entry_ref
            else:
                stop = max(x["h"], z["hi"]) + SL_BUFFER_ATR * atr
                target_candidates = [q for q in active if q["id"] != z["id"] and q["hi"] < entry_ref]
                if not target_candidates:
                    stats["no_opposite_zone"] += 1
                    continue
                tz = max(target_candidates, key=lambda q: q["hi"])
                tp2 = tz["hi"]
                risk_ref = stop - entry_ref
                room = entry_ref - tp2

            if risk_ref <= 0:
                continue
            risk_atr = risk_ref / atr
            if not (MIN_RISK_ATR <= risk_atr <= MAX_RISK_ATR):
                stats["risk_filter"] += 1
                continue
            if room / risk_ref < MIN_TARGET_R:
                stats["target_rr_filter"] += 1
                continue

            signals.append({
                "side": side,
                "activation": x["ct"],
                "signal_i": i,
                "signal_close": entry_ref,
                "atr": atr,
                "stop": stop,
                "tp2": tp2,
                "zone_id": z["id"],
                "zone_center": z["center"],
                "zone_lo": z["lo"],
                "zone_hi": z["hi"],
                "zone_touches": z["touches"],
                "zone_daily_touches": z["daily_touches"],
                "target_zone_id": tz["id"],
                "target_zone_touches": tz["touches"],
                "signal_clv": clv,
                "risk_ref_atr": risk_atr,
            })
            last_signal_i[z["id"]] = i
            stats["signals"] += 1

    return d, signals, dict(stats)


def execute(sym, b15):
    d4, signals, st = find_signals(b15)
    t15 = [x["t"] for x in b15]
    lo = int(core.EVAL_START.timestamp() * 1000)
    hi = int(core.EVAL_END.timestamp() * 1000)
    trades = []
    busy_until = -1

    for s in signals:
        activation = s["activation"]
        if not (lo <= activation < hi):
            continue
        if activation < busy_until:
            st["signal_while_busy"] = st.get("signal_while_busy", 0) + 1
            continue

        j = bisect_left(t15, activation)
        if j >= len(b15) or b15[j]["t"] >= hi:
            continue

        fill = b15[j]["o"]
        gap_atr = abs(fill - s["signal_close"]) / s["atr"]
        if gap_atr > MAX_ENTRY_GAP_ATR:
            st["entry_gap_filter"] = st.get("entry_gap_filter", 0) + 1
            continue

        side = s["side"]
        stop = s["stop"]
        tp2 = s["tp2"]
        if side == "LONG":
            risk = fill - stop
            room = tp2 - fill
        else:
            risk = stop - fill
            room = fill - tp2

        if risk <= 0 or room <= 0 or room / risk < MIN_TARGET_R:
            st["post_gap_rr_filter"] = st.get("post_gap_rr_filter", 0) + 1
            continue

        tp1 = fill + risk if side == "LONG" else fill - risk
        st["filled"] = st.get("filled", 0) + 1

        pnl = -core.cost(fill)
        rem = 1.0
        cur_stop = stop
        hit1 = hit2 = False
        exit_t = b15[j]["ct"]
        reason = "TIME"
        hold_until = activation + MAX_HOLD_SIGNAL_BARS * SIGNAL_TF_MIN * 60_000
        last_i = j

        for k in range(j, len(b15)):
            b = b15[k]
            if b["t"] >= hi or b["t"] >= hold_until:
                break
            last_i = k

            if side == "LONG":
                if b["o"] <= cur_stop:
                    pnl += rem * (b["o"] - fill) - core.cost(b["o"], rem)
                    rem = 0.0; exit_t = b["ct"]; reason = "GAP_STOP"; break
                if b["l"] <= cur_stop:
                    pnl += rem * (cur_stop - fill) - core.cost(cur_stop, rem)
                    rem = 0.0; exit_t = b["ct"]; reason = "STOP"; break

                if not hit1 and (b["o"] >= tp1 or b["h"] >= tp1):
                    px = b["o"] if b["o"] >= tp1 else tp1
                    f = min(TP1_FRAC, rem)
                    pnl += f * (px - fill) - core.cost(px, f)
                    rem -= f
                    hit1 = True
                    cur_stop = max(cur_stop, fill)
                    if rem > 0 and b["l"] <= cur_stop:
                        pnl += rem * (cur_stop - fill) - core.cost(cur_stop, rem)
                        rem = 0.0; exit_t = b["ct"]; reason = "BE_AFTER_TP1"; break

                if rem > 0 and hit1 and (b["o"] >= tp2 or b["h"] >= tp2):
                    px = b["o"] if b["o"] >= tp2 else tp2
                    pnl += rem * (px - fill) - core.cost(px, rem)
                    rem = 0.0; hit2 = True; exit_t = b["ct"]; reason = "TP2"; break

            else:
                if b["o"] >= cur_stop:
                    pnl += rem * (fill - b["o"]) - core.cost(b["o"], rem)
                    rem = 0.0; exit_t = b["ct"]; reason = "GAP_STOP"; break
                if b["h"] >= cur_stop:
                    pnl += rem * (fill - cur_stop) - core.cost(cur_stop, rem)
                    rem = 0.0; exit_t = b["ct"]; reason = "STOP"; break

                if not hit1 and (b["o"] <= tp1 or b["l"] <= tp1):
                    px = b["o"] if b["o"] <= tp1 else tp1
                    f = min(TP1_FRAC, rem)
                    pnl += f * (fill - px) - core.cost(px, f)
                    rem -= f
                    hit1 = True
                    cur_stop = min(cur_stop, fill)
                    if rem > 0 and b["h"] >= cur_stop:
                        pnl += rem * (fill - cur_stop) - core.cost(cur_stop, rem)
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

        trades.append({
            "symbol": sym,
            "timeframe": "4H",
            "direction": side,
            "signal_t": activation,
            "entry_t": b15[j]["t"],
            "exit_t": exit_t,
            "signal_close": s["signal_close"],
            "fill": fill,
            "initial_sl": stop,
            "tp1": tp1,
            "tp2": tp2,
            "risk": risk,
            "r": pnl / risk,
            "reason": reason,
            "tp1_hit": hit1,
            "tp2_hit": hit2,
            "hold_hours": max(0.0, (exit_t - b15[j]["t"]) / 3_600_000),
            "entry_gap_atr": gap_atr,
            "zone_id": s["zone_id"],
            "zone_center": s["zone_center"],
            "zone_lo": s["zone_lo"],
            "zone_hi": s["zone_hi"],
            "zone_touches": s["zone_touches"],
            "zone_daily_touches": s["zone_daily_touches"],
            "target_zone_id": s["target_zone_id"],
            "target_zone_touches": s["target_zone_touches"],
            "signal_clv": s["signal_clv"],
            "risk_ref_atr": s["risk_ref_atr"],
            "target_r_at_fill": room / risk,
        })
        busy_until = exit_t

    st["fill_rate"] = st.get("filled", 0) / st.get("signals", 1) if st.get("signals", 0) else None
    return trades, st


def grouped_metrics(trades, key):
    g = defaultdict(list)
    for t in trades:
        g[t[key]].append(t)
    return {k: core.metrics(v) for k, v in sorted(g.items())}


def main():
    alltr = []
    cells = {}
    for sym in SYMBOLS:
        b15 = core.load_15m(sym)
        ts, st = execute(sym, b15)
        cells[sym] = {"metrics": core.metrics(ts), "stats": st}
        alltr += ts
        print("RESULT", sym, json.dumps(cells[sym]), flush=True)

    years = defaultdict(list)
    for t in alltr:
        years[str(datetime.fromtimestamp(t["entry_t"] / 1000, UTC).year)].append(t)

    out = {
        "strategy": "SR Reclaim v1 frozen",
        "asset_class": "Binance USDT-M perpetual",
        "period": {
            "fetch_start": core.FETCH_START.isoformat(),
            "eval_start": core.EVAL_START.isoformat(),
            "eval_end_exclusive": core.EVAL_END.isoformat(),
        },
        "rules": {
            "signal_timeframe": "4H",
            "execution_timeframe": "15m next-open market",
            "zone_timeframes": ["4H", "1D"],
            "zone_level": "pivot candle body edge (low pivot=min(open,close), high pivot=max(open,close))",
            "zone_merge_atr": ZONE_MERGE_ATR,
            "zone_half_atr": ZONE_HALF_ATR,
            "zone_max_half_atr": ZONE_MAX_HALF_ATR,
            "zone_min_touches": ZONE_MIN_TOUCHES,
            "zone_max_age_days": ZONE_MAX_AGE_DAYS,
            "min_touch_separation_hours": MIN_TOUCH_SEP_HOURS,
            "confirmation": {
                "reclaim": "previous close outside zone, wick penetrates at least zone center, current close reclaims zone",
                "clv_long_min": CLV_LONG_MIN,
                "clv_short_max": CLV_SHORT_MAX,
                "bos_lookback_bars": BOS_LOOKBACK,
                "trend": f"EMA{EMA_FAST}/EMA{EMA_SLOW} aligned and EMA{EMA_SLOW} slope over {EMA_SLOPE_BARS} bars agrees",
            },
            "entry": "first 15m open after confirmed 4H close",
            "max_entry_gap_atr": MAX_ENTRY_GAP_ATR,
            "sl": "beyond signal extreme/zone edge plus ATR buffer",
            "sl_buffer_atr": SL_BUFFER_ATR,
            "risk_atr_range": [MIN_RISK_ATR, MAX_RISK_ATR],
            "tp1": f"{TP1_R:.1f}R, {TP1_FRAC:.0%} size then stop to breakeven",
            "tp2": "near edge of nearest pre-existing opposite S/R zone",
            "min_target_r": MIN_TARGET_R,
            "max_hold_signal_bars": MAX_HOLD_SIGNAL_BARS,
            "zone_signal_cooldown_bars": ZONE_SIGNAL_COOLDOWN_BARS,
            "intrabar": "15m stop-first conservative",
        },
        "costs": {
            "fee_bps": core.FEE_BPS,
            "slippage_bps": core.SLIP_BPS,
            "per_fill_total_bps": core.COST_BPS,
        },
        "summary": core.metrics(alltr),
        "directions": grouped_metrics(alltr, "direction"),
        "symbols": grouped_metrics(alltr, "symbol"),
        "years": {k: core.metrics(v) for k, v in sorted(years.items())},
        "symbol_details": cells,
        "trades": alltr,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("FINAL", json.dumps({k: v for k, v in out.items() if k != "trades"}, indent=2), flush=True)


if __name__ == "__main__":
    main()
