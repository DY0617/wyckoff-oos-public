import json
import statistics
from collections import defaultdict
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

import backtest_trend_structure_v0_1_crypto as core
from extract_stock53_recent5y_15m_cache import SYMS

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/cache/stock53_recent5y_15m.parquet"
OUT = ROOT / "data/validation/trend_structure_v0_1_stock53_recent5y.json"

UTC = timezone.utc
NY = ZoneInfo("America/New_York")
EVAL_START = datetime(2021, 4, 1, tzinfo=UTC)
EVAL_END = datetime(2026, 4, 1, tzinfo=UTC)


def to_ms(ts):
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=NY)
    return int(ts.astimezone(UTC).timestamp() * 1000)


def load_symbol(con, sym):
    rows = con.execute(
        """
        SELECT b,o,h,l,c,v
        FROM read_parquet(?)
        WHERE symbol=?
        ORDER BY b
        """,
        [str(DATA), sym],
    ).fetchall()
    out = []
    for ts, o, h, l, c, v in rows:
        t = to_ms(ts)
        out.append(
            {
                "t": t,
                "ct": t + 15 * 60_000,
                "o": float(o),
                "h": float(h),
                "l": float(l),
                "c": float(c),
                "v": float(v),
            }
        )
    return out


def session_key(bar):
    dt = datetime.fromtimestamp(bar["t"] / 1000, UTC).astimezone(NY)
    return dt.date(), dt.hour, dt.minute


def aggregate_rth_1h(b15):
    by_day = defaultdict(list)
    for b in b15:
        dt = datetime.fromtimestamp(b["t"] / 1000, UTC).astimezone(NY)
        if time(9, 30) <= dt.time() < time(16, 0):
            by_day[dt.date()].append(b)

    out = []
    for d in sorted(by_day):
        xs = sorted(by_day[d], key=lambda z: z["t"])
        # Six complete 60m bars from 09:30 through 15:30 ET.
        # The final 15:30-16:00 half-hour stays execution-only.
        for k in range(0, 24, 4):
            part = xs[k : k + 4]
            if len(part) != 4:
                continue
            if part[-1]["ct"] - part[0]["t"] != 60 * 60_000:
                continue
            out.append(
                {
                    "t": part[0]["t"],
                    "ct": part[-1]["ct"],
                    "o": part[0]["o"],
                    "h": max(z["h"] for z in part),
                    "l": min(z["l"] for z in part),
                    "c": part[-1]["c"],
                    "v": sum(z["v"] for z in part),
                }
            )
    return out


def aggregate_rth_daily(b15):
    by_day = defaultdict(list)
    for b in b15:
        dt = datetime.fromtimestamp(b["t"] / 1000, UTC).astimezone(NY)
        if time(9, 30) <= dt.time() < time(16, 0):
            by_day[dt.date()].append(b)

    out = []
    for d in sorted(by_day):
        xs = sorted(by_day[d], key=lambda z: z["t"])
        if len(xs) < 24:
            continue
        out.append(
            {
                "t": xs[0]["t"],
                "ct": xs[-1]["ct"],
                "o": xs[0]["o"],
                "h": max(z["h"] for z in xs),
                "l": min(z["l"] for z in xs),
                "c": xs[-1]["c"],
                "v": sum(z["v"] for z in xs),
            }
        )
    return out


def main():
    if not DATA.exists():
        raise FileNotFoundError(DATA)

    con = duckdb.connect()
    alltr = []
    symbols = {}
    for n, sym in enumerate(SYMS, 1):
        b15 = load_symbol(con, sym)
        if len(b15) < 500:
            symbols[sym] = {"metrics": core.metrics([]), "stats": {"skipped": "insufficient_data", "bars15": len(b15)}}
            print("SKIP", sym, len(b15), flush=True)
            continue

        h1 = aggregate_rth_1h(b15)
        daily = aggregate_rth_daily(b15)
        ts, st = core.simulate_symbol(
            sym,
            b15,
            h1_override=h1,
            h4_override=daily,
            eval_start=EVAL_START,
            eval_end=EVAL_END,
        )
        st["bars15"] = len(b15)
        st["bars1h_rth"] = len(h1)
        st["daily_rth"] = len(daily)
        symbols[sym] = {"metrics": core.metrics(ts), "stats": st}
        alltr += ts
        print("RESULT", n, len(SYMS), sym, json.dumps(symbols[sym]), flush=True)

    con.close()

    by_track = defaultdict(list)
    by_direction = defaultdict(list)
    by_year = defaultdict(list)
    for t in alltr:
        by_track[t["track"]].append(t)
        by_direction[t["direction"]].append(t)
        by_year[str(datetime.fromtimestamp(t["entry_t"] / 1000, UTC).year)].append(t)

    out = {
        "strategy": "Trend Structure v0.1 frozen",
        "asset_class": "US stock RTH cash-chart research set",
        "clock": {
            "regime": "previous completed RTH daily bar",
            "signal": "six complete 60m RTH bars: 09:30-15:30 ET",
            "execution": "15m RTH, including 15:30-16:00 ET",
        },
        "period": {
            "eval_start": EVAL_START.isoformat(),
            "eval_end_exclusive": EVAL_END.isoformat(),
        },
        "costs": {"fee_bps": core.FEE_BPS, "slippage_bps": core.SLIP_BPS},
        "summary": core.metrics(alltr),
        "tracks": {k: core.metrics(v) for k, v in sorted(by_track.items())},
        "directions": {k: core.metrics(v) for k, v in sorted(by_direction.items())},
        "years": {k: core.metrics(v) for k, v in sorted(by_year.items())},
        "symbols": symbols,
        "trades": alltr,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("FINAL", json.dumps({k: v for k, v in out.items() if k != "trades"}, indent=2), flush=True)


if __name__ == "__main__":
    main()
