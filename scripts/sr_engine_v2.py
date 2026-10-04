from collections import defaultdict

import backtest_sr_reclaim_v1_crypto as legacy

ZONE_TFS = (240, 1440)
FRACTAL_R = 2
EVENT_REACTION_MIN_ATR = 0.75
MERGE_ATR = 0.40
HALF_WIDTH_ATR = 0.20
MAX_HALF_WIDTH_ATR = 0.60
MIN_TOUCHES = 2
MIN_SCORE = 3.00
MAX_AGE_DAYS = 540
MIN_EVENT_SEP_HOURS = 12


def body_lo(x):
    return min(x["o"], x["c"])


def body_hi(x):
    return max(x["o"], x["c"])


def build_events(b15):
    out = []
    for tf in ZONE_TFS:
        d = legacy.core.enrich_atr(legacy.core.aggregate(b15, tf))
        w = 2.0 if tf == 1440 else 1.0
        for i in range(FRACTAL_R, len(d) - FRACTAL_R):
            win = d[i - FRACTAL_R : i + FRACTAL_R + 1]
            atr = d[i].get("atr14")
            if atr is None or atr <= 0:
                continue
            ki = i + FRACTAL_R
            known_t = d[ki]["ct"]

            blo = body_lo(d[i])
            lows = [body_lo(x) for x in win]
            if blo == min(lows) and lows.count(blo) == 1:
                reaction = (max(d[j]["h"] for j in range(i, ki + 1)) - blo) / atr
                if reaction >= EVENT_REACTION_MIN_ATR:
                    out.append({
                        "kind": "L", "level": blo, "atr": atr, "tf": tf,
                        "event_t": d[i]["ct"], "known_t": known_t,
                        "reaction_atr": reaction,
                        "weight": w * min(2.0, reaction),
                    })

            bhi = body_hi(d[i])
            highs = [body_hi(x) for x in win]
            if bhi == max(highs) and highs.count(bhi) == 1:
                reaction = (bhi - min(d[j]["l"] for j in range(i, ki + 1))) / atr
                if reaction >= EVENT_REACTION_MIN_ATR:
                    out.append({
                        "kind": "H", "level": bhi, "atr": atr, "tf": tf,
                        "event_t": d[i]["ct"], "known_t": known_t,
                        "reaction_atr": reaction,
                        "weight": w * min(2.0, reaction),
                    })

    out.sort(key=lambda e: (e["known_t"], e["event_t"], e["tf"], e["kind"]))
    return out


def _recalc(z):
    ps = z["points"]
    total_w = sum(p["weight"] for p in ps)
    if total_w <= 0:
        total_w = float(len(ps))
    z["center"] = sum(p["level"] * p["weight"] for p in ps) / total_w
    z["avg_atr"] = sum(p["atr"] for p in ps) / len(ps)
    dev = max([0.0] + [abs(p["level"] - z["center"]) for p in ps])
    half = max(HALF_WIDTH_ATR * z["avg_atr"], dev)
    half = min(half, MAX_HALF_WIDTH_ATR * z["avg_atr"])
    z["lo"] = z["center"] - half
    z["hi"] = z["center"] + half
    z["touches"] = len(ps)
    z["score"] = sum(p["weight"] for p in ps)
    z["daily_events"] = sum(p["tf"] == 1440 for p in ps)
    z["low_events"] = sum(p["kind"] == "L" for p in ps)
    z["high_events"] = sum(p["kind"] == "H" for p in ps)
    z["avg_reaction_atr"] = sum(p["reaction_atr"] for p in ps) / len(ps)
    z["last_event_t"] = max(p["event_t"] for p in ps)
    z["last_known_t"] = max(p["known_t"] for p in ps)


def add_event(zones, e, next_id):
    best = None
    best_dist = None
    for z in zones:
        scale = max(e["atr"], z["avg_atr"])
        dist = abs(e["level"] - z["center"])
        if dist <= MERGE_ATR * scale and (best_dist is None or dist < best_dist):
            best, best_dist = z, dist

    if best is None:
        z = {"id": next_id, "points": [e.copy()]}
        _recalc(z)
        zones.append(z)
        return next_id + 1

    sep = MIN_EVENT_SEP_HOURS * 3_600_000
    nearby = [p for p in best["points"] if abs(e["event_t"] - p["event_t"]) < sep]
    if nearby:
        # Same market turn across 4H/1D: keep the stronger observation rather
        # than double-counting it as two independent touches.
        strongest = max(nearby, key=lambda p: p["weight"])
        if e["weight"] > strongest["weight"]:
            best["points"].remove(strongest)
            best["points"].append(e.copy())
            _recalc(best)
    else:
        best["points"].append(e.copy())
        _recalc(best)
    return next_id


def active_zones(zones, t):
    max_age = MAX_AGE_DAYS * 86_400_000
    out = []
    for z in zones:
        if z["touches"] < MIN_TOUCHES or z["score"] < MIN_SCORE:
            continue
        if t - z["last_event_t"] > max_age:
            continue
        out.append({
            "id": z["id"], "center": z["center"], "lo": z["lo"], "hi": z["hi"],
            "touches": z["touches"], "score": z["score"],
            "daily_events": z["daily_events"],
            "low_events": z["low_events"], "high_events": z["high_events"],
            "avg_reaction_atr": z["avg_reaction_atr"],
            "last_event_t": z["last_event_t"], "last_known_t": z["last_known_t"],
        })
    return out
