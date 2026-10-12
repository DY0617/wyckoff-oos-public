"""ARM v1 data adapters & reproducible research runner.

Stock: HF historical US 1-minute RTH, aggregated into 09:30 ET-anchored 1H.
Crypto: Binance Vision USDT-M 1H and historical funding settlement rates.
Run: python scripts/backtest_arm_v1_swing.py --market crypto|stock
"""
import argparse
import csv
import io
import json
import math
import os
import time
import urllib.error
import urllib.request
import zipfile
from collections import defaultdict
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import arm_v1_swing_core as arm

UTC = timezone.utc
NY = ZoneInfo("America/New_York")
STOCKS = ("AAPL", "AMZN", "AVGO", "MSFT", "MU", "AMD", "INTC", "JPM", "NFLX",
          "V", "COST", "GOOGL", "META", "NVDA", "TSLA", "UBER", "WMT", "AMAT",
          "CAT", "HD", "ORCL", "TSM", "CRM", "CSCO", "DIS", "IBM", "COIN", "MSTR")
# Existing stock30 core set, minus SPY and QQQ ETFs. ETFs are benchmarks, not selection candidates.
STOCKS = STOCKS + ("QQQ",)
STOCK_SOURCE = tuple(sorted(set(STOCKS + ("SPY", "FB", "GOOG"))))
CRYPTO = ("BTCUSDT", "ETHUSDT")
HF = "https://huggingface.co/datasets/mito0o852/OHLCV-1m/resolve/main/data"
VISION = "https://data.binance.vision/data/futures/um/monthly"


def month_range(start, end):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        y, m = (y+1, 1) if m == 12 else (y, m+1)


def retrieve_zip(url, optional=False):
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ARM-v1-research/1.0"})
            with urllib.request.urlopen(req, timeout=55) as r:
                binary = r.read()
            with zipfile.ZipFile(io.BytesIO(binary)) as zf:
                return zf.read(zf.namelist()[0]).decode("utf-8-sig")
        except urllib.error.HTTPError as e:
            if optional and e.code == 404:
                return None
            last = e
        except Exception as e:
            last = e
        time.sleep(2 * (attempt+1))
    raise RuntimeError("Required archive unavailable: " + url + " (" + repr(last) + ")")


def collect_crypto(start, end):
    result = {s: [] for s in CRYPTO}
    for sym in CRYPTO:
        for y, m in month_range(start, end - timedelta(milliseconds=1)):
            url = f"{VISION}/klines/{sym}/1h/{sym}-1h-{y:04d}-{m:02d}.zip"
            rows = csv.reader(io.StringIO(retrieve_zip(url)))
            count = 0
            for row in rows:
                if not row or not row[0].isdigit():
                    continue
                ts = int(row[0])
                if ts < 10_000_000_000:
                    ts *= 1000
                dt = datetime.fromtimestamp(ts/1000, UTC)
                if dt < start or dt >= end:
                    continue
                result[sym].append(dict(t=ts, ct=ts+3_600_000-1,
                                         o=float(row[1]), h=float(row[2]), l=float(row[3]),
                                         c=float(row[4]), v=float(row[5]),
                                         day=dt.date().isoformat()))
                count += 1
            print("CRYPTO", sym, y, m, count, flush=True)
    for s, arr in result.items():
        arr.sort(key=lambda b: b["t"])
        if not arr:
            raise RuntimeError("No crypto history: " + s)
    return result


def normalize_stock_symbol(sym, date_value):
    if sym == "FB":
        return "META" if date_value < date(2022, 6, 9) else None
    if sym == "META":
        return "META" if date_value >= date(2022, 6, 9) else None
    if sym == "GOOG":
        return "GOOGL" if date_value < date(2014, 4, 3) else None
    if sym == "GOOGL":
        return "GOOGL" if date_value >= date(2014, 4, 3) else None
    return sym if sym in STOCKS or sym == "SPY" else None


def adjust_splits(bars):
    """Detect common split ratios; adjust preceding prices, NOT the current/future prices."""
    if not bars:
        return bars
    by_day = defaultdict(list)
    for b in bars:
        by_day[b["day"]].append(b)
    days = sorted(by_day)
    events = []
    for i in range(1, len(days)):
        before = by_day[days[i-1]][-1]["c"]
        after = by_day[days[i]][0]["o"]
        if before <= 0 or after <= 0:
            continue
        ratio = before / after
        mag = max(ratio, 1/ratio)
        if mag < 1.35:
            continue
        split = min((1.5, 2, 3, 4, 5, 7, 10, 15, 20), key=lambda k: abs(mag/k - 1))
        if abs(mag/split - 1) <= 0.05:
            events.append((days[i], 1/split if ratio > 1 else split))
    for b in bars:
        factor = math.prod(f for d, f in events if b["day"] < d)
        for col in ("o", "h", "l", "c"):
            b[col] *= factor
        if factor:
            b["v"] /= factor
    return bars


def collect_stocks(start, end):
    try:
        import duckdb
    except ImportError as e:
        raise RuntimeError("Stock research requires: pip install duckdb") from e
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs")
    out = defaultdict(list)
    qmarks = ",".join(["?"] * len(STOCK_SOURCE))
    sql = f"""
      WITH src AS (
        SELECT ticker, timezone('America/New_York', timestamp) AS et,
               open, high, low, "close", volume
        FROM read_parquet(?) WHERE ticker IN ({qmarks})
      ), rth AS (
        SELECT *, cast(et AS DATE) AS d,
             CAST(floor((extract(hour FROM et)*60 + extract(minute FROM et)-570)/60) AS INTEGER) AS slot
        FROM src WHERE cast(et AS TIME)>=time '09:30:00'
                 AND cast(et AS TIME)<time '16:00:00'
      )
      SELECT ticker, d, slot, arg_min(open, et), max(high), min(low),
             arg_max("close", et), sum(volume)
      FROM rth GROUP BY ticker,d,slot ORDER BY ticker,d,slot
    """
    for y, m in month_range(start, end - timedelta(milliseconds=1)):
        uri = f"{HF}/ohlcv_{y:04d}-{m:02d}.parquet"
        last_error = None
        rows = None
        for attempt in range(5):
            try:
                rows = con.execute(sql, [uri, *STOCK_SOURCE]).fetchall()
                break
            except Exception as e:
                last_error = e
                print("HF RETRY", y, m, attempt+1, repr(e), flush=True)
                time.sleep(min(25, 4*(attempt+1)))
        if rows is None:
            raise RuntimeError(f"Missing stock parquet {y}-{m:02d}: {last_error!r}")
        for original, day, slot, op, hi, lo, cl, vol in rows:
            sym = normalize_stock_symbol(str(original), day)
            if sym is None:
                continue
            local = datetime.combine(day, dtime(9,30), tzinfo=NY) + timedelta(hours=int(slot))
            ts = int(local.astimezone(UTC).timestamp() * 1000)
            close_local = min(local + timedelta(hours=1),
                              datetime.combine(day, dtime(16), tzinfo=NY))
            ct = int(close_local.astimezone(UTC).timestamp() * 1000) - 1
            if ts < int(start.timestamp()*1000) or ts >= int(end.timestamp()*1000):
                continue
            out[sym].append(dict(t=ts, ct=ct, o=float(op), h=float(hi),
                                 l=float(lo), c=float(cl), v=float(vol or 0),
                                 day=day.isoformat(), session_hour=int(slot)))
        print("STOCK MONTH", y, m, len(rows), flush=True)
    con.close()
    for sym in STOCKS + ("SPY",):
        out[sym].sort(key=lambda b: b["t"])
        if not out[sym]:
            raise RuntimeError("Missing stock symbol " + sym)
        adjust_splits(out[sym])
    return out


def funding_rows(text):
    if text is None:
        return []
    lines = list(csv.reader(io.StringIO(text)))
    if not lines:
        return []
    hdr = [x.strip().lower() for x in lines[0]]
    if not lines[0][0].strip().isdigit():
        ix = {k: i for i, k in enumerate(hdr)}
        ti = ix.get("calc_time", ix.get("fundingtime", 0))
        ri = ix.get("last_funding_rate", ix.get("funding_rate", ix.get("fundingrate", 1)))
        lines = lines[1:]
    else:
        ti, ri = 0, 1
    result = []
    for row in lines:
        try:
            ts, rate = int(float(row[ti])), float(row[ri])
            if ts < 10_000_000_000:
                ts *= 1000
            result.append((ts, rate))
        except (ValueError, IndexError):
            pass
    return result


def collect_funding(trades):
    required = defaultdict(set)
    for tr in trades:
        from_dt = datetime.fromtimestamp(tr["entry_t"]/1000, UTC)
        to_dt = datetime.fromtimestamp(tr["exit_t"]/1000, UTC)
        for y, m in month_range(from_dt, to_dt):
            required[tr["symbol"]].add((y,m))
    funding = {}
    for sym, months in required.items():
        rates = []
        for y, m in sorted(months):
            url = f"{VISION}/fundingRate/{sym}/{sym}-fundingRate-{y:04d}-{m:02d}.zip"
            txt = retrieve_zip(url)
            r = funding_rows(txt)
            if not r:
                raise RuntimeError("Funding archive unexpectedly empty: " + url)
            rates.extend(r)
            print("FUNDING", sym, y, m, len(r), flush=True)
        funding[sym] = sorted(set(rates))
    return funding


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", choices=["stock", "crypto"], required=True)
    parser.add_argument("--start", default="2021-09-28")
    parser.add_argument("--end", default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    eval_start = datetime.fromisoformat(args.start).replace(tzinfo=UTC)
    default_end = "2026-04-01" if args.market == "stock" else "2026-09-28"
    eval_end = datetime.fromisoformat(args.end or default_end).replace(tzinfo=UTC)
    if eval_end <= eval_start:
        raise ValueError("Evaluation period must be positive")
    warmup_start = eval_start - timedelta(days=520)
    source_end = eval_end
    raw = (collect_stocks(warmup_start, source_end) if args.market == "stock"
           else collect_crypto(warmup_start, source_end))
    prepared = {k: arm.prepare(v, args.market) for k,v in raw.items()}
    bench = prepared["SPY" if args.market=="stock" else "BTCUSDT"]
    universe = (STOCKS if args.market == "stock" else CRYPTO)
    rank_dates = (arm.stock_rank_dates({s:prepared[s] for s in universe}, bench)
                  if args.market=="stock" else None)
    all_trades = []
    for sym in universe:
        t = arm.run_symbol(sym, prepared[sym], bench, args.market, rank_dates)
        all_trades.extend(tr for tr in t if
                          int(eval_start.timestamp()*1000) <= tr["entry_t"] < int(eval_end.timestamp()*1000))
        print("SYMBOL", sym, len(t), flush=True)
    funding = collect_funding(all_trades) if args.market == "crypto" else {}
    arm.apply_funding(all_trades, funding)
    eligible, p = arm.portfolio(all_trades)
    report = {
        "name": "ARM_v1_swing_frozen",
        "market": args.market,
        "window": {"start": args.start, "end_exclusive": eval_end.date().isoformat()},
        "instruments": list(universe),
        "parameters": arm.PARAMS,
        "raw": arm.summary(all_trades),
        "portfolio": {"stats": arm.summary(eligible), **p},
        "by_symbol": {s: arm.summary([t for t in all_trades if t["symbol"]==s]) for s in universe},
        "trades": all_trades,
        "costs": {"fee_plus_slippage_each_side_bps": 6,
                  "funding": "actual settlement rates, entry-notional approximation" if args.market=="crypto" else "N/A"},
        "limitations": [
            "Hypothesis, not validated profitability; temporal / unseen-symbol OOS still required.",
            "Portfolio cap is applied post-trade-simulation rather than integrated into the strategy engine.",
            "One-hour OHLC fill ordering is conservative and can overestimate stop-outs.",
            "Gap entry and gap stop use observed hour open; partial-hour fill sequence is unknown.",
            "Stock universe is a current-selected set with survivorship bias and split-event heuristic.",
            "Crypto funding applies entry notional at settlement, not historical varying mark notional.",
            "No liquidation, borrow, futures basis, exchange outage, market impact or tax model.",
            "Time stop uses 70 RTH hour-bars (approximately 10 sessions) for stocks, 10 calendar days for crypto."
        ]
    }
    out = Path(args.out or f"data/validation/arm_v1_swing_{args.market}.json")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("SUMMARY", json.dumps({"market":args.market, "raw":report["raw"],
                                 "portfolio":{k:v for k,v in report["portfolio"].items() if k!="curve"},
                                 "by_symbol":report["by_symbol"]}, indent=2), flush=True)


if __name__ == "__main__":
    main()
