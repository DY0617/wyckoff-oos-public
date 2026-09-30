import csv
import io
import json
import math
import statistics
import time
import urllib.error
import urllib.request
import zipfile
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/validation/trend_structure_v0_1_crypto_5y.json"
UTC = timezone.utc

SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT")
FETCH_START = datetime(2021, 1, 1, tzinfo=UTC)
EVAL_START = datetime(2021, 9, 1, tzinfo=UTC)
EVAL_END = datetime(2026, 9, 1, tzinfo=UTC)

FEE_BPS = 4.0
SLIP_BPS = 2.0
COST_BPS = FEE_BPS + SLIP_BPS

PIVOT_R = 3
PIVOT_LOOKBACK = 120
PIVOT_MIN_SPAN = 12
LINE_RMSE_ATR_MAX = 0.35
LINE_SLOPE_ATR_MIN = 0.01
LINE_SLOPE_ATR_MAX = 0.25

ENTRY_BUFFER_ATR = 0.05
ENTRY_VALID_15M = 16
RISK_MIN_ATR = 0.70
RISK_MAX_ATR = 2.80
TP1_R = 1.5
TP2_R = 2.5
MAX_HOLD_15M = 10 * 24 * 4

REG_WINDOW = 80
REG_K = 1.5
REG_SLOPE_ATR_MIN = 0.03


def month_iter(start, end):
    y, m = start.year, start.month
    while (y, m) < (end.year, end.month):
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def fetch_zip(url, attempts=5):
    last = None
    for a in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "trend-structure-v0.1/1.0"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            last = e
        except Exception as e:
            last = e
        time.sleep(min(20, 2 * a))
    raise RuntimeError(f"download failed: {url} {last!r}")


def normalize_ms(x):
    v = int(float(x))
    while v > 10_000_000_000_000:
        v //= 1000
    if v < 10_000_000_000:
        v *= 1000
    return v


def load_15m(sym):
    lo = int(FETCH_START.timestamp() * 1000)
    hi = int(EVAL_END.timestamp() * 1000)
    out = []
    for y, m in month_iter(FETCH_START, EVAL_END):
        url = (
            f"https://data.binance.vision/data/futures/um/monthly/klines/"
            f"{sym}/15m/{sym}-15m-{y:04d}-{m:02d}.zip"
        )
        raw = fetch_zip(url)
        if raw is None:
            print("MISSING", sym, y, m, flush=True)
            continue
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            txt = z.read(z.namelist()[0]).decode("utf-8-sig")
        n = 0
        for r in csv.reader(io.StringIO(txt)):
            if not r:
                continue
            try:
                t = normalize_ms(r[0])
                o, h, l, c, v = map(float, r[1:6])
            except Exception:
                continue
            if lo <= t < hi:
                out.append({"t": t, "ct": t + 15 * 60_000, "o": o, "h": h, "l": l, "c": c, "v": v})
                n += 1
        print("MONTH", sym, f"{y:04d}-{m:02d}", n, flush=True)
    dedup = {x["t"]: x for x in out}
    out = [dedup[k] for k in sorted(dedup)]
    print("LOADED", sym, len(out), flush=True)
    return out


def aggregate(base, minutes):
    ms = minutes * 60_000
    buckets = defaultdict(list)
    for x in base:
        buckets[(x["t"] // ms) * ms].append(x)
    need = minutes // 15
    out = []
    for k in sorted(buckets):
        xs = sorted(buckets[k], key=lambda z: z["t"])
        if len(xs) != need or xs[0]["t"] != k or xs[-1]["ct"] != k + ms:
            continue
        out.append(
            {
                "t": k,
                "ct": k + ms,
                "o": xs[0]["o"],
                "h": max(z["h"] for z in xs),
                "l": min(z["l"] for z in xs),
                "c": xs[-1]["c"],
                "v": sum(z["v"] for z in xs),
            }
        )
    return out


def ema_series(vals, n):
    k = 2.0 / (n + 1.0)
    e = None
    out = []
    for x in vals:
        e = x if e is None else e + k * (x - e)
        out.append(e)
    return out


def enrich(D):
    if not D:
        return D
    closes = [x["c"] for x in D]
    vols = [x["v"] for x in D]
    e20 = ema_series(closes, 20)
    e50 = ema_series(closes, 50)

    atr = None
    avg_gain = None
    avg_loss = None
    prev_close = None

    for i, x in enumerate(D):
        pc = closes[i - 1] if i else x["c"]
        tr = max(x["h"] - x["l"], abs(x["h"] - pc), abs(x["l"] - pc))
        atr = tr if atr is None else ((atr * 13.0) + tr) / 14.0

        if i == 0:
            gain = loss = 0.0
        else:
            d = closes[i] - closes[i - 1]
            gain = max(d, 0.0)
            loss = max(-d, 0.0)
        if avg_gain is None:
            avg_gain = gain
            avg_loss = loss
        else:
            avg_gain = ((avg_gain * 13.0) + gain) / 14.0
            avg_loss = ((avg_loss * 13.0) + loss) / 14.0
        if avg_loss <= 1e-12:
            rsi = 100.0 if avg_gain > 0 else 50.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))

        x["atr14"] = atr
        x["ema20"] = e20[i]
        x["ema50"] = e50[i]
        x["ema20_5ago"] = e20[i - 5] if i >= 5 else None
        x["rsi14"] = rsi
        x["vol_sma20"] = statistics.fmean(vols[i - 19 : i + 1]) if i >= 19 else None
        prev_close = x["c"]
    return D


def build_pivots(D):
    lows, highs = [], []
    for c in range(PIVOT_R, len(D) - PIVOT_R):
        win = D[c - PIVOT_R : c + PIVOT_R + 1]
        lo = D[c]["l"]
        hi = D[c]["h"]
        if lo == min(z["l"] for z in win) and sum(z["l"] == lo for z in win) == 1:
            lows.append({"idx": c, "price": lo, "known": c + PIVOT_R})
        if hi == max(z["h"] for z in win) and sum(z["h"] == hi for z in win) == 1:
            highs.append({"idx": c, "price": hi, "known": c + PIVOT_R})

    li = hi_i = 0
    last_lo = last_hi = None
    for i in range(len(D)):
        while li < len(lows) and lows[li]["known"] <= i:
            last_lo = lows[li]["price"]
            li += 1
        while hi_i < len(highs) and highs[hi_i]["known"] <= i:
            last_hi = highs[hi_i]["price"]
            hi_i += 1
        D[i]["last_pivot_low"] = last_lo
        D[i]["last_pivot_high"] = last_hi
    return lows, highs


def linreg_xy(xs, ys):
    n = len(xs)
    xm = statistics.fmean(xs)
    ym = statistics.fmean(ys)
    den = sum((x - xm) ** 2 for x in xs)
    if den <= 0:
        return None
    m = sum((x - xm) * (y - ym) for x, y in zip(xs, ys)) / den
    b = ym - m * xm
    rmse = math.sqrt(sum((y - (m * x + b)) ** 2 for x, y in zip(xs, ys)) / n)
    return m, b, rmse


def trendline(pivots, at_i, atr, mode):
    cand = [p for p in pivots if p["known"] <= at_i and 0 <= at_i - p["idx"] <= PIVOT_LOOKBACK]
    if len(cand) < 3 or atr is None or atr <= 0:
        return None
    ps = cand[-3:]
    prices = [p["price"] for p in ps]
    if mode == "rising" and not (prices[0] < prices[1] < prices[2]):
        return None
    if mode == "falling" and not (prices[0] > prices[1] > prices[2]):
        return None
    span = ps[-1]["idx"] - ps[0]["idx"]
    if span < PIVOT_MIN_SPAN:
        return None
    fit = linreg_xy([p["idx"] for p in ps], prices)
    if fit is None:
        return None
    m, b, rmse = fit
    norm = abs(m) / atr
    if rmse > LINE_RMSE_ATR_MAX * atr:
        return None
    if not (LINE_SLOPE_ATR_MIN <= norm <= LINE_SLOPE_ATR_MAX):
        return None
    if mode == "rising" and m <= 0:
        return None
    if mode == "falling" and m >= 0:
        return None
    score = (
        50.0
        + 25.0 * min(1.0, span / 48.0)
        + 25.0 * max(0.0, 1.0 - rmse / (LINE_RMSE_ATR_MAX * atr))
    )
    return {"m": m, "b": b, "rmse": rmse, "score": score, "pivots": ps}


def line_value(line, idx):
    return line["m"] * idx + line["b"]


def regime4(x):
    if x is None or x.get("ema20_5ago") is None:
        return None
    if x["c"] > x["ema50"] and x["ema20"] > x["ema50"] and x["ema20"] > x["ema20_5ago"]:
        return "LONG"
    if x["c"] < x["ema50"] and x["ema20"] < x["ema50"] and x["ema20"] < x["ema20_5ago"]:
        return "SHORT"
    return None


def regression_channel(h1, i):
    if i + 1 < REG_WINDOW:
        return None
    ys = [z["c"] for z in h1[i - REG_WINDOW + 1 : i + 1]]
    xs = list(range(REG_WINDOW))
    fit = linreg_xy(xs, ys)
    if fit is None:
        return None
    m, b, _ = fit
    pred = [m * x + b for x in xs]
    resid = [y - p for y, p in zip(ys, pred)]
    sd = math.sqrt(sum(r * r for r in resid) / len(resid))
    center = pred[-1]
    return {"slope": m, "center": center, "lower": center - REG_K * sd, "upper": center + REG_K * sd, "sd": sd}


def find_breakout_retest(h1, pivots, i, side):
    A = h1[i]["atr14"]
    if A is None or A <= 0:
        return None
    start = max(1, i - 8)
    for j in range(i - 1, start - 1, -1):
        Aj = h1[j]["atr14"]
        vma = h1[j].get("vol_sma20")
        if Aj is None or Aj <= 0 or vma is None or vma <= 0:
            continue
        if side == "LONG":
            ln = trendline(pivots, j, Aj, "falling")
            if ln is None:
                continue
            prev_ln = line_value(ln, j - 1)
            now_ln = line_value(ln, j)
            broke = h1[j - 1]["c"] <= prev_ln and h1[j]["c"] > now_ln + 0.10 * Aj
            vol_ok = h1[j]["v"] >= 1.20 * vma
            if not (broke and vol_ok):
                continue
            cur_ln = line_value(ln, i)
            retest = h1[i]["l"] <= cur_ln + 0.35 * A and h1[i]["c"] > cur_ln and h1[i]["rsi14"] >= 50.0
            if retest:
                return {"line": ln, "line_now": cur_ln, "breakout_i": j}
        else:
            ln = trendline(pivots, j, Aj, "rising")
            if ln is None:
                continue
            prev_ln = line_value(ln, j - 1)
            now_ln = line_value(ln, j)
            broke = h1[j - 1]["c"] >= prev_ln and h1[j]["c"] < now_ln - 0.10 * Aj
            vol_ok = h1[j]["v"] >= 1.20 * vma
            if not (broke and vol_ok):
                continue
            cur_ln = line_value(ln, i)
            retest = h1[i]["h"] >= cur_ln - 0.35 * A and h1[i]["c"] < cur_ln and h1[i]["rsi14"] <= 50.0
            if retest:
                return {"line": ln, "line_now": cur_ln, "breakout_i": j}
    return None


def make_signal(h1, h4, ct4, low_pivots, high_pivots, i):
    x = h1[i]
    if i < max(REG_WINDOW - 1, 55):
        return None
    k4 = bisect_left(ct4, x["ct"] + 1) - 1
    if k4 < 0:
        return None
    side = regime4(h4[k4])
    if side is None:
        return None

    A = x["atr14"]
    vma = x.get("vol_sma20")
    if A is None or A <= 0 or vma is None or vma <= 0:
        return None

    tracks = []

    # Track A: pivot trendline pullback
    if side == "LONG" and x["ema20"] > x["ema50"]:
        ln = trendline(low_pivots, i, A, "rising")
        if ln is not None:
            lv = line_value(ln, i)
            if x["l"] <= lv + 0.35 * A and x["c"] >= lv - 0.10 * A and x["rsi14"] >= 45.0 and x["v"] >= 0.80 * vma:
                entry = x["h"] + ENTRY_BUFFER_ATR * A
                lp = x.get("last_pivot_low")
                bases = [lv - 0.40 * A]
                if lp is not None:
                    bases.append(lp - 0.20 * A)
                sl = min(bases)
                tracks.append(("A_PULLBACK", entry, sl, {"line": lv, "line_score": ln["score"]}))
    elif side == "SHORT" and x["ema20"] < x["ema50"]:
        ln = trendline(high_pivots, i, A, "falling")
        if ln is not None:
            lv = line_value(ln, i)
            if x["h"] >= lv - 0.35 * A and x["c"] <= lv + 0.10 * A and x["rsi14"] <= 55.0 and x["v"] >= 0.80 * vma:
                entry = x["l"] - ENTRY_BUFFER_ATR * A
                hp = x.get("last_pivot_high")
                bases = [lv + 0.40 * A]
                if hp is not None:
                    bases.append(hp + 0.20 * A)
                sl = max(bases)
                tracks.append(("A_PULLBACK", entry, sl, {"line": lv, "line_score": ln["score"]}))

    # Track B: trendline breakout + retest
    if side == "LONG":
        br = find_breakout_retest(h1, high_pivots, i, "LONG")
        if br is not None:
            entry = x["h"] + ENTRY_BUFFER_ATR * A
            lp = x.get("last_pivot_low")
            bases = [br["line_now"] - 0.40 * A, x["l"] - 0.20 * A]
            if lp is not None:
                bases.append(lp - 0.20 * A)
            sl = min(bases)
            tracks.append(("B_BREAK_RETEST", entry, sl, {"line": br["line_now"], "breakout_i": br["breakout_i"]}))
    else:
        br = find_breakout_retest(h1, low_pivots, i, "SHORT")
        if br is not None:
            entry = x["l"] - ENTRY_BUFFER_ATR * A
            hp = x.get("last_pivot_high")
            bases = [br["line_now"] + 0.40 * A, x["h"] + 0.20 * A]
            if hp is not None:
                bases.append(hp + 0.20 * A)
            sl = max(bases)
            tracks.append(("B_BREAK_RETEST", entry, sl, {"line": br["line_now"], "breakout_i": br["breakout_i"]}))

    # Track C: regression channel pullback
    reg = regression_channel(h1, i)
    if reg is not None and abs(reg["slope"]) / A >= REG_SLOPE_ATR_MIN:
        if side == "LONG" and x["ema20"] > x["ema50"] and reg["slope"] > 0:
            if x["l"] <= reg["lower"] + 0.20 * A and x["c"] > reg["lower"] and x["rsi14"] >= 42.0:
                entry = x["h"] + ENTRY_BUFFER_ATR * A
                lp = x.get("last_pivot_low")
                bases = [reg["lower"] - 0.50 * A]
                if lp is not None:
                    bases.append(lp - 0.20 * A)
                sl = min(bases)
                tracks.append(("C_REG_PULLBACK", entry, sl, {"reg_lower": reg["lower"], "reg_slope_atr": reg["slope"] / A}))
        elif side == "SHORT" and x["ema20"] < x["ema50"] and reg["slope"] < 0:
            if x["h"] >= reg["upper"] - 0.20 * A and x["c"] < reg["upper"] and x["rsi14"] <= 58.0:
                entry = x["l"] - ENTRY_BUFFER_ATR * A
                hp = x.get("last_pivot_high")
                bases = [reg["upper"] + 0.50 * A]
                if hp is not None:
                    bases.append(hp + 0.20 * A)
                sl = max(bases)
                tracks.append(("C_REG_PULLBACK", entry, sl, {"reg_upper": reg["upper"], "reg_slope_atr": reg["slope"] / A}))

    if not tracks:
        return None

    priority = {"A_PULLBACK": 0, "B_BREAK_RETEST": 1, "C_REG_PULLBACK": 2}
    tracks.sort(key=lambda z: priority[z[0]])
    track, entry, sl, meta = tracks[0]
    risk = (entry - sl) if side == "LONG" else (sl - entry)
    if risk <= 0:
        return None
    risk_atr = risk / A
    if not (RISK_MIN_ATR <= risk_atr <= RISK_MAX_ATR):
        return {"rejected": "risk", "track": track, "risk_atr": risk_atr}

    tp1 = entry + TP1_R * risk if side == "LONG" else entry - TP1_R * risk
    tp2 = entry + TP2_R * risk if side == "LONG" else entry - TP2_R * risk
    return {
        "rejected": None,
        "track": track,
        "side": side,
        "entry": entry,
        "sl": sl,
        "risk": risk,
        "risk_atr": risk_atr,
        "tp1": tp1,
        "tp2": tp2,
        "meta": meta,
    }


def cost(px, frac=1.0):
    return frac * px * COST_BPS / 10000.0


def metrics(ts):
    o = sorted(ts, key=lambda z: (z["exit_t"], z["symbol"], z["track"]))
    rs = [x["r"] for x in o]
    pos = [r for r in rs if r > 0]
    neg = [r for r in rs if r < 0]
    eq = peak = 0.0
    dd = 0.0
    cur = mx = 0
    for r in rs:
        eq += r
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
        if r < 0:
            cur += 1
            mx = max(mx, cur)
        else:
            cur = 0
    holds = [x["hold_hours"] for x in o]
    return {
        "trades": len(o),
        "long": sum(x["direction"] == "LONG" for x in o),
        "short": sum(x["direction"] == "SHORT" for x in o),
        "wins": len(pos),
        "losses": len(neg),
        "win_rate": len(pos) / len(o) if o else None,
        "total_r": sum(rs),
        "avg_r": statistics.fmean(rs) if rs else None,
        "profit_factor": sum(pos) / abs(sum(neg)) if neg else None,
        "max_drawdown_r": dd,
        "max_losing_streak": mx,
        "tp1_hit_rate": sum(x["tp1_hit"] for x in o) / len(o) if o else None,
        "tp2_hit_rate": sum(x["tp2_hit"] for x in o) / len(o) if o else None,
        "runner_activation_rate": sum(x["runner_activated"] for x in o) / len(o) if o else None,
        "avg_hold_hours": statistics.fmean(holds) if holds else None,
        "median_hold_hours": statistics.median(holds) if holds else None,
    }


def simulate_symbol(sym, b15, h1_override=None, h4_override=None, eval_start=None, eval_end=None):
    q15 = [dict(x) for x in b15]
    h1 = enrich(h1_override if h1_override is not None else aggregate(b15, 60))
    h4 = enrich(h4_override if h4_override is not None else aggregate(b15, 240))
    low_pivots, high_pivots = build_pivots(h1)
    t15 = [x["t"] for x in q15]
    ct1 = [x["ct"] for x in h1]
    ct4 = [x["ct"] for x in h4]

    eval_start = eval_start or EVAL_START
    eval_end = eval_end or EVAL_END
    lo = int(eval_start.timestamp() * 1000)
    hi = int(eval_end.timestamp() * 1000)
    trades = []
    st = defaultdict(int)
    busy_until = -1

    for i, x in enumerate(h1):
        if x["ct"] < lo or x["ct"] >= hi:
            continue
        if x["ct"] < busy_until:
            st["signal_while_busy"] += 1
            continue

        sig = make_signal(h1, h4, ct4, low_pivots, high_pivots, i)
        if sig is None:
            continue
        st["raw_signals"] += 1
        st[f"raw_{sig.get('track', 'UNKNOWN')}"] += 1
        if sig.get("rejected"):
            st["risk_rejected"] += 1
            continue

        side = sig["side"]
        entry = sig["entry"]
        sl = sig["sl"]
        risk = sig["risk"]
        tp1 = sig["tp1"]
        tp2 = sig["tp2"]
        track = sig["track"]
        st["valid_orders"] += 1
        st[f"valid_{track}"] += 1

        pstart = bisect_left(t15, x["ct"])
        fill_idx = None
        fill_px = None
        for j in range(pstart, min(pstart + ENTRY_VALID_15M, len(q15))):
            b = q15[j]
            if b["t"] >= hi:
                break
            if side == "LONG":
                if b["o"] >= entry:
                    fill_idx, fill_px = j, b["o"]
                    break
                if b["h"] >= entry:
                    fill_idx, fill_px = j, entry
                    break
            else:
                if b["o"] <= entry:
                    fill_idx, fill_px = j, b["o"]
                    break
                if b["l"] <= entry:
                    fill_idx, fill_px = j, entry
                    break

        expiry = x["ct"] + ENTRY_VALID_15M * 15 * 60_000
        if fill_idx is None:
            st["entry_expired"] += 1
            st[f"expired_{track}"] += 1
            busy_until = expiry
            continue

        st["filled"] += 1
        st[f"filled_{track}"] += 1

        pnl = -cost(fill_px, 1.0)
        remaining = 1.0
        tp1_hit = False
        tp2_hit = False
        runner_activated = False
        dyn_stop = sl
        exit_t = q15[fill_idx]["ct"]
        exit_px = fill_px
        reason = "TIME"
        last_idx = min(fill_idx + MAX_HOLD_15M - 1, len(q15) - 1)

        for j in range(fill_idx, last_idx + 1):
            b = q15[j]
            if b["t"] >= hi:
                last_idx = j
                break

            if runner_activated:
                k1 = bisect_left(ct1, b["t"] + 1) - 1
                if k1 >= 0:
                    z = h1[k1]
                    A1 = z["atr14"]
                    if A1 is not None and A1 > 0:
                        if side == "LONG":
                            cands = [fill_px, z["ema20"] - 0.20 * A1]
                            if z.get("last_pivot_low") is not None:
                                cands.append(z["last_pivot_low"] - 0.20 * A1)
                            dyn_stop = max(dyn_stop, max(cands))
                        else:
                            cands = [fill_px, z["ema20"] + 0.20 * A1]
                            if z.get("last_pivot_high") is not None:
                                cands.append(z["last_pivot_high"] + 0.20 * A1)
                            dyn_stop = min(dyn_stop, min(cands))

            # Stop first: conservative intrabar convention.
            if side == "LONG":
                if b["o"] <= dyn_stop:
                    pnl += remaining * (b["o"] - fill_px) - cost(b["o"], remaining)
                    exit_px, exit_t, reason, remaining = b["o"], b["ct"], "GAP_STOP", 0.0
                    break
                if b["l"] <= dyn_stop:
                    pnl += remaining * (dyn_stop - fill_px) - cost(dyn_stop, remaining)
                    exit_px, exit_t, reason, remaining = dyn_stop, b["ct"], "STOP", 0.0
                    break

                if not tp1_hit:
                    px1 = b["o"] if b["o"] >= tp1 else (tp1 if b["h"] >= tp1 else None)
                    if px1 is not None:
                        frac = min(0.20, remaining)
                        pnl += frac * (px1 - fill_px) - cost(px1, frac)
                        remaining -= frac
                        tp1_hit = True
                        dyn_stop = max(dyn_stop, fill_px)
                        # Conservative same-bar BE check after TP1 activation.
                        if remaining > 0 and b["l"] <= dyn_stop:
                            pnl += remaining * (dyn_stop - fill_px) - cost(dyn_stop, remaining)
                            exit_px, exit_t, reason, remaining = dyn_stop, b["ct"], "BE_AFTER_TP1", 0.0
                            break

                if remaining > 0 and tp1_hit and not tp2_hit:
                    px2 = b["o"] if b["o"] >= tp2 else (tp2 if b["h"] >= tp2 else None)
                    if px2 is not None:
                        frac = min(0.20, remaining)
                        pnl += frac * (px2 - fill_px) - cost(px2, frac)
                        remaining -= frac
                        tp2_hit = True
                        runner_activated = remaining > 0

            else:
                if b["o"] >= dyn_stop:
                    pnl += remaining * (fill_px - b["o"]) - cost(b["o"], remaining)
                    exit_px, exit_t, reason, remaining = b["o"], b["ct"], "GAP_STOP", 0.0
                    break
                if b["h"] >= dyn_stop:
                    pnl += remaining * (fill_px - dyn_stop) - cost(dyn_stop, remaining)
                    exit_px, exit_t, reason, remaining = dyn_stop, b["ct"], "STOP", 0.0
                    break

                if not tp1_hit:
                    px1 = b["o"] if b["o"] <= tp1 else (tp1 if b["l"] <= tp1 else None)
                    if px1 is not None:
                        frac = min(0.20, remaining)
                        pnl += frac * (fill_px - px1) - cost(px1, frac)
                        remaining -= frac
                        tp1_hit = True
                        dyn_stop = min(dyn_stop, fill_px)
                        if remaining > 0 and b["h"] >= dyn_stop:
                            pnl += remaining * (fill_px - dyn_stop) - cost(dyn_stop, remaining)
                            exit_px, exit_t, reason, remaining = dyn_stop, b["ct"], "BE_AFTER_TP1", 0.0
                            break

                if remaining > 0 and tp1_hit and not tp2_hit:
                    px2 = b["o"] if b["o"] <= tp2 else (tp2 if b["l"] <= tp2 else None)
                    if px2 is not None:
                        frac = min(0.20, remaining)
                        pnl += frac * (fill_px - px2) - cost(px2, frac)
                        remaining -= frac
                        tp2_hit = True
                        runner_activated = remaining > 0

            if j == last_idx and remaining > 0:
                px = b["c"]
                pnl += remaining * ((px - fill_px) if side == "LONG" else (fill_px - px)) - cost(px, remaining)
                exit_px, exit_t, reason, remaining = px, b["ct"], "TIME", 0.0
                break

        if remaining > 0:
            b = q15[last_idx]
            px = b["c"]
            pnl += remaining * ((px - fill_px) if side == "LONG" else (fill_px - px)) - cost(px, remaining)
            exit_px, exit_t, reason, remaining = px, b["ct"], "END", 0.0

        trades.append(
            {
                "symbol": sym,
                "track": track,
                "direction": side,
                "signal_t": x["ct"],
                "entry_t": q15[fill_idx]["t"],
                "exit_t": exit_t,
                "entry": entry,
                "fill": fill_px,
                "initial_sl": sl,
                "tp1": tp1,
                "tp2": tp2,
                "planned_risk": risk,
                "risk_atr": sig["risk_atr"],
                "r": pnl / risk,
                "reason": reason,
                "tp1_hit": tp1_hit,
                "tp2_hit": tp2_hit,
                "runner_activated": runner_activated,
                "hold_hours": max(0.0, (exit_t - q15[fill_idx]["t"]) / 3_600_000),
                "meta": sig["meta"],
            }
        )
        busy_until = exit_t

    st = dict(st)
    st["entry_fill_rate"] = st.get("filled", 0) / st.get("valid_orders", 1) if st.get("valid_orders", 0) else None
    st["risk_reject_rate"] = st.get("risk_rejected", 0) / st.get("raw_signals", 1) if st.get("raw_signals", 0) else None
    return trades, st


def main():
    alltr = []
    symbols = {}
    for sym in SYMBOLS:
        b15 = load_15m(sym)
        ts, st = simulate_symbol(sym, b15)
        symbols[sym] = {"metrics": metrics(ts), "stats": st}
        alltr += ts
        print("RESULT", sym, json.dumps(symbols[sym]), flush=True)

    by_track = defaultdict(list)
    by_direction = defaultdict(list)
    by_year = defaultdict(list)
    for t in alltr:
        by_track[t["track"]].append(t)
        by_direction[t["direction"]].append(t)
        year = str(datetime.fromtimestamp(t["entry_t"] / 1000, UTC).year)
        by_year[year].append(t)

    out = {
        "strategy": "Trend Structure v0.1 frozen",
        "asset_class": "Binance USDT-M perpetual",
        "period": {
            "fetch_start": FETCH_START.isoformat(),
            "eval_start": EVAL_START.isoformat(),
            "eval_end_exclusive": EVAL_END.isoformat(),
        },
        "costs": {"fee_bps": FEE_BPS, "slippage_bps": SLIP_BPS},
        "summary": metrics(alltr),
        "tracks": {k: metrics(v) for k, v in sorted(by_track.items())},
        "directions": {k: metrics(v) for k, v in sorted(by_direction.items())},
        "years": {k: metrics(v) for k, v in sorted(by_year.items())},
        "symbols": symbols,
        "trades": alltr,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("FINAL", json.dumps({k: v for k, v in out.items() if k != "trades"}, indent=2), flush=True)


if __name__ == "__main__":
    main()
