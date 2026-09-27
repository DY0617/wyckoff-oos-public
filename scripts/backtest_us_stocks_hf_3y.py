import bisect
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import requests
import pandas_market_calendars as mcal
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

sys.path.insert(0, str(Path(__file__).parent))
import wyckoff_status as w

SYMBOLS = (
    "AAOI","AAPL","AMAT","AMD","AMZN","ARM","AVGO","AXTI","BABA","BE",
    "BMNR","CAT","CBRS","COHR","COIN","COST","CRCL","CRDO","CRM","CRWD",
    "CRWV","CSCO","DELL","DIS","DRAM","EWJ","EWY","GME","GOOGL","HD",
    "HOOD","HPE","IBM","INTC","IREN","IWM","JPM","KORU","LITE","LLY",
    "META","MRVL","MSFT","MSTR","MU","MUU","NBIS","NFLX","NVDA","ORCL",
    "PLTR","QCOM","QQQ","RKLB","SKHY","SMCI","SNDK","SNXX","SOXL","SOXS",
    "SPCX","SPY","TQQQ","TSLA","TSM","UBER","V","WDC","WMT","ZM",
)
HF_BASE = "https://huggingface.co/datasets/mito0o852/OHLCV-1m/resolve/main/data"
WARMUP_START = pd.Timestamp("2022-09-01", tz="UTC")
EVAL_START = pd.Timestamp("2023-04-01", tz="UTC")
EVAL_END = pd.Timestamp("2026-04-01", tz="UTC")
TF15 = 15 * 60 * 1000
OUT = Path("data/validation/us_stocks_hf_3y_backtest.json")
TRADES_OUT = Path("data/validation/us_stocks_hf_3y_trades.json")
NY = "America/New_York"


def month_iter(start, end):
    p = start.to_period("M")
    q = (end - pd.Timedelta(days=1)).to_period("M")
    while p <= q:
        yield f"{p.year:04d}-{p.month:02d}"
        p += 1


def make_http():
    s = requests.Session()
    retry = Retry(total=5, connect=5, read=5, backoff_factor=1.5,
                  status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=frozenset(["GET"]))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update({"User-Agent": "wyckoff-data-us-stock-hf-backtest/1.0"})
    return s


def download_month(session, ym, dst):
    url = f"{HF_BASE}/ohlcv_{ym}.parquet"
    with session.get(url, stream=True, timeout=(20, 300)) as r:
        r.raise_for_status()
        with open(dst, "wb") as f:
            for chunk in r.iter_content(chunk_size=8 * 1024 * 1024):
                if chunk:
                    f.write(chunk)
    return os.path.getsize(dst)


def normalize_ts(series):
    if pd.api.types.is_datetime64_any_dtype(series):
        return pd.to_datetime(series, utc=True, errors="coerce")
    if pd.api.types.is_numeric_dtype(series):
        valid = pd.to_numeric(series, errors="coerce").dropna()
        if valid.empty:
            return pd.to_datetime(series, utc=True, errors="coerce")
        x = float(valid.abs().median())
        unit = "ns" if x >= 1e17 else "us" if x >= 1e14 else "ms" if x >= 1e11 else "s"
        return pd.to_datetime(series, unit=unit, utc=True, errors="coerce")
    return pd.to_datetime(series, utc=True, errors="coerce")


def market_schedule():
    cal = mcal.get_calendar("NYSE")
    sched = cal.schedule(start_date=WARMUP_START.date(), end_date=(EVAL_END - pd.Timedelta(days=1)).date())
    sched = sched.rename(columns={"market_open": "session_open", "market_close": "session_close"})
    sched["session_date"] = [x.date() for x in sched.index]
    return sched[["session_date", "session_open", "session_close"]].reset_index(drop=True)


def load_15m():
    schedule = market_schedule()
    all_parts = []
    coverage = {s: {"raw_1m": 0, "bars_15m": 0} for s in SYMBOLS}
    http = make_http()
    tmp = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "hf_us_1m_month.parquet"

    for idx, ym in enumerate(month_iter(WARMUP_START, EVAL_END), 1):
        t0 = time.time()
        if tmp.exists():
            tmp.unlink()
        size = download_month(http, ym, tmp)
        table = pq.read_table(
            tmp,
            columns=["timestamp", "open", "high", "low", "close", "volume", "ticker"],
            filters=[("ticker", "in", list(SYMBOLS))],
        )
        df = table.to_pandas()
        del table
        if df.empty:
            print(f"{ym}: no target rows, file={size/1e6:.1f}MB", flush=True)
            tmp.unlink(missing_ok=True)
            continue

        df["ticker"] = df["ticker"].astype(str).str.upper()
        df = df[df["ticker"].isin(SYMBOLS)].copy()
        df["timestamp"] = normalize_ts(df["timestamp"])
        df = df.dropna(subset=["timestamp", "open", "high", "low", "close", "volume"])
        for s, n in df["ticker"].value_counts().items():
            if s in coverage:
                coverage[s]["raw_1m"] += int(n)

        local = df["timestamp"].dt.tz_convert(NY)
        df["session_date"] = local.dt.date
        df = df.merge(schedule, on="session_date", how="inner")
        df = df[(df["timestamp"] >= df["session_open"]) & (df["timestamp"] < df["session_close"])].copy()
        if df.empty:
            tmp.unlink(missing_ok=True)
            continue

        offset_min = ((df["timestamp"] - df["session_open"]).dt.total_seconds() // 60).astype("int32")
        df["bucket"] = (offset_min // 15).astype("int16")
        df["bucket_t"] = df["session_open"] + pd.to_timedelta(df["bucket"] * 15, unit="m")
        df = df.sort_values(["ticker", "timestamp"])
        g = (df.groupby(["ticker", "session_date", "bucket_t", "session_close"], observed=True, sort=False)
               .agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                    close=("close", "last"), volume=("volume", "sum"), n1m=("timestamp", "size"))
               .reset_index())
        all_parts.append(g)
        for s, n in g["ticker"].value_counts().items():
            if s in coverage:
                coverage[s]["bars_15m"] += int(n)
        print(f"{ym}: file={size/1e6:.1f}MB target1m={len(df):,} rth15m={len(g):,} {time.time()-t0:.1f}s", flush=True)
        tmp.unlink(missing_ok=True)

    if not all_parts:
        raise RuntimeError("No target data downloaded from Hugging Face")
    m15 = pd.concat(all_parts, ignore_index=True)
    m15 = (m15.sort_values(["ticker", "bucket_t"])
               .drop_duplicates(["ticker", "bucket_t"], keep="last"))
    return m15, coverage


def rows_for_symbol(m15, symbol):
    x = m15[m15["ticker"] == symbol].copy()
    if x.empty:
        return [], [], []
    x = x.sort_values("bucket_t")
    # Do not assume pandas datetime storage resolution (ns/us can vary by backend).
    # Convert through Timestamp.timestamp() so internal bar times are always epoch milliseconds.
    x["t"] = x["bucket_t"].map(lambda z: int(pd.Timestamp(z).timestamp() * 1000)).astype("int64")
    x["ct"] = x["t"] + TF15 - 1

    M = [{"t": int(r.t), "o": float(r.open), "h": float(r.high), "l": float(r.low),
          "c": float(r.close), "v": float(r.volume), "ct": int(r.ct)}
         for r in x.itertuples(index=False)]
    if M and M[0]["t"] < 1_000_000_000_000:
        raise RuntimeError(f"timestamp unit error for {symbol}: {M[0]['t']}")

    local = x["bucket_t"].dt.tz_convert(NY)
    x["local_min"] = local.dt.hour * 60 + local.dt.minute
    close_local = x["session_close"].dt.tz_convert(NY)
    x["close_min"] = close_local.dt.hour * 60 + close_local.dt.minute
    x["h_bucket"] = ((x["close_min"] > 810) & (x["local_min"] >= 810)).astype("int8")

    def aggregate(group_cols):
        out = []
        for _, g in x.groupby(group_cols, observed=True, sort=True):
            g = g.sort_values("bucket_t")
            out.append({
                "t": int(g["t"].iloc[0]),
                "o": float(g["open"].iloc[0]),
                "h": float(g["high"].max()),
                "l": float(g["low"].min()),
                "c": float(g["close"].iloc[-1]),
                "v": float(g["volume"].sum()),
                "ct": int(g["ct"].iloc[-1]),
            })
        return out

    H = aggregate(["session_date", "h_bucket"])
    D = aggregate(["session_date"])
    return M, H, D


def floor_cent(x):
    return math.floor((x + 1e-9) * 100) / 100


def ceil_cent(x):
    return math.ceil((x - 1e-9) * 100) / 100


def quantize_snap(snap):
    s = dict(snap)
    if s.get("entry") is None or s.get("stop") is None:
        return s
    d = s.get("direction")
    if d == "LONG":
        s["entry"] = ceil_cent(float(s["entry"]))
        s["stop"] = floor_cent(float(s["stop"]))
        if s.get("tp1") is not None: s["tp1"] = floor_cent(float(s["tp1"]))
        if s.get("tp2") is not None: s["tp2"] = floor_cent(float(s["tp2"]))
    elif d == "SHORT":
        s["entry"] = floor_cent(float(s["entry"]))
        s["stop"] = ceil_cent(float(s["stop"]))
        if s.get("tp1") is not None: s["tp1"] = ceil_cent(float(s["tp1"]))
        if s.get("tp2") is not None: s["tp2"] = ceil_cent(float(s["tp2"]))
    if s.get("tp2") is not None:
        risk = abs(s["entry"] - s["stop"])
        s["rr"] = ((s["tp2"] - s["entry"]) / risk if d == "LONG"
                   else (s["entry"] - s["tp2"]) / risk) if risk else -99
    return s


def simulate_symbol(symbol, M, H0, D0):
    if len(D0) < 60 or len(H0) < 60 or not M:
        return {"symbol": symbol, "skipped": True, "reason": "INSUFFICIENT_RTH_DATA",
                "data": {"d1": len(D0), "h4": len(H0), "m15": len(M)}, "trades": []}

    H = w.enrich([dict(z) for z in H0])
    D = w.enrich([dict(z) for z in D0])
    mt = [z["t"] for z in M]
    hc = [z["ct"] for z in H]
    dc = [z["ct"] for z in D]
    h_index = {z["t"]: i for i, z in enumerate(H)}
    eval_start_ms = int(EVAL_START.timestamp() * 1000)
    eval_end_ms = int(EVAL_END.timestamp() * 1000)

    seen = set()
    pending = {}
    trades = []
    busy_until = -1

    def finish_trade(p, trig):
        direction = p["direction"]
        entry, stop0, tp1, tp2 = map(float, (p["entry"], p["stop"], p["tp1"], p["tp2"]))
        risk = abs(entry - stop0)
        if risk <= 0:
            return None
        sign = 1 if direction == "LONG" else -1
        trig_open = H[trig]["t"]
        trig_end = H[trig]["ct"] + 1
        mi = bisect.bisect_left(mt, trig_open)
        entry_i = None
        while mi < len(M) and M[mi]["t"] < trig_end:
            z = M[mi]
            if z["l"] <= entry <= z["h"]:
                entry_i = mi
                break
            mi += 1
        if entry_i is None:
            return None

        rr = 0.0
        remain = 1.0
        stop = stop0
        tp1_done = False
        tp2_done = False
        last_z = None
        entry_t = M[entry_i]["t"]
        mi = entry_i

        while mi < len(M) and M[mi]["t"] < eval_end_ms:
            z = M[mi]
            zclose = z["ct"]
            last_z = z
            hit_stop = z["l"] <= stop if direction == "LONG" else z["h"] >= stop
            if hit_stop:
                rr += remain * (sign * (stop - entry) / risk)
                remain = 0.0
                break

            hit_tp1 = (z["h"] >= tp1) if direction == "LONG" else (z["l"] <= tp1)
            if not tp1_done and hit_tp1:
                rr += 0.30 * (sign * (tp1 - entry) / risk)
                remain -= 0.30
                tp1_done = True
                if (direction == "LONG" and stop < entry) or (direction == "SHORT" and stop > entry):
                    stop = entry

            hit_tp2 = (z["h"] >= tp2) if direction == "LONG" else (z["l"] <= tp2)
            if not tp2_done and hit_tp2:
                rr += 0.30 * (sign * (tp2 - entry) / risk)
                remain -= 0.30
                tp2_done = True
                if (direction == "LONG" and stop < tp1) or (direction == "SHORT" and stop > tp1):
                    stop = tp1

            if tp2_done and remain > 1e-12:
                hk = bisect.bisect_right(hc, zclose) - 1
                if hk >= 2:
                    piv = hk - 1
                    atr = H[piv].get("atr")
                    if atr:
                        if direction == "LONG" and H[piv]["l"] < H[piv-1]["l"] and H[piv]["l"] < H[piv+1]["l"]:
                            ns = floor_cent(H[piv]["l"] - 0.3 * atr)
                            if ns > stop:
                                stop = ns
                        if direction == "SHORT" and H[piv]["h"] > H[piv-1]["h"] and H[piv]["h"] > H[piv+1]["h"]:
                            ns = ceil_cent(H[piv]["h"] + 0.3 * atr)
                            if ns < stop:
                                stop = ns
            mi += 1

        base = {
            "symbol": symbol, "direction": direction, "entry_t": entry_t,
            "exit_t": (last_z["t"] if last_z else entry_t),
            "entry": entry, "initial_stop": stop0, "tp1": tp1, "tp2": tp2,
            "planned_rr": float(p["rr"]), "tp1_hit": tp1_done, "tp2_hit": tp2_done,
            "limit_fill": True,
        }
        if remain > 0:
            mark = last_z["c"] if last_z else entry
            return {**base, "r": rr + remain * (sign * (mark - entry) / risk), "open": True}
        return {**base, "r": rr, "open": False}

    for hi in range(12, len(H)):
        if H[hi]["t"] < eval_start_ms:
            continue
        if H[hi]["t"] >= eval_end_ms:
            break
        if H[hi]["t"] <= busy_until:
            continue
        close_t = H[hi]["ct"]
        di = bisect.bisect_right(dc, close_t) - 1
        if di < 30:
            continue
        hs = H[max(0, hi-799):hi+1]
        ds = D[max(0, di-199):di+1]
        if len(hs) < 60 or len(ds) < 60:
            continue

        snap = quantize_snap(w.local(hs, ds, {}))
        cur_atr = H[hi].get("atr")

        filled_this_bar = False
        for key, p in list(pending.items()):
            if hi <= p["seen_hi"]:
                continue
            z = H[hi]
            touched = z["h"] >= p["entry"] if p["direction"] == "LONG" else z["l"] <= p["entry"]
            if touched:
                tr = finish_trade(p, hi)
                if tr is not None:
                    del pending[key]
                    trades.append(tr)
                    busy_until = (10**30 if tr["open"] else tr["exit_t"])
                    pending.clear()
                    filled_this_bar = True
                    break
            hard = bool(cur_atr and (z["c"] < p["support"] - 0.75*cur_atr or z["c"] > p["resistance"] + 0.75*cur_atr))
            is_out = z["c"] < p["support"] or z["c"] > p["resistance"]
            p["outside_count"] = p.get("outside_count", 0) + 1 if is_out else 0
            if hard or p["outside_count"] >= 2 or hi >= p["expiry_hi"]:
                pending.pop(key, None)

        if filled_this_bar or H[hi]["t"] <= busy_until:
            continue
        if (snap.get("actionable") and snap.get("entry") is not None and snap.get("stop") is not None
                and snap.get("tp1") is not None and snap.get("tp2") is not None):
            key = ("B", snap["direction"], snap.get("test_open_ms"),
                   round(float(snap["entry"]), 2), round(float(snap["stop"]), 2))
            if key not in seen:
                seen.add(key)
                ti = h_index.get(int(snap["test_open_ms"]))
                if ti is not None:
                    expiry_hi = min(ti + 9, len(H) - 1)
                    if hi < expiry_hi:
                        pending[key] = {
                            "direction": snap["direction"], "entry": float(snap["entry"]),
                            "stop": float(snap["stop"]), "tp1": float(snap["tp1"]),
                            "tp2": float(snap["tp2"]), "rr": float(snap["rr"]),
                            "support": float(snap["support"]), "resistance": float(snap["resistance"]),
                            "seen_hi": hi, "expiry_hi": expiry_hi, "outside_count": 0,
                        }

    return {
        "symbol": symbol, "skipped": False,
        "data": {
            "d1": len(D), "h4": len(H), "m15": len(M),
            "first": D[0]["t"], "last": M[-1]["t"],
            "aggregation": "HF_1M_OFFICIAL_RTH_TO_15M_4H_STUB_1D",
            "entry_session": "OFFICIAL_RTH_ONLY",
            "management": "RTH_SPOT_15M",
            "entry_fill_model": "LIMIT_TOUCH_PLANNED_PRICE",
            "source": "HUGGINGFACE_mito0o852_OHLCV-1m",
        },
        "trades": trades,
    }


def summarize(trades):
    closed = [t for t in trades if not t["open"]]
    wins = sum(t["r"] > 0 for t in closed)
    losses = sum(t["r"] < 0 for t in closed)
    be = len(closed) - wins - losses
    return {
        "entered": len(trades), "closed": len(closed), "open": len(trades)-len(closed),
        "wins": wins, "losses": losses, "be": be,
        "win_rate": wins/len(closed) if closed else None,
        "total_r": sum(t["r"] for t in closed),
        "avg_r": sum(t["r"] for t in closed)/len(closed) if closed else None,
        "tp1_hit_rate": sum(t["tp1_hit"] for t in trades)/len(trades) if trades else None,
        "tp2_hit_rate": sum(t["tp2_hit"] for t in trades)/len(trades) if trades else None,
    }


def main():
    started = datetime.now(timezone.utc)
    m15, coverage = load_15m()
    symbol_results = {}
    all_trades = []
    missing = []
    firsts, lasts = [], []

    for i, symbol in enumerate(SYMBOLS, 1):
        M, H, D = rows_for_symbol(m15, symbol)
        if M:
            firsts.append(M[0]["t"])
            lasts.append(M[-1]["t"])
        r = simulate_symbol(symbol, M, H, D)
        s = summarize(r["trades"])
        symbol_results[symbol] = {**s, "data": r["data"]}
        all_trades.extend(r["trades"])
        if not M:
            missing.append(symbol)
        print(f"[{i}/{len(SYMBOLS)}] {symbol}: {s}", flush=True)

    all_trades.sort(key=lambda t: (t["entry_t"], t["symbol"]))
    total = summarize(all_trades)

    report = {
        "engine": "STOCK_TRACK_B_US_SPOT_HF_3Y_V1_LIMIT_TOUCH",
        "source": {
            "dataset": "mito0o852/OHLCV-1m",
            "host": "Hugging Face",
            "original_source": "Finnhub per dataset card",
            "source_timeframe": "1m",
            "backtest_timeframe": "RTH 15m -> RTH 4h stub + 1d",
        },
        "period": {
            "warmup_start": WARMUP_START.isoformat(),
            "evaluation_start": EVAL_START.isoformat(),
            "evaluation_end_exclusive": EVAL_END.isoformat(),
            "requested_years": 3,
            "actual_first_15m_ms": min(firsts) if firsts else None,
            "actual_last_15m_ms": max(lasts) if lasts else None,
        },
        "strategy": {
            "name": "Track B frozen",
            "entry_fill": "LIMIT_TOUCH: low <= planned_entry <= high",
            "entry": "official US RTH only",
            "management": "RTH spot 15m proxy; TP1 30%->BE, TP2 30%->TP1, runner 40% confirmed RTH 4h pivot",
            "costs": "none (R-multiple structural comparison)",
            "proxy_limitations": [
                "US cash/ETF prices, not Binance TradFi perpetual futures",
                "management observes RTH spot bars only, not Binance 24h futures bars",
                "symbols without public US cash history are reported as missing/short-history",
            ],
        },
        "universe": {"requested": len(SYMBOLS), "symbols": list(SYMBOLS), "missing_no_rows": missing},
        "totals": total,
        "symbols": symbol_results,
        "coverage": coverage,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runtime_seconds": (datetime.now(timezone.utc)-started).total_seconds(),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    TRADES_OUT.write_text(json.dumps({"summary": report, "trades": all_trades}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({"totals": total, "missing": missing, "runtime_seconds": report["runtime_seconds"]}, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
