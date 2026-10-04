import json
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import backtest_sr_reclaim_v1_crypto as sr

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/validation/sr_reclaim_v1_1_retest_entry.json"
UTC = timezone.utc

ENTRY_VALID_BARS = 3
MIN_TARGET_R = 2.0
MIN_RISK_ATR = 0.35
MAX_RISK_ATR = 2.0

VARIANTS = ("zone_edge", "zone_center")


def find_candidates(b15):
    d = sr.core.enrich_atr(sr.core.aggregate(b15, sr.SIGNAL_TF_MIN))
    closes = [x["c"] for x in d]
    ef = sr.ema(closes, sr.EMA_FAST)
    es = sr.ema(closes, sr.EMA_SLOW)
    events = sr.zone_events(b15)
    zones, next_zone_id, eidx = [], 1, 0
    out = []
    stats = defaultdict(int)
    last_signal_i = {}

    warm = max(sr.EMA_SLOW + sr.EMA_SLOPE_BARS, sr.BOS_LOOKBACK + 2)
    for i in range(warm, len(d)):
        x, prev = d[i], d[i - 1]
        while eidx < len(events) and events[eidx]["known_t"] <= x["t"]:
            next_zone_id = sr.add_event(zones, events[eidx], next_zone_id)
            eidx += 1

        active = sr.snapshot_active(zones, x["t"])
        if not active:
            continue
        atr = x["atr14"]
        if not atr or atr <= 0 or x["h"] <= x["l"]:
            continue

        clv = (x["c"] - x["l"]) / (x["h"] - x["l"])
        prior_hi = max(d[j]["h"] for j in range(i - sr.BOS_LOOKBACK, i))
        prior_lo = min(d[j]["l"] for j in range(i - sr.BOS_LOOKBACK, i))

        longs = [
            z for z in active
            if prev["c"] > z["hi"]
            and x["l"] <= z["hi"]
            and x["l"] <= z["center"]
            and x["c"] > z["hi"]
            and clv >= sr.CLV_LONG_MIN
            and x["c"] > prior_hi
            and ef[i] >= es[i]
            and es[i] > es[i - sr.EMA_SLOPE_BARS]
        ]
        shorts = [
            z for z in active
            if prev["c"] < z["lo"]
            and x["h"] >= z["lo"]
            and x["h"] >= z["center"]
            and x["c"] < z["lo"]
            and clv <= sr.CLV_SHORT_MAX
            and x["c"] < prior_lo
            and ef[i] <= es[i]
            and es[i] < es[i - sr.EMA_SLOPE_BARS]
        ]

        candidates = []
        if longs:
            candidates.append(("LONG", max(longs, key=lambda z: z["center"])))
        if shorts:
            candidates.append(("SHORT", min(shorts, key=lambda z: z["center"])))

        for side, z in candidates:
            if i - last_signal_i.get(z["id"], -10**9) < sr.ZONE_SIGNAL_COOLDOWN_BARS:
                stats["zone_cooldown"] += 1
                continue

            if side == "LONG":
                stop = min(x["l"], z["lo"]) - sr.SL_BUFFER_ATR * atr
                target_candidates = [q for q in active if q["id"] != z["id"] and q["lo"] > z["hi"]]
                if not target_candidates:
                    stats["no_opposite_zone"] += 1
                    continue
                tz = min(target_candidates, key=lambda q: q["lo"])
                tp2 = tz["lo"]
            else:
                stop = max(x["h"], z["hi"]) + sr.SL_BUFFER_ATR * atr
                target_candidates = [q for q in active if q["id"] != z["id"] and q["hi"] < z["lo"]]
                if not target_candidates:
                    stats["no_opposite_zone"] += 1
                    continue
                tz = max(target_candidates, key=lambda q: q["hi"])
                tp2 = tz["hi"]

            out.append({
                "side": side,
                "activation": x["ct"],
                "signal_i": i,
                "signal_close": x["c"],
                "atr": atr,
                "stop": stop,
                "tp2": tp2,
                "zone": z.copy(),
                "target_zone": tz.copy(),
                "signal_clv": clv,
            })
            last_signal_i[z["id"]] = i
            stats["candidates"] += 1

    return out, dict(stats)


def fill_limit(b15, t15, s, entry):
    start = bisect_left(t15, s["activation"])
    valid_until = s["activation"] + ENTRY_VALID_BARS * sr.SIGNAL_TF_MIN * 60_000
    stop = s["stop"]
    side = s["side"]

    for j in range(start, len(b15)):
        b = b15[j]
        if b["t"] >= valid_until:
            break
        if side == "LONG":
            if b["o"] <= stop:
                return None, None, "INVALID_GAP_STOP"
            if b["o"] <= entry:
                return j, b["o"], None
            if b["l"] <= entry:
                return j, entry, None
        else:
            if b["o"] >= stop:
                return None, None, "INVALID_GAP_STOP"
            if b["o"] >= entry:
                return j, b["o"], None
            if b["h"] >= entry:
                return j, entry, None
    return None, None, "EXPIRED"


def simulate_variant(sym, b15, candidates, variant):
    t15 = [x["t"] for x in b15]
    lo = int(sr.core.EVAL_START.timestamp() * 1000)
    hi = int(sr.core.EVAL_END.timestamp() * 1000)
    trades, st = [], defaultdict(int)
    busy_until = -1

    for s in candidates:
        if not (lo <= s["activation"] < hi):
            continue
        if s["activation"] < busy_until:
            st["signal_while_busy"] += 1
            continue

        z = s["zone"]
        if variant == "zone_edge":
            entry = z["hi"] if s["side"] == "LONG" else z["lo"]
        elif variant == "zone_center":
            entry = z["center"]
        else:
            raise ValueError(variant)

        if s["side"] == "LONG":
            risk_ref = entry - s["stop"]
            room_ref = s["tp2"] - entry
        else:
            risk_ref = s["stop"] - entry
            room_ref = entry - s["tp2"]
        if risk_ref <= 0 or room_ref <= 0:
            st["invalid_geometry"] += 1
            continue
        risk_atr = risk_ref / s["atr"]
        if not (MIN_RISK_ATR <= risk_atr <= MAX_RISK_ATR):
            st["risk_filter"] += 1
            continue
        if room_ref / risk_ref < MIN_TARGET_R:
            st["target_rr_filter"] += 1
            continue

        st["orders"] += 1
        fill_i, fill, fail = fill_limit(b15, t15, s, entry)
        if fill_i is None:
            st["expired" if fail == "EXPIRED" else "invalid_gap_stop"] += 1
            continue

        side, stop, tp2 = s["side"], s["stop"], s["tp2"]
        risk = (fill - stop) if side == "LONG" else (stop - fill)
        room = (tp2 - fill) if side == "LONG" else (fill - tp2)
        if risk <= 0 or room <= 0 or room / risk < MIN_TARGET_R:
            st["post_fill_rr_filter"] += 1
            continue

        tp1 = fill + risk if side == "LONG" else fill - risk
        st["filled"] += 1
        pnl = -sr.core.cost(fill)
        rem = 1.0
        cur_stop = stop
        hit1 = hit2 = False
        reason = "TIME"
        exit_t = b15[fill_i]["ct"]
        hold_until = b15[fill_i]["t"] + sr.MAX_HOLD_SIGNAL_BARS * sr.SIGNAL_TF_MIN * 60_000
        last_i = fill_i

        for k in range(fill_i, len(b15)):
            b = b15[k]
            if b["t"] >= hi or b["t"] >= hold_until:
                break
            last_i = k

            if side == "LONG":
                if b["o"] <= cur_stop:
                    pnl += rem * (b["o"] - fill) - sr.core.cost(b["o"], rem)
                    rem = 0; exit_t = b["ct"]; reason = "GAP_STOP"; break
                if b["l"] <= cur_stop:
                    pnl += rem * (cur_stop - fill) - sr.core.cost(cur_stop, rem)
                    rem = 0; exit_t = b["ct"]; reason = "STOP"; break
                if not hit1 and (b["o"] >= tp1 or b["h"] >= tp1):
                    px = b["o"] if b["o"] >= tp1 else tp1
                    f = min(sr.TP1_FRAC, rem)
                    pnl += f * (px - fill) - sr.core.cost(px, f)
                    rem -= f; hit1 = True; cur_stop = max(cur_stop, fill)
                    if rem > 0 and b["l"] <= cur_stop:
                        pnl += rem * (cur_stop - fill) - sr.core.cost(cur_stop, rem)
                        rem = 0; exit_t = b["ct"]; reason = "BE_AFTER_TP1"; break
                if rem > 0 and hit1 and (b["o"] >= tp2 or b["h"] >= tp2):
                    px = b["o"] if b["o"] >= tp2 else tp2
                    pnl += rem * (px - fill) - sr.core.cost(px, rem)
                    rem = 0; hit2 = True; exit_t = b["ct"]; reason = "TP2"; break
            else:
                if b["o"] >= cur_stop:
                    pnl += rem * (fill - b["o"]) - sr.core.cost(b["o"], rem)
                    rem = 0; exit_t = b["ct"]; reason = "GAP_STOP"; break
                if b["h"] >= cur_stop:
                    pnl += rem * (fill - cur_stop) - sr.core.cost(cur_stop, rem)
                    rem = 0; exit_t = b["ct"]; reason = "STOP"; break
                if not hit1 and (b["o"] <= tp1 or b["l"] <= tp1):
                    px = b["o"] if b["o"] <= tp1 else tp1
                    f = min(sr.TP1_FRAC, rem)
                    pnl += f * (fill - px) - sr.core.cost(px, f)
                    rem -= f; hit1 = True; cur_stop = min(cur_stop, fill)
                    if rem > 0 and b["h"] >= cur_stop:
                        pnl += rem * (fill - cur_stop) - sr.core.cost(cur_stop, rem)
                        rem = 0; exit_t = b["ct"]; reason = "BE_AFTER_TP1"; break
                if rem > 0 and hit1 and (b["o"] <= tp2 or b["l"] <= tp2):
                    px = b["o"] if b["o"] <= tp2 else tp2
                    pnl += rem * (fill - px) - sr.core.cost(px, rem)
                    rem = 0; hit2 = True; exit_t = b["ct"]; reason = "TP2"; break

        if rem > 0:
            b = b15[last_i]
            px = b["c"]
            pnl += rem * ((px - fill) if side == "LONG" else (fill - px)) - sr.core.cost(px, rem)
            exit_t = b["ct"]
            reason = "TIME"

        trades.append({
            "symbol": sym,
            "timeframe": "4H",
            "variant": variant,
            "direction": side,
            "signal_t": s["activation"],
            "entry_t": b15[fill_i]["t"],
            "exit_t": exit_t,
            "signal_close": s["signal_close"],
            "order_entry": entry,
            "fill": fill,
            "initial_sl": stop,
            "tp1": tp1,
            "tp2": tp2,
            "risk": risk,
            "r": pnl / risk,
            "reason": reason,
            "tp1_hit": hit1,
            "tp2_hit": hit2,
            "hold_hours": max(0, (exit_t - b15[fill_i]["t"]) / 3_600_000),
            "zone_id": z["id"],
            "zone_touches": z["touches"],
            "target_zone_id": s["target_zone"]["id"],
            "target_r_at_fill": room / risk,
            "risk_atr": risk / s["atr"],
        })
        busy_until = exit_t

    st["fill_rate"] = st["filled"] / st["orders"] if st["orders"] else None
    return trades, dict(st)


def grouped_metrics(trades, key):
    g = defaultdict(list)
    for t in trades:
        g[t[key]].append(t)
    return {k: sr.core.metrics(v) for k, v in sorted(g.items())}


def main():
    cache = {sym: sr.core.load_15m(sym) for sym in sr.SYMBOLS}
    candidate_cache = {}
    candidate_stats = {}
    for sym, b15 in cache.items():
        cs, st = find_candidates(b15)
        candidate_cache[sym] = cs
        candidate_stats[sym] = st
        print("CANDIDATES", sym, len(cs), json.dumps(st), flush=True)

    variants = {}
    for variant in VARIANTS:
        alltr = []
        per_symbol = {}
        for sym, b15 in cache.items():
            ts, st = simulate_variant(sym, b15, candidate_cache[sym], variant)
            alltr += ts
            per_symbol[sym] = {"metrics": sr.core.metrics(ts), "stats": st}
        variants[variant] = {
            "summary": sr.core.metrics(alltr),
            "directions": grouped_metrics(alltr, "direction"),
            "symbols": grouped_metrics(alltr, "symbol"),
            "details": per_symbol,
            "trades": alltr,
        }
        print("RESULT", variant, json.dumps(variants[variant]["summary"]), flush=True)

    out = {
        "strategy": "SR Reclaim v1.1 retest-entry diagnostic",
        "base_confirmation": "same as SR Reclaim v1",
        "entry_valid_4h_bars": ENTRY_VALID_BARS,
        "min_target_r": MIN_TARGET_R,
        "risk_atr_range": [MIN_RISK_ATR, MAX_RISK_ATR],
        "candidate_stats": candidate_stats,
        "variants": variants,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("FINAL", json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "trades"} for k, v in variants.items()}, indent=2), flush=True)


if __name__ == "__main__":
    main()
