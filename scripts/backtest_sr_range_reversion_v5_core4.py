import json
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import backtest_sr_reclaim_v1_crypto as sr

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/validation/sr_range_reversion_v5_core4_5y.json"
UTC = timezone.utc

SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT")
SIGNAL_TF_MIN = 60

ER_N = 20
ER_MAX = 0.35
EMA_FAST = 20
EMA_SLOW = 50
EMA_GAP_ATR_MAX = 1.00
RANGE_WIDTH_ATR_MIN = 3.0
RANGE_WIDTH_ATR_MAX = 12.0

CLV_LONG_MIN = 0.65
CLV_SHORT_MAX = 0.35
SL_BUFFER_ATR = 0.15
RISK_MIN_ATR = 0.35
RISK_MAX_ATR = 2.50
ENTRY_GAP_MAX_ATR = 0.25
TP1_FRAC = 0.50
MAX_HOLD_HOURS = 96
PAIR_COOLDOWN_HOURS = 48


def ema(vals, n):
    a = 2.0 / (n + 1.0)
    out, cur = [], None
    for v in vals:
        cur = v if cur is None else a * v + (1.0 - a) * cur
        out.append(cur)
    return out


def enrich_range(d):
    c = [x["c"] for x in d]
    e20 = ema(c, EMA_FAST)
    e50 = ema(c, EMA_SLOW)
    atr = None
    for i, x in enumerate(d):
        pc = d[i - 1]["c"] if i else x["c"]
        tr = max(x["h"] - x["l"], abs(x["h"] - pc), abs(x["l"] - pc))
        atr = tr if atr is None else ((13.0 * atr) + tr) / 14.0
        x["atr14_v5"] = atr
        x["ema20_v5"] = e20[i]
        x["ema50_v5"] = e50[i]
        if i >= ER_N:
            direction = abs(c[i] - c[i - ER_N])
            noise = sum(abs(c[j] - c[j - 1]) for j in range(i - ER_N + 1, i + 1))
            x["er20_v5"] = direction / noise if noise > 1e-12 else 0.0
        else:
            x["er20_v5"] = None
    return d


def range_regime(h4, ct4, t):
    k = bisect_left(ct4, t + 1) - 1
    if k < max(EMA_SLOW, ER_N):
        return None
    x = h4[k]
    atr = x["atr14_v5"]
    er = x["er20_v5"]
    if not atr or atr <= 0 or er is None:
        return None
    gap = abs(x["ema20_v5"] - x["ema50_v5"]) / atr
    if er <= ER_MAX and gap <= EMA_GAP_ATR_MAX:
        return {"atr": atr, "er": er, "ema_gap_atr": gap}
    return None


def clv(x):
    return (x["c"] - x["l"]) / (x["h"] - x["l"]) if x["h"] > x["l"] else 0.5


def pair_for_price(active, px, h4_atr):
    below = [z for z in active if z["hi"] < px]
    above = [z for z in active if z["lo"] > px]
    if not below or not above:
        return None
    sup = max(below, key=lambda z: z["hi"])
    res = min(above, key=lambda z: z["lo"])
    width = res["lo"] - sup["hi"]
    if width <= 0:
        return None
    width_atr = width / h4_atr
    if not (RANGE_WIDTH_ATR_MIN <= width_atr <= RANGE_WIDTH_ATR_MAX):
        return None
    return sup, res, width_atr


def make_signals(b15):
    h1 = sr.core.enrich_atr(sr.core.aggregate(b15, SIGNAL_TF_MIN))
    h4 = enrich_range(sr.core.aggregate(b15, 240))
    ct4 = [x["ct"] for x in h4]
    events = sr.zone_events(b15)

    zones, next_zone_id, eidx = [], 1, 0
    last_pair_t = {}
    signals = []
    st = defaultdict(int)

    for i in range(EMA_SLOW + 5, len(h1)):
        x, prev = h1[i], h1[i - 1]
        now = x["t"]
        atr = x["atr14"]
        if not atr or atr <= 0:
            continue

        while eidx < len(events) and events[eidx]["known_t"] <= now:
            next_zone_id = sr.add_event(zones, events[eidx], next_zone_id)
            eidx += 1
        active = sr.snapshot_active(zones, now)
        if not active:
            continue

        rr = range_regime(h4, ct4, x["ct"])
        if rr is None:
            st["regime_reject"] += 1
            continue

        pair = pair_for_price(active, prev["c"], rr["atr"])
        if pair is None:
            st["pair_reject"] += 1
            continue
        sup, res, width_atr = pair
        pair_id = (sup["id"], res["id"])
        if x["ct"] - last_pair_t.get(pair_id, -10**18) < PAIR_COOLDOWN_HOURS * 3_600_000:
            st["pair_cooldown"] += 1
            continue

        cv = clv(x)

        # Long rejection from lower range boundary.
        if (
            prev["c"] > sup["hi"]
            and x["l"] <= sup["center"]
            and x["c"] > sup["hi"]
            and x["c"] > x["o"]
            and cv >= CLV_LONG_MIN
        ):
            stop = min(x["l"], sup["lo"]) - SL_BUFFER_ATR * atr
            mid = (sup["hi"] + res["lo"]) / 2.0
            tp2 = res["lo"]
            if x["c"] < mid < tp2:
                signals.append({
                    "side": "LONG", "activation": x["ct"], "signal_close": x["c"],
                    "atr": atr, "stop": stop, "tp1_ref": mid, "tp2_ref": tp2,
                    "support": sup.copy(), "resistance": res.copy(),
                    "range_width_atr": width_atr, "er20": rr["er"],
                    "ema_gap_atr": rr["ema_gap_atr"], "signal_clv": cv,
                })
                last_pair_t[pair_id] = x["ct"]
                st["signals_long"] += 1

        # Short rejection from upper range boundary.
        elif (
            prev["c"] < res["lo"]
            and x["h"] >= res["center"]
            and x["c"] < res["lo"]
            and x["c"] < x["o"]
            and cv <= CLV_SHORT_MAX
        ):
            stop = max(x["h"], res["hi"]) + SL_BUFFER_ATR * atr
            mid = (sup["hi"] + res["lo"]) / 2.0
            tp2 = sup["hi"]
            if x["c"] > mid > tp2:
                signals.append({
                    "side": "SHORT", "activation": x["ct"], "signal_close": x["c"],
                    "atr": atr, "stop": stop, "tp1_ref": mid, "tp2_ref": tp2,
                    "support": sup.copy(), "resistance": res.copy(),
                    "range_width_atr": width_atr, "er20": rr["er"],
                    "ema_gap_atr": rr["ema_gap_atr"], "signal_clv": cv,
                })
                last_pair_t[pair_id] = x["ct"]
                st["signals_short"] += 1

    return signals, dict(st)


def execute(sym, b15):
    signals, st = make_signals(b15)
    t15 = [x["t"] for x in b15]
    lo = int(sr.core.EVAL_START.timestamp() * 1000)
    hi = int(sr.core.EVAL_END.timestamp() * 1000)
    trades = []
    busy_until = -1

    for s in signals:
        if not (lo <= s["activation"] < hi):
            continue
        if s["activation"] < busy_until:
            st["busy"] = st.get("busy", 0) + 1
            continue

        j = bisect_left(t15, s["activation"])
        if j >= len(b15) or b15[j]["t"] >= hi:
            continue
        fill = b15[j]["o"]
        gap_atr = abs(fill - s["signal_close"]) / s["atr"]
        if gap_atr > ENTRY_GAP_MAX_ATR:
            st["gap_filter"] = st.get("gap_filter", 0) + 1
            continue

        side, stop = s["side"], s["stop"]
        risk = (fill - stop) if side == "LONG" else (stop - fill)
        if risk <= 0:
            continue
        risk_atr = risk / s["atr"]
        if not (RISK_MIN_ATR <= risk_atr <= RISK_MAX_ATR):
            st["risk_filter"] = st.get("risk_filter", 0) + 1
            continue

        tp1, tp2 = s["tp1_ref"], s["tp2_ref"]
        if side == "LONG" and not (fill < tp1 < tp2):
            continue
        if side == "SHORT" and not (fill > tp1 > tp2):
            continue

        pnl = -sr.core.cost(fill)
        rem = 1.0
        cur_stop = stop
        hit1 = hit2 = False
        reason = "TIME"
        exit_t = b15[j]["ct"]
        last_i = j
        hold_until = b15[j]["t"] + MAX_HOLD_HOURS * 3_600_000

        for k in range(j, len(b15)):
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
                    f = min(TP1_FRAC, rem)
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
                    f = min(TP1_FRAC, rem)
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
            rem = 0
            exit_t = b["ct"]
            reason = "TIME"

        trades.append({
            "symbol": sym, "timeframe": "1H", "direction": side,
            "signal_t": s["activation"], "entry_t": b15[j]["t"], "exit_t": exit_t,
            "fill": fill, "initial_sl": stop, "tp1": tp1, "tp2": tp2,
            "risk": risk, "risk_atr": risk_atr, "r": pnl / risk,
            "reason": reason, "tp1_hit": hit1, "tp2_hit": hit2,
            "hold_hours": max(0.0, (exit_t - b15[j]["t"]) / 3_600_000),
            "support_zone_id": s["support"]["id"], "resistance_zone_id": s["resistance"]["id"],
            "range_width_atr": s["range_width_atr"], "er20": s["er20"],
            "ema_gap_atr": s["ema_gap_atr"], "signal_clv": s["signal_clv"],
            "target1_r_at_fill": abs(tp1 - fill) / risk,
            "target2_r_at_fill": abs(tp2 - fill) / risk,
        })
        busy_until = exit_t

    st["filled"] = len(trades)
    return trades, st


def grouped_metrics(trades, key):
    g = defaultdict(list)
    for t in trades:
        g[t[key]].append(t)
    return {k: sr.core.metrics(v) for k, v in sorted(g.items())}


def main():
    alltr = []
    details = {}
    for sym in SYMBOLS:
        b15 = sr.core.load_15m(sym)
        ts, st = execute(sym, b15)
        alltr += ts
        details[sym] = {"metrics": sr.core.metrics(ts), "stats": st}
        print("RESULT", sym, json.dumps(details[sym]), flush=True)

    years = defaultdict(list)
    for t in alltr:
        years[str(datetime.fromtimestamp(t["entry_t"] / 1000, UTC).year)].append(t)

    out = {
        "strategy": "SR Range Reversion v5 frozen baseline",
        "asset_class": "Binance USDT-M perpetual",
        "rules": {
            "zone_source": "4H+1D confirmed body-edge zones, >=2 interactions",
            "signal_tf": "1H",
            "range_regime": {
                "4h_er20_max": ER_MAX,
                "4h_ema20_50_gap_atr_max": EMA_GAP_ATR_MAX,
                "range_width_atr": [RANGE_WIDTH_ATR_MIN, RANGE_WIDTH_ATR_MAX],
            },
            "setup": "reject lower/upper boundary from inside a neutral HTF range",
            "entry": "next 15m open",
            "sl_buffer_atr": SL_BUFFER_ATR,
            "risk_atr_range": [RISK_MIN_ATR, RISK_MAX_ATR],
            "tp1": "range midpoint, 50%, then BE",
            "tp2": "near edge of opposite HTF zone",
            "max_hold_hours": MAX_HOLD_HOURS,
            "pair_cooldown_hours": PAIR_COOLDOWN_HOURS,
            "same_bar": "15m stop-first conservative",
        },
        "costs": {
            "fee_bps": sr.core.FEE_BPS, "slippage_bps": sr.core.SLIP_BPS,
            "per_fill_total_bps": sr.core.COST_BPS,
        },
        "summary": sr.core.metrics(alltr),
        "directions": grouped_metrics(alltr, "direction"),
        "symbols": grouped_metrics(alltr, "symbol"),
        "years": {k: sr.core.metrics(v) for k, v in sorted(years.items())},
        "details": details,
        "trades": alltr,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("FINAL", json.dumps({k: v for k, v in out.items() if k != "trades"}, indent=2), flush=True)


if __name__ == "__main__":
    main()
