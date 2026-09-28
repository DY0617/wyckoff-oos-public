import bisect
import csv
import io
import json
import math
import os
import statistics
import time
import urllib.request
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

UTC = timezone.utc
VISION = "https://data.binance.vision/data/futures/um"
SYMBOLS = ("BTCUSDT", "ETHUSDT")
HOUR_MS = 60 * 60 * 1000

# LDFR v0.2 -- frozen before first test.
EVAL_START = datetime(2021, 9, 28, tzinfo=UTC)
EVAL_END = datetime(2026, 9, 28, tzinfo=UTC)
WARMUP_START = datetime(2021, 6, 1, tzinfo=UTC)
TRAIN_END = datetime(2024, 9, 28, tzinfo=UTC)
VALID_END = datetime(2025, 9, 28, tzinfo=UTC)

SWEEP_LOOKBACK = 20
DISPLACEMENT_WINDOW = 3
DISPLACEMENT_ATR = 1.50
DISPLACEMENT_BODY_FRAC = 0.60
DISPLACEMENT_CLV_LONG = 0.75
DISPLACEMENT_CLV_SHORT = 0.25
FVG_MIN_ATR = 0.15
RETEST_WINDOW = 8
CONFIRM_WINDOW = 2
STOP_PAD_ATR = 0.15
TP1_R = 1.50
TP2_R = 3.00
TP1_FRACTION = 0.50
FEE_BPS = 4.0
SLIPPAGE_BPS = 2.0
COST_BPS = FEE_BPS + SLIPPAGE_BPS
OUT = Path(os.environ.get("OUT", "data/validation/ldfr_v0_2_crypto_5y.json"))


def ms(dt):
    return int(dt.timestamp() * 1000)


def norm_ts(x):
    v = int(x)
    return v // 1000 if v > 100_000_000_000_000 else v


def month_iter(start_dt, end_dt):
    y, m = start_dt.year, start_dt.month
    while (y, m) <= (end_dt.year, end_dt.month):
        yield y, m
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1


def download_zip_rows(url, required=True):
    last_err = None
    for attempt in range(6):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ldfr-backtest/0.1"})
            with urllib.request.urlopen(req, timeout=45) as r:
                raw = r.read()
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                names = zf.namelist()
                if not names:
                    raise RuntimeError("empty zip")
                text = zf.read(names[0]).decode("utf-8")
            rows = []
            for row in csv.reader(io.StringIO(text)):
                if not row or not row[0].lstrip("-").isdigit():
                    continue
                ot = norm_ts(row[0])
                ct = norm_ts(row[6])
                rows.append({
                    "t": ot,
                    "ct": ct,
                    "o": float(row[1]),
                    "h": float(row[2]),
                    "l": float(row[3]),
                    "c": float(row[4]),
                    "v": float(row[5]),
                })
            return rows
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 404 and not required:
                return []
            time.sleep(min(15, 2 + attempt * 2))
        except Exception as e:
            last_err = e
            time.sleep(min(15, 2 + attempt * 2))
    if required:
        raise RuntimeError(f"Binance Vision download failed: {url}: {last_err!r}")
    return []


def fetch_vision_1h(symbol, start_dt, end_dt):
    rows = []
    # Completed months through the month before EVAL_END.
    last_full_month = datetime(end_dt.year, end_dt.month, 1, tzinfo=UTC)
    for y, m in month_iter(start_dt, last_full_month):
        month_start = datetime(y, m, 1, tzinfo=UTC)
        if month_start >= last_full_month:
            break
        url = f"{VISION}/monthly/klines/{symbol}/1h/{symbol}-1h-{y:04d}-{m:02d}.zip"
        part = download_zip_rows(url, required=True)
        print("VISION_MONTH", symbol, f"{y:04d}-{m:02d}", len(part), flush=True)
        rows.extend(part)

    # Current partial month: daily archives up to end_dt-1 day.
    cur = last_full_month
    while cur < end_dt:
        nxt = cur.timestamp() + 24 * 60 * 60
        if nxt > end_dt.timestamp():
            break
        url = f"{VISION}/daily/klines/{symbol}/1h/{symbol}-1h-{cur:%Y-%m-%d}.zip"
        part = download_zip_rows(url, required=False)
        if not part:
            print("VISION_DAY_NOT_YET_PUBLISHED", symbol, cur.strftime("%Y-%m-%d"), flush=True)
            break
        print("VISION_DAY", symbol, cur.strftime("%Y-%m-%d"), len(part), flush=True)
        rows.extend(part)
        cur = datetime.fromtimestamp(nxt, UTC)

    lo, hi = ms(start_dt), ms(end_dt)
    dedup = {x["t"]: x for x in rows if lo <= x["t"] < hi}
    out = [dedup[k] for k in sorted(dedup)]
    if not out:
        raise RuntimeError(f"No Binance Vision rows for {symbol}")
    return out


def aggregate_4h(h1):
    groups = defaultdict(list)
    for x in h1:
        bucket = (x["t"] // (4 * HOUR_MS)) * (4 * HOUR_MS)
        groups[bucket].append(x)
    out = []
    for t in sorted(groups):
        a = sorted(groups[t], key=lambda z: z["t"])
        if len(a) != 4 or any(a[i]["t"] != t + i * HOUR_MS for i in range(4)):
            continue
        out.append({
            "t": t,
            "ct": a[-1]["ct"],
            "o": a[0]["o"],
            "h": max(z["h"] for z in a),
            "l": min(z["l"] for z in a),
            "c": a[-1]["c"],
            "v": sum(z["v"] for z in a),
        })
    return out


def ema(values, n):
    k = 2.0 / (n + 1.0)
    out = []
    e = None
    for x in values:
        e = x if e is None else e + k * (x - e)
        out.append(e)
    return out


def enrich_1h(bars):
    if not bars:
        return bars
    prev = None
    atr = None
    for x in bars:
        pc = x["c"] if prev is None else prev
        tr = max(x["h"] - x["l"], abs(x["h"] - pc), abs(x["l"] - pc))
        atr = tr if atr is None else ((atr * 13.0) + tr) / 14.0
        x["atr"] = atr
        rng = x["h"] - x["l"]
        x["spread"] = rng
        x["body"] = abs(x["c"] - x["o"])
        x["body_frac"] = x["body"] / rng if rng > 0 else 0.0
        x["clv"] = (x["c"] - x["l"]) / rng if rng > 0 else 0.5
        prev = x["c"]
    return bars


def enrich_4h(bars):
    if not bars:
        return bars
    cs = [x["c"] for x in bars]
    e20 = ema(cs, 20)
    e50 = ema(cs, 50)
    for i, x in enumerate(bars):
        x["ema20"] = e20[i]
        x["ema50"] = e50[i]
        x["ema20_slope5"] = (e20[i] - e20[i - 5]) / 5.0 if i >= 5 else None
    return bars


def regime(h4, h4_closes, asof_ct, direction):
    j = bisect.bisect_right(h4_closes, asof_ct) - 1
    if j < 50:
        return False, None
    x = h4[j]
    slope = x.get("ema20_slope5")
    if slope is None:
        return False, j
    if direction == "LONG":
        ok = x["c"] > x["ema50"] and x["ema20"] > x["ema50"] and slope > 0
    else:
        ok = x["c"] < x["ema50"] and x["ema20"] < x["ema50"] and slope < 0
    return ok, j


def displacement_ok(x, direction):
    if not x.get("atr") or x["atr"] <= 0:
        return False
    if x["spread"] < DISPLACEMENT_ATR * x["atr"]:
        return False
    if x["body_frac"] < DISPLACEMENT_BODY_FRAC:
        return False
    if direction == "LONG":
        return x["c"] > x["o"] and x["clv"] >= DISPLACEMENT_CLV_LONG
    return x["c"] < x["o"] and x["clv"] <= DISPLACEMENT_CLV_SHORT


def fvg_for(bars, i, direction):
    if i < 2:
        return None
    a, c = bars[i - 2], bars[i]
    atr = c.get("atr") or 0.0
    if atr <= 0:
        return None
    if direction == "LONG":
        low, high = a["h"], c["l"]
        if high <= low:
            return None
    else:
        low, high = c["h"], a["l"]
        if high <= low:
            return None
    size = high - low
    if size < FVG_MIN_ATR * atr:
        return None
    return {"low": low, "high": high, "mid": (low + high) / 2.0, "size": size}


FVG_AFTER_DISPLACEMENT_BARS = 2


def build_setups(symbol, h1, h4):
    h4_closes = [x["ct"] for x in h4]
    setups = []
    used_confirmation = set()
    start_i = max(SWEEP_LOOKBACK, 60)
    for i in range(start_i, len(h1) - 2):
        s = h1[i]
        if s["ct"] < ms(EVAL_START) or s["ct"] >= ms(EVAL_END):
            continue
        prev = h1[i - SWEEP_LOOKBACK:i]
        prev_low = min(x["l"] for x in prev)
        prev_high = max(x["h"] for x in prev)
        candidates = []
        if s["l"] < prev_low and s["c"] > prev_low:
            candidates.append(("LONG", prev_low))
        if s["h"] > prev_high and s["c"] < prev_high:
            candidates.append(("SHORT", prev_high))
        if not candidates:
            continue

        for direction, swept_level in candidates:
            reg_ok, _ = regime(h4, h4_closes, s["ct"], direction)
            if not reg_ok:
                continue

            disp_i = None
            fvg_i = None
            fvg = None
            for j in range(i, min(len(h1), i + DISPLACEMENT_WINDOW + 1)):
                if not displacement_ok(h1[j], direction):
                    continue
                disp_i = j
                for g in range(j, min(len(h1), j + FVG_AFTER_DISPLACEMENT_BARS + 1)):
                    gap = fvg_for(h1, g, direction)
                    if gap is not None:
                        fvg_i, fvg = g, gap
                        break
                if fvg is not None:
                    break
            if disp_i is None or fvg_i is None:
                continue

            retest_i = None
            for k in range(fvg_i + 1, min(len(h1), fvg_i + RETEST_WINDOW + 1)):
                q = h1[k]
                touched = q["l"] <= fvg["mid"] <= q["h"]
                valid = q["c"] > fvg["low"] if direction == "LONG" else q["c"] < fvg["high"]
                if touched and valid:
                    retest_i = k
                    break
            if retest_i is None:
                continue

            conf_i = None
            for k in range(retest_i, min(len(h1) - 1, retest_i + CONFIRM_WINDOW + 1)):
                q, p = h1[k], h1[k - 1]
                ok = q["c"] > p["h"] if direction == "LONG" else q["c"] < p["l"]
                if ok:
                    conf_i = k
                    break
            if conf_i is None or conf_i in used_confirmation:
                continue

            reg2, _ = regime(h4, h4_closes, h1[conf_i]["ct"], direction)
            if not reg2:
                continue

            atr = h1[conf_i].get("atr") or 0.0
            if atr <= 0:
                continue
            stop = (s["l"] - STOP_PAD_ATR * atr) if direction == "LONG" else (s["h"] + STOP_PAD_ATR * atr)
            used_confirmation.add(conf_i)
            setups.append({
                "symbol": symbol,
                "direction": direction,
                "sweep_i": i,
                "sweep_t": s["t"],
                "swept_level": swept_level,
                "displacement_i": disp_i,
                "displacement_t": h1[disp_i]["t"],
                "fvg_i": fvg_i,
                "fvg_t": h1[fvg_i]["t"],
                "fvg": fvg,
                "retest_i": retest_i,
                "retest_t": h1[retest_i]["t"],
                "confirmation_i": conf_i,
                "confirmation_t": h1[conf_i]["t"],
                "stop_raw": stop,
            })
    setups.sort(key=lambda x: x["confirmation_t"])
    return setups


def diagnostic_funnel(h1, h4):
    h4_closes = [x["ct"] for x in h4]
    keys = ("sweep", "regime", "displacement", "fvg", "retest", "confirmation", "final_regime")
    out = {"TOTAL": {k: 0 for k in keys}, "LONG": {k: 0 for k in keys}, "SHORT": {k: 0 for k in keys}}

    def inc(direction, key):
        out["TOTAL"][key] += 1
        out[direction][key] += 1

    start_i = max(SWEEP_LOOKBACK, 60)
    for i in range(start_i, len(h1) - 2):
        bar = h1[i]
        if bar["ct"] < ms(EVAL_START) or bar["ct"] >= ms(EVAL_END):
            continue
        prev = h1[i - SWEEP_LOOKBACK:i]
        prev_low = min(x["l"] for x in prev)
        prev_high = max(x["h"] for x in prev)
        candidates = []
        if bar["l"] < prev_low and bar["c"] > prev_low:
            candidates.append("LONG")
        if bar["h"] > prev_high and bar["c"] < prev_high:
            candidates.append("SHORT")

        for direction in candidates:
            inc(direction, "sweep")
            reg_ok, _ = regime(h4, h4_closes, bar["ct"], direction)
            if not reg_ok:
                continue
            inc(direction, "regime")

            any_disp = False
            disp_i = None
            fvg_i = None
            gap = None
            for j in range(i, min(len(h1), i + DISPLACEMENT_WINDOW + 1)):
                if not displacement_ok(h1[j], direction):
                    continue
                any_disp = True
                if disp_i is None:
                    disp_i = j
                for gidx in range(j, min(len(h1), j + FVG_AFTER_DISPLACEMENT_BARS + 1)):
                    g = fvg_for(h1, gidx, direction)
                    if g is not None:
                        fvg_i, gap = gidx, g
                        break
                if gap is not None:
                    break
            if not any_disp:
                continue
            inc(direction, "displacement")
            if fvg_i is None:
                continue
            inc(direction, "fvg")

            retest_i = None
            for k in range(fvg_i + 1, min(len(h1), fvg_i + RETEST_WINDOW + 1)):
                q = h1[k]
                touched = q["l"] <= gap["mid"] <= q["h"]
                valid = q["c"] > gap["low"] if direction == "LONG" else q["c"] < gap["high"]
                if touched and valid:
                    retest_i = k
                    break
            if retest_i is None:
                continue
            inc(direction, "retest")

            conf_i = None
            for k in range(retest_i, min(len(h1) - 1, retest_i + CONFIRM_WINDOW + 1)):
                q, p = h1[k], h1[k - 1]
                ok = q["c"] > p["h"] if direction == "LONG" else q["c"] < p["l"]
                if ok:
                    conf_i = k
                    break
            if conf_i is None:
                continue
            inc(direction, "confirmation")

            reg2, _ = regime(h4, h4_closes, h1[conf_i]["ct"], direction)
            if reg2:
                inc(direction, "final_regime")
    return out


def fill_cost(notional):
    return notional * COST_BPS / 10000.0


def simulate_symbol(symbol, h1, setups):
    trades = []
    busy_until_i = -1
    for s in setups:
        ci = s["confirmation_i"]
        if ci <= busy_until_i or ci + 1 >= len(h1):
            continue
        entry_i = ci + 1
        eb = h1[entry_i]
        if eb["t"] >= ms(EVAL_END):
            continue
        direction = s["direction"]
        sign = 1.0 if direction == "LONG" else -1.0
        raw_entry = eb["o"]
        entry = raw_entry * (1.0 + sign * SLIPPAGE_BPS / 10000.0)
        stop = s["stop_raw"]
        if (direction == "LONG" and entry <= stop) or (direction == "SHORT" and entry >= stop):
            continue
        risk = abs(entry - stop)
        if risk <= 0:
            continue
        size = 1.0 / risk
        tp1 = entry + sign * TP1_R * risk
        tp2 = entry + sign * TP2_R * risk
        realized = -fill_cost(size * entry)
        remaining = 1.0
        tp1_done = False
        stop_now = stop
        events = []
        exit_i = entry_i
        reason = "OPEN_MARK"

        for j in range(entry_i, len(h1)):
            b = h1[j]
            if b["t"] >= ms(EVAL_END):
                break
            exit_i = j
            hit_stop = b["l"] <= stop_now if direction == "LONG" else b["h"] >= stop_now
            if hit_stop:
                realized += remaining * sign * (stop_now - entry) * size
                realized -= fill_cost(remaining * size * stop_now)
                events.append({"type": "BE" if abs(stop_now - entry) < 1e-12 else "STOP", "t": b["t"], "price": stop_now, "fraction": remaining})
                remaining = 0.0
                reason = events[-1]["type"]
                break

            hit_tp1 = b["h"] >= tp1 if direction == "LONG" else b["l"] <= tp1
            hit_tp2 = b["h"] >= tp2 if direction == "LONG" else b["l"] <= tp2

            if not tp1_done and hit_tp1:
                frac = min(TP1_FRACTION, remaining)
                realized += frac * sign * (tp1 - entry) * size
                realized -= fill_cost(frac * size * tp1)
                remaining -= frac
                tp1_done = True
                events.append({"type": "TP1", "t": b["t"], "price": tp1, "fraction": frac})
                stop_now = entry

            if tp1_done and remaining > 0 and hit_tp2:
                frac = remaining
                realized += frac * sign * (tp2 - entry) * size
                realized -= fill_cost(frac * size * tp2)
                events.append({"type": "TP2", "t": b["t"], "price": tp2, "fraction": frac})
                remaining = 0.0
                reason = "TP2"
                break

        if remaining > 0:
            last = h1[min(exit_i, len(h1) - 1)]
            mark = last["c"]
            realized += remaining * sign * (mark - entry) * size
            realized -= fill_cost(remaining * size * mark)
            events.append({"type": "END_MARK", "t": last["t"], "price": mark, "fraction": remaining})
            reason = "END_MARK"

        busy_until_i = exit_i
        trades.append({
            "symbol": symbol,
            "direction": direction,
            "sweep_t": s["sweep_t"],
            "displacement_t": s["displacement_t"],
            "fvg_t": s["fvg_t"],
            "retest_t": s["retest_t"],
            "confirmation_t": s["confirmation_t"],
            "entry_t": eb["t"],
            "exit_t": h1[min(exit_i, len(h1) - 1)]["t"],
            "entry": entry,
            "stop": stop,
            "tp1": tp1,
            "tp2": tp2,
            "risk_pct": risk / entry,
            "r": realized,
            "reason": reason,
            "events": events,
        })
    return trades


def max_drawdown(rs):
    eq = 0.0
    peak = 0.0
    worst = 0.0
    for r in rs:
        eq += r
        peak = max(peak, eq)
        worst = min(worst, eq - peak)
    return worst


def max_loss_streak(rs):
    best = cur = 0
    for r in rs:
        if r < 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def metrics(trades):
    ts = sorted(trades, key=lambda x: (x["exit_t"], x["symbol"]))
    rs = [x["r"] for x in ts]
    pos = [r for r in rs if r > 0]
    neg = [r for r in rs if r < 0]
    tp1 = sum(any(e["type"] == "TP1" for e in x["events"]) for x in ts)
    tp2 = sum(any(e["type"] == "TP2" for e in x["events"]) for x in ts)
    return {
        "trades": len(ts),
        "long": sum(x["direction"] == "LONG" for x in ts),
        "short": sum(x["direction"] == "SHORT" for x in ts),
        "wins": len(pos),
        "losses": len(neg),
        "win_rate": len(pos) / len(ts) if ts else None,
        "total_r": sum(rs),
        "avg_r": statistics.fmean(rs) if rs else None,
        "median_r": statistics.median(rs) if rs else None,
        "avg_win_r": statistics.fmean(pos) if pos else None,
        "avg_loss_r": statistics.fmean(neg) if neg else None,
        "profit_factor": (sum(pos) / abs(sum(neg))) if neg else None,
        "max_drawdown_r": max_drawdown(rs),
        "max_losing_streak": max_loss_streak(rs),
        "tp1_rate": tp1 / len(ts) if ts else None,
        "tp2_rate": tp2 / len(ts) if ts else None,
        "avg_risk_pct": statistics.fmean(x["risk_pct"] for x in ts) if ts else None,
    }


def split_name(tms):
    dt = datetime.fromtimestamp(tms / 1000, UTC)
    if dt < TRAIN_END:
        return "development_2021-09-28_2024-09-27"
    if dt < VALID_END:
        return "validation_2024-09-28_2025-09-27"
    return "oos_2025-09-28_2026-09-27"


def main():
    all_trades = []
    setup_counts = {}
    funnel_counts = {}
    source_counts = {}
    for symbol in SYMBOLS:
        print("FETCH_VISION", symbol, "1h", flush=True)
        raw1 = fetch_vision_1h(symbol, WARMUP_START, EVAL_END)
        h1 = enrich_1h(raw1)
        h4 = enrich_4h(aggregate_4h(raw1))
        source_counts[symbol] = {
            "1h_bars": len(h1),
            "4h_bars": len(h4),
            "first_1h_open": datetime.fromtimestamp(h1[0]["t"] / 1000, UTC).isoformat() if h1 else None,
            "last_1h_close": datetime.fromtimestamp(h1[-1]["ct"] / 1000, UTC).isoformat() if h1 else None,
        }
        funnel_counts[symbol] = diagnostic_funnel(h1, h4)
        setups = build_setups(symbol, h1, h4)
        setup_counts[symbol] = len(setups)
        trades = simulate_symbol(symbol, h1, setups)
        all_trades.extend(trades)
        print("DONE", symbol, "setups", len(setups), "trades", len(trades), flush=True)

    by_split = defaultdict(list)
    by_year = defaultdict(list)
    by_symbol = defaultdict(list)
    for t in all_trades:
        by_split[split_name(t["entry_t"])].append(t)
        by_year[str(datetime.fromtimestamp(t["entry_t"] / 1000, UTC).year)].append(t)
        by_symbol[t["symbol"]].append(t)

    out = {
        "strategy": "LDFR_v0.2",
        "status": "FROZEN_V0_2_FIRST_TEST",
        "market": "Binance Vision USDT-M perpetual",
        "symbols": list(SYMBOLS),
        "period": {"warmup_start": WARMUP_START.isoformat(), "eval_start": EVAL_START.isoformat(), "eval_end_exclusive": EVAL_END.isoformat()},
        "logic": {
            "regime": "closed 4H close>EMA50, EMA20>EMA50, EMA20 5-bar slope>0 for long; exact inverse short",
            "liquidity_sweep": f"1H current extreme breaches prior {SWEEP_LOOKBACK}-bar extreme and closes back inside",
            "displacement": f"within {DISPLACEMENT_WINDOW} bars: range>={DISPLACEMENT_ATR} ATR14, body/range>={DISPLACEMENT_BODY_FRAC}, CLV long>={DISPLACEMENT_CLV_LONG}/short<={DISPLACEMENT_CLV_SHORT}",
            "fvg": f"3-candle FVG >= {FVG_MIN_ATR} ATR14 on displacement bar or within next {FVG_AFTER_DISPLACEMENT_BARS} bars",
            "retest": f"FVG midpoint touch within {RETEST_WINDOW} bars without close through far edge",
            "confirmation": f"within {CONFIRM_WINDOW} bars after retest: close beyond prior candle high/low; entry next 1H open",
            "stop": f"sweep extreme +/- {STOP_PAD_ATR} ATR14",
            "management": f"TP1 {TP1_R}R on {TP1_FRACTION:.0%}, remainder stop->BE; TP2 {TP2_R}R exits rest",
            "ambiguity": "same 1H bar stop checked before targets",
            "costs": {"fee_bps_per_fill": FEE_BPS, "slippage_bps_per_fill": SLIPPAGE_BPS},
            "positioning": "fixed 1R reference risk per trade; one open position per symbol",
        },
        "data_counts": source_counts,
        "setup_counts": setup_counts,
        "funnel_counts": funnel_counts,
        "summary": metrics(all_trades),
        "splits": {k: metrics(v) for k, v in sorted(by_split.items())},
        "years": {k: metrics(v) for k, v in sorted(by_year.items())},
        "symbols_summary": {k: metrics(v) for k, v in sorted(by_symbol.items())},
        "trades": sorted(all_trades, key=lambda x: (x["entry_t"], x["symbol"])),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"summary": out["summary"], "splits": out["splits"], "setup_counts": setup_counts, "funnel_counts": funnel_counts}, indent=2), flush=True)


if __name__ == "__main__":
    main()
