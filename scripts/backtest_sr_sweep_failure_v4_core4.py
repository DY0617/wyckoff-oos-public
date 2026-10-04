import json
import statistics
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import backtest_sr_reclaim_v1_crypto as sr

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/validation/sr_sweep_failure_v4_core4_5y.json"
UTC = timezone.utc

SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT")
SIGNAL_TF_MIN = 60

SWEEP_MIN_ATR = 0.10
SWEEP_MAX_ATR = 0.80
CLV_LONG_MIN = 0.70
CLV_SHORT_MAX = 0.30
WICK_BODY_MIN = 1.00

SL_BUFFER_ATR = 0.15
RISK_MIN_ATR = 0.35
RISK_MAX_ATR = 2.00
ENTRY_GAP_MAX_ATR = 0.25

TP1_R = 1.00
TP2_R = 2.00
TP1_FRAC = 0.50
MAX_HOLD_HOURS = 48
ZONE_COOLDOWN_HOURS = 48


def clv(x):
    return (x["c"] - x["l"]) / (x["h"] - x["l"]) if x["h"] > x["l"] else 0.5


def make_signals(b15):
    h1 = sr.core.enrich_atr(sr.core.aggregate(b15, SIGNAL_TF_MIN))
    events = sr.zone_events(b15)
    zones, next_zone_id, eidx = [], 1, 0
    last_used_t = {}
    signals = []
    st = defaultdict(int)

    for i in range(20, len(h1)):
        x, prev = h1[i], h1[i - 1]
        now = x["t"]
        atr = x["atr14"]
        if atr is None or atr <= 0 or x["h"] <= x["l"]:
            continue

        while eidx < len(events) and events[eidx]["known_t"] <= now:
            next_zone_id = sr.add_event(zones, events[eidx], next_zone_id)
            eidx += 1
        active = sr.snapshot_active(zones, now)
        if not active:
            continue

        cv = clv(x)
        body = abs(x["c"] - x["o"])
        body = max(body, 1e-12)

        longs = []
        shorts = []
        for z in active:
            if x["ct"] - last_used_t.get(z["id"], -10**18) < ZONE_COOLDOWN_HOURS * 3_600_000:
                continue

            # Support sweep failure: price was above the zone, runs below the far edge,
            # then closes fully back above the zone with a dominant lower wick.
            if prev["c"] > z["hi"]:
                depth = (z["lo"] - x["l"]) / atr
                lower_wick = min(x["o"], x["c"]) - x["l"]
                if (
                    SWEEP_MIN_ATR <= depth <= SWEEP_MAX_ATR
                    and x["c"] > z["hi"]
                    and x["c"] > x["o"]
                    and cv >= CLV_LONG_MIN
                    and lower_wick / body >= WICK_BODY_MIN
                ):
                    longs.append((z, depth, lower_wick / body))

            # Resistance sweep failure: mirror.
            if prev["c"] < z["lo"]:
                depth = (x["h"] - z["hi"]) / atr
                upper_wick = x["h"] - max(x["o"], x["c"])
                if (
                    SWEEP_MIN_ATR <= depth <= SWEEP_MAX_ATR
                    and x["c"] < z["lo"]
                    and x["c"] < x["o"]
                    and cv <= CLV_SHORT_MAX
                    and upper_wick / body >= WICK_BODY_MIN
                ):
                    shorts.append((z, depth, upper_wick / body))

        if longs:
            z, depth, wr = max(longs, key=lambda q: q[0]["center"])
            stop = x["l"] - SL_BUFFER_ATR * atr
            signals.append({
                "side": "LONG", "activation": x["ct"], "signal_close": x["c"],
                "atr": atr, "stop": stop, "zone": z.copy(), "sweep_depth_atr": depth,
                "wick_body_ratio": wr, "signal_clv": cv,
            })
            last_used_t[z["id"]] = x["ct"]
            st["signals_long"] += 1

        if shorts:
            z, depth, wr = min(shorts, key=lambda q: q[0]["center"])
            stop = x["h"] + SL_BUFFER_ATR * atr
            signals.append({
                "side": "SHORT", "activation": x["ct"], "signal_close": x["c"],
                "atr": atr, "stop": stop, "zone": z.copy(), "sweep_depth_atr": depth,
                "wick_body_ratio": wr, "signal_clv": cv,
            })
            last_used_t[z["id"]] = x["ct"]
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

        tp1 = fill + TP1_R * risk if side == "LONG" else fill - TP1_R * risk
        tp2 = fill + TP2_R * risk if side == "LONG" else fill - TP2_R * risk

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
            "zone_id": s["zone"]["id"], "zone_touches": s["zone"]["touches"],
            "zone_daily_touches": s["zone"]["daily_touches"],
            "sweep_depth_atr": s["sweep_depth_atr"],
            "wick_body_ratio": s["wick_body_ratio"],
            "signal_clv": s["signal_clv"], "entry_gap_atr": gap_atr,
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
        "strategy": "SR Sweep Failure v4 frozen baseline",
        "asset_class": "Binance USDT-M perpetual",
        "rules": {
            "zone_source": "4H+1D confirmed body-edge zones, >=2 interactions",
            "signal_tf": "1H",
            "setup": "approach from outside, sweep beyond far zone edge by bounded ATR depth, fully reclaim zone on same 1H candle",
            "sweep_depth_atr": [SWEEP_MIN_ATR, SWEEP_MAX_ATR],
            "clv": [CLV_LONG_MIN, CLV_SHORT_MAX],
            "wick_body_min": WICK_BODY_MIN,
            "entry": "next 15m open after completed 1H sweep-failure candle",
            "sl_buffer_atr": SL_BUFFER_ATR,
            "risk_atr_range": [RISK_MIN_ATR, RISK_MAX_ATR],
            "tp1": [TP1_R, TP1_FRAC],
            "tp2_r": TP2_R,
            "after_tp1": "breakeven",
            "max_hold_hours": MAX_HOLD_HOURS,
            "zone_cooldown_hours": ZONE_COOLDOWN_HOURS,
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
