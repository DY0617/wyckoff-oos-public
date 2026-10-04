import json
import statistics
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import backtest_sr_reclaim_v1_crypto as sr
import sr_engine_v2 as eng

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/validation/sr_momentum_breakout_v7_core4_5y.json"
UTC = timezone.utc

SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT")

EMA_FAST = 20
EMA_SLOW = 50
BREAK_BUFFER_ATR = 0.15
BODY_MIN_ATR = 0.80
VOL_MIN_MULT = 1.30
CLV_LONG_MIN = 0.75
CLV_SHORT_MAX = 0.25

SL_BUFFER_ATR = 0.15
RISK_MIN_ATR = 0.50
RISK_MAX_ATR = 2.50
ENTRY_GAP_MAX_ATR = 0.30
TP1_R = 1.00
TP2_R = 2.50
TP1_FRAC = 0.50
MAX_HOLD_HOURS = 72
ZONE_COOLDOWN_HOURS = 48


def ema(vals, n):
    a = 2.0 / (n + 1.0)
    out, cur = [], None
    for v in vals:
        cur = v if cur is None else a * v + (1.0 - a) * cur
        out.append(cur)
    return out


def enrich_trend(d):
    c = [x["c"] for x in d]
    e20, e50 = ema(c, EMA_FAST), ema(c, EMA_SLOW)
    for i, x in enumerate(d):
        x["ema20_v7"] = e20[i]
        x["ema50_v7"] = e50[i]
    return d


def trend_at(d, cts, t):
    k = bisect_left(cts, t + 1) - 1
    if k < EMA_SLOW + 3:
        return None
    x = d[k]
    if (
        x["ema20_v7"] > x["ema50_v7"]
        and x["c"] > x["ema20_v7"]
        and x["ema50_v7"] > d[k - 3]["ema50_v7"]
    ):
        return "LONG"
    if (
        x["ema20_v7"] < x["ema50_v7"]
        and x["c"] < x["ema20_v7"]
        and x["ema50_v7"] < d[k - 3]["ema50_v7"]
    ):
        return "SHORT"
    return None


def enrich_h1(d):
    d = sr.core.enrich_atr(d)
    vols = [x["v"] for x in d]
    for i, x in enumerate(d):
        x["vol_sma20_v7"] = statistics.fmean(vols[i - 19:i + 1]) if i >= 19 else None
    return d


def clv(x):
    return (x["c"] - x["l"]) / (x["h"] - x["l"]) if x["h"] > x["l"] else 0.5


def make_signals(b15):
    h1 = enrich_h1(sr.core.aggregate(b15, 60))
    h4 = enrich_trend(sr.core.aggregate(b15, 240))
    d1 = enrich_trend(sr.core.aggregate(b15, 1440))
    ct4, ctd = [x["ct"] for x in h4], [x["ct"] for x in d1]

    events = eng.build_events(b15)
    zones, next_id, eidx = [], 1, 0
    last_used = {}
    signals = []
    st = defaultdict(int)

    for i in range(EMA_SLOW + 5, len(h1)):
        x, prev = h1[i], h1[i - 1]
        now = x["t"]
        atr = x["atr14"]
        vma = x["vol_sma20_v7"]
        if not atr or atr <= 0 or not vma or vma <= 0:
            continue

        while eidx < len(events) and events[eidx]["known_t"] <= now:
            next_id = eng.add_event(zones, events[eidx], next_id)
            eidx += 1
        active = eng.active_zones(zones, now)
        if not active:
            continue

        r4, rd = trend_at(h4, ct4, x["ct"]), trend_at(d1, ctd, x["ct"])
        if r4 is None or rd is None or r4 != rd:
            st["trend_reject"] += 1
            continue

        body_atr = abs(x["c"] - x["o"]) / atr
        cv = clv(x)
        vol_mult = x["v"] / vma

        if r4 == "LONG" and body_atr >= BODY_MIN_ATR and cv >= CLV_LONG_MIN and vol_mult >= VOL_MIN_MULT:
            crossed = [
                z for z in active
                if prev["c"] <= z["hi"]
                and x["c"] > z["hi"] + BREAK_BUFFER_ATR * atr
                and x["ct"] - last_used.get(z["id"], -10**18) >= ZONE_COOLDOWN_HOURS * 3_600_000
            ]
            if crossed:
                z = max(crossed, key=lambda q: q["center"])
                signals.append({
                    "side": "LONG", "activation": x["ct"], "signal_close": x["c"],
                    "atr": atr, "stop": z["lo"] - SL_BUFFER_ATR * atr,
                    "zone": z.copy(), "body_atr": body_atr,
                    "vol_mult": vol_mult, "signal_clv": cv,
                })
                last_used[z["id"]] = x["ct"]
                st["signals_long"] += 1

        elif r4 == "SHORT" and body_atr >= BODY_MIN_ATR and cv <= CLV_SHORT_MAX and vol_mult >= VOL_MIN_MULT:
            crossed = [
                z for z in active
                if prev["c"] >= z["lo"]
                and x["c"] < z["lo"] - BREAK_BUFFER_ATR * atr
                and x["ct"] - last_used.get(z["id"], -10**18) >= ZONE_COOLDOWN_HOURS * 3_600_000
            ]
            if crossed:
                z = min(crossed, key=lambda q: q["center"])
                signals.append({
                    "side": "SHORT", "activation": x["ct"], "signal_close": x["c"],
                    "atr": atr, "stop": z["hi"] + SL_BUFFER_ATR * atr,
                    "zone": z.copy(), "body_atr": body_atr,
                    "vol_mult": vol_mult, "signal_clv": cv,
                })
                last_used[z["id"]] = x["ct"]
                st["signals_short"] += 1

    return signals, dict(st)


def execute(sym, b15):
    signals, st = make_signals(b15)
    t15 = [x["t"] for x in b15]
    lo = int(sr.core.EVAL_START.timestamp() * 1000)
    hi = int(sr.core.EVAL_END.timestamp() * 1000)
    trades, busy_until = [], -1

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
        gap = abs(fill - s["signal_close"]) / s["atr"]
        if gap > ENTRY_GAP_MAX_ATR:
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

        tp1 = fill + TP1_R * risk if side == "LONG" else fill - TP1_R * risk
        tp2 = fill + TP2_R * risk if side == "LONG" else fill - TP2_R * risk

        pnl = -sr.core.cost(fill)
        rem, cur_stop = 1.0, stop
        hit1 = hit2 = False
        reason, exit_t, last_i = "TIME", b15[j]["ct"], j
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
            exit_t = b["ct"]
            reason = "TIME"

        z = s["zone"]
        trades.append({
            "symbol": sym, "timeframe": "1H", "direction": side,
            "signal_t": s["activation"], "entry_t": b15[j]["t"], "exit_t": exit_t,
            "fill": fill, "initial_sl": stop, "tp1": tp1, "tp2": tp2,
            "risk": risk, "risk_atr": risk_atr, "r": pnl / risk,
            "reason": reason, "tp1_hit": hit1, "tp2_hit": hit2,
            "hold_hours": max(0.0, (exit_t - b15[j]["t"]) / 3_600_000),
            "zone_id": z["id"], "zone_touches": z["touches"], "zone_score": z["score"],
            "zone_daily_events": z["daily_events"], "zone_avg_reaction_atr": z["avg_reaction_atr"],
            "body_atr": s["body_atr"], "volume_mult": s["vol_mult"],
            "signal_clv": s["signal_clv"], "entry_gap_atr": gap,
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
    alltr, details = [], {}
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
        "strategy": "SR Momentum Breakout v7 frozen baseline",
        "asset_class": "Binance USDT-M perpetual",
        "zone_engine": "SR Engine v2 scored 4H/1D body levels",
        "rules": {
            "trend": "1D+4H EMA20/EMA50 alignment, close beyond EMA20, EMA50 slope aligned",
            "signal_tf": "1H",
            "break_buffer_atr": BREAK_BUFFER_ATR,
            "body_min_atr": BODY_MIN_ATR,
            "volume_min_sma20_mult": VOL_MIN_MULT,
            "clv_long_min": CLV_LONG_MIN, "clv_short_max": CLV_SHORT_MAX,
            "entry": "next 15m open",
            "stop": "far zone edge +0.15 ATR",
            "risk_atr_range": [RISK_MIN_ATR, RISK_MAX_ATR],
            "tp1": [TP1_R, TP1_FRAC], "tp2_r": TP2_R,
            "after_tp1": "breakeven", "max_hold_hours": MAX_HOLD_HOURS,
            "same_bar": "15m stop-first conservative",
        },
        "costs": {"fee_bps": sr.core.FEE_BPS, "slippage_bps": sr.core.SLIP_BPS},
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
