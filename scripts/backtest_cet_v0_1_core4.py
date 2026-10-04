import json
import statistics
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import backtest_sr_reclaim_v1_crypto as base

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/validation/cet_v0_1_core4_5y.json"
UTC = timezone.utc

SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT")
LOOKBACK = 20
ER_N = 20
ATR_FAST = 14
ATR_SLOW = 50

COMPRESSION_ATR_RATIO_MAX = 0.80
COMPRESSION_ER_MAX = 0.35
BREAK_BUFFER_ATR = 0.05
BODY_MIN_ATR = 0.80
VOL_MIN_MULT = 1.50
CLV_LONG_MIN = 0.75
CLV_SHORT_MAX = 0.25

SL_BUFFER_ATR = 0.15
RISK_MIN_ATR = 0.50
RISK_MAX_ATR = 2.50
ENTRY_GAP_MAX_ATR = 0.30

TP1_R = 1.00
TP2_R = 2.50
TP1_FRAC = 0.30
MAX_HOLD_HOURS = 120
COOLDOWN_HOURS = 24


def clv(x):
    return (x["c"] - x["l"]) / (x["h"] - x["l"]) if x["h"] > x["l"] else 0.5


def enrich(h1):
    closes = [x["c"] for x in h1]
    vols = [x["v"] for x in h1]
    a14 = a50 = None
    for i, x in enumerate(h1):
        pc = closes[i - 1] if i else x["c"]
        tr = max(x["h"] - x["l"], abs(x["h"] - pc), abs(x["l"] - pc))
        a14 = tr if a14 is None else ((ATR_FAST - 1) * a14 + tr) / ATR_FAST
        a50 = tr if a50 is None else ((ATR_SLOW - 1) * a50 + tr) / ATR_SLOW
        x["atr14_cet"] = a14
        x["atr50_cet"] = a50
        x["vol_sma20_cet"] = statistics.fmean(vols[i - 19:i + 1]) if i >= 19 else None
        if i >= ER_N:
            direct = abs(closes[i] - closes[i - ER_N])
            noise = sum(abs(closes[j] - closes[j - 1]) for j in range(i - ER_N + 1, i + 1))
            x["er20_cet"] = direct / noise if noise > 1e-12 else 0.0
        else:
            x["er20_cet"] = None
    return h1


def make_signals(b15):
    h1 = enrich(base.core.aggregate(b15, 60))
    signals = []
    st = defaultdict(int)
    last_signal_t = -10**18

    warm = max(ATR_SLOW + 5, LOOKBACK + 2)
    for i in range(warm, len(h1)):
        x = h1[i]
        p = h1[i - 1]
        atr = x["atr14_cet"]
        if not atr or atr <= 0:
            continue
        if x["ct"] - last_signal_t < COOLDOWN_HOURS * 3_600_000:
            continue

        # Compression is measured BEFORE the breakout candle.
        p_a14, p_a50, p_er = p["atr14_cet"], p["atr50_cet"], p["er20_cet"]
        if not p_a14 or not p_a50 or p_er is None:
            continue
        atr_ratio = p_a14 / p_a50
        if atr_ratio > COMPRESSION_ATR_RATIO_MAX or p_er > COMPRESSION_ER_MAX:
            st["compression_reject"] += 1
            continue

        prior = h1[i - LOOKBACK:i]
        hi20 = max(z["h"] for z in prior)
        lo20 = min(z["l"] for z in prior)
        vma = x["vol_sma20_cet"]
        if not vma or vma <= 0:
            continue

        body_atr = abs(x["c"] - x["o"]) / atr
        volume_mult = x["v"] / vma
        cv = clv(x)

        if (
            x["c"] > hi20 + BREAK_BUFFER_ATR * atr
            and body_atr >= BODY_MIN_ATR
            and volume_mult >= VOL_MIN_MULT
            and cv >= CLV_LONG_MIN
            and x["c"] > x["o"]
        ):
            signals.append({
                "side": "LONG", "activation": x["ct"], "signal_close": x["c"],
                "atr": atr, "stop": x["l"] - SL_BUFFER_ATR * atr,
                "hi20": hi20, "lo20": lo20, "body_atr": body_atr,
                "volume_mult": volume_mult, "clv": cv,
                "compression_atr_ratio": atr_ratio, "compression_er": p_er,
            })
            last_signal_t = x["ct"]
            st["signals_long"] += 1

        elif (
            x["c"] < lo20 - BREAK_BUFFER_ATR * atr
            and body_atr >= BODY_MIN_ATR
            and volume_mult >= VOL_MIN_MULT
            and cv <= CLV_SHORT_MAX
            and x["c"] < x["o"]
        ):
            signals.append({
                "side": "SHORT", "activation": x["ct"], "signal_close": x["c"],
                "atr": atr, "stop": x["h"] + SL_BUFFER_ATR * atr,
                "hi20": hi20, "lo20": lo20, "body_atr": body_atr,
                "volume_mult": volume_mult, "clv": cv,
                "compression_atr_ratio": atr_ratio, "compression_er": p_er,
            })
            last_signal_t = x["ct"]
            st["signals_short"] += 1

    return signals, dict(st)


def execute(sym, b15):
    signals, st = make_signals(b15)
    t15 = [x["t"] for x in b15]
    lo = int(base.core.EVAL_START.timestamp() * 1000)
    hi = int(base.core.EVAL_END.timestamp() * 1000)
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

        pnl = -base.core.cost(fill)
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
                    pnl += rem * (b["o"] - fill) - base.core.cost(b["o"], rem)
                    rem = 0; exit_t = b["ct"]; reason = "GAP_STOP"; break
                if b["l"] <= cur_stop:
                    pnl += rem * (cur_stop - fill) - base.core.cost(cur_stop, rem)
                    rem = 0; exit_t = b["ct"]; reason = "STOP"; break
                if not hit1 and (b["o"] >= tp1 or b["h"] >= tp1):
                    px = b["o"] if b["o"] >= tp1 else tp1
                    f = min(TP1_FRAC, rem)
                    pnl += f * (px - fill) - base.core.cost(px, f)
                    rem -= f; hit1 = True; cur_stop = max(cur_stop, fill)
                    if rem > 0 and b["l"] <= cur_stop:
                        pnl += rem * (cur_stop - fill) - base.core.cost(cur_stop, rem)
                        rem = 0; exit_t = b["ct"]; reason = "BE_AFTER_TP1"; break
                if rem > 0 and hit1 and (b["o"] >= tp2 or b["h"] >= tp2):
                    px = b["o"] if b["o"] >= tp2 else tp2
                    pnl += rem * (px - fill) - base.core.cost(px, rem)
                    rem = 0; hit2 = True; exit_t = b["ct"]; reason = "TP2"; break
            else:
                if b["o"] >= cur_stop:
                    pnl += rem * (fill - b["o"]) - base.core.cost(b["o"], rem)
                    rem = 0; exit_t = b["ct"]; reason = "GAP_STOP"; break
                if b["h"] >= cur_stop:
                    pnl += rem * (fill - cur_stop) - base.core.cost(cur_stop, rem)
                    rem = 0; exit_t = b["ct"]; reason = "STOP"; break
                if not hit1 and (b["o"] <= tp1 or b["l"] <= tp1):
                    px = b["o"] if b["o"] <= tp1 else tp1
                    f = min(TP1_FRAC, rem)
                    pnl += f * (fill - px) - base.core.cost(px, f)
                    rem -= f; hit1 = True; cur_stop = min(cur_stop, fill)
                    if rem > 0 and b["h"] >= cur_stop:
                        pnl += rem * (fill - cur_stop) - base.core.cost(cur_stop, rem)
                        rem = 0; exit_t = b["ct"]; reason = "BE_AFTER_TP1"; break
                if rem > 0 and hit1 and (b["o"] <= tp2 or b["l"] <= tp2):
                    px = b["o"] if b["o"] <= tp2 else tp2
                    pnl += rem * (fill - px) - base.core.cost(px, rem)
                    rem = 0; hit2 = True; exit_t = b["ct"]; reason = "TP2"; break

        if rem > 0:
            b = b15[last_i]
            px = b["c"]
            pnl += rem * ((px - fill) if side == "LONG" else (fill - px)) - base.core.cost(px, rem)
            exit_t = b["ct"]
            reason = "TIME"

        trades.append({
            "symbol": sym, "timeframe": "1H", "direction": side,
            "signal_t": s["activation"], "entry_t": b15[j]["t"], "exit_t": exit_t,
            "fill": fill, "initial_sl": stop, "tp1": tp1, "tp2": tp2,
            "risk": risk, "risk_atr": risk_atr, "r": pnl / risk,
            "reason": reason, "tp1_hit": hit1, "tp2_hit": hit2,
            "hold_hours": max(0.0, (exit_t - b15[j]["t"]) / 3_600_000),
            "body_atr": s["body_atr"], "volume_mult": s["volume_mult"],
            "signal_clv": s["clv"], "compression_atr_ratio": s["compression_atr_ratio"],
            "compression_er": s["compression_er"], "entry_gap_atr": gap,
        })
        busy_until = exit_t

    st["filled"] = len(trades)
    return trades, st


def grouped_metrics(trades, key):
    g = defaultdict(list)
    for t in trades:
        g[t[key]].append(t)
    return {k: base.core.metrics(v) for k, v in sorted(g.items())}


def main():
    alltr, details = [], {}
    for sym in SYMBOLS:
        b15 = base.core.load_15m(sym)
        ts, st = execute(sym, b15)
        alltr += ts
        details[sym] = {"metrics": base.core.metrics(ts), "stats": st}
        print("RESULT", sym, json.dumps(details[sym]), flush=True)

    years = defaultdict(list)
    for t in alltr:
        years[str(datetime.fromtimestamp(t["entry_t"] / 1000, UTC).year)].append(t)

    out = {
        "strategy": "CET v0.1 frozen baseline",
        "concept": "Compression -> Expansion Transition",
        "rules": {
            "signal_tf": "1H",
            "compression": {
                "prior_atr14_atr50_max": COMPRESSION_ATR_RATIO_MAX,
                "prior_er20_max": COMPRESSION_ER_MAX,
            },
            "breakout": {
                "lookback": LOOKBACK,
                "buffer_atr": BREAK_BUFFER_ATR,
                "body_min_atr": BODY_MIN_ATR,
                "volume_min_sma20_mult": VOL_MIN_MULT,
                "clv_long_min": CLV_LONG_MIN,
                "clv_short_max": CLV_SHORT_MAX,
            },
            "entry": "next 15m open",
            "stop": "breakout candle opposite extreme +0.15 ATR",
            "risk_atr_range": [RISK_MIN_ATR, RISK_MAX_ATR],
            "tp1": [TP1_R, TP1_FRAC],
            "tp2_r": TP2_R,
            "after_tp1": "breakeven",
            "max_hold_hours": MAX_HOLD_HOURS,
            "cooldown_hours": COOLDOWN_HOURS,
            "same_bar": "15m stop-first conservative",
        },
        "costs": {"fee_bps": base.core.FEE_BPS, "slippage_bps": base.core.SLIP_BPS},
        "summary": base.core.metrics(alltr),
        "directions": grouped_metrics(alltr, "direction"),
        "symbols": grouped_metrics(alltr, "symbol"),
        "years": {k: base.core.metrics(v) for k, v in sorted(years.items())},
        "details": details,
        "trades": alltr,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("FINAL", json.dumps({k: v for k, v in out.items() if k != "trades"}, indent=2), flush=True)


if __name__ == "__main__":
    main()
