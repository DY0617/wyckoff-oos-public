import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import backtest_track_b_15_25_60_alt_oos_v1 as alt
import backtest_sr_reclaim_v1_crypto as sr
import wyckoff_status as w

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/validation/track_b_sr_clear_tp1_alt4_oos_v1.json"


def build_trades(raw, filters):
    cache = {}
    for s in alt.SYMS:
        D = w.enrich([dict(x) for x in raw[s]["1d"]])
        H = w.enrich([dict(x) for x in raw[s]["4h"]])
        M = [dict(x) for x in raw[s]["15m"]]
        cache[s] = (D, H, M)

    alt.bt._CACHE.clear()
    alt.bt.dataset = lambda sym: cache[sym]
    alt.bt.symbol_filters = lambda sym: filters[sym]
    old = alt.bt.RISK
    alt.bt.RISK = alt.RISK
    alltr = []
    try:
        for s in alt.SYMS:
            r = alt.bt.simulate(
                s, alt.A_OFF, {}, alt.EVAL_START_MS, alt.EVAL_END_MS,
                alt.FEE_BPS, alt.SLIPPAGE_BPS,
                a_mode="snapshot", b_runner_mode="pivot", b_scale_mode="15_25_60"
            )
            ts = [
                {"symbol": s, **t}
                for t in r["trades"]
                if t["track"] == "B" and t["reason"] != "OPEN_MARK"
            ]
            alltr += ts
            print("BASE_TRADES", s, len(ts), flush=True)
    finally:
        alt.bt.RISK = old
    return sorted(alltr, key=lambda x: (x["entry_t"], x["symbol"]))


def zone_snapshots(raw, trades):
    by_sym = defaultdict(list)
    for t in trades:
        by_sym[t["symbol"]].append(t)

    out = {}
    for sym, ts in by_sym.items():
        m15 = [{**x, "ct": x["t"] + 15 * 60_000} for x in raw[sym]["15m"]]
        events = sr.zone_events(m15)
        zones = []
        eidx = 0
        next_zone_id = 1
        for t in sorted(ts, key=lambda x: x["entry_t"]):
            now = t["entry_t"]
            while eidx < len(events) and events[eidx]["known_t"] <= now:
                next_zone_id = sr.add_event(zones, events[eidx], next_zone_id)
                eidx += 1
            key = (sym, t["entry_t"], t["direction"], round(float(t["entry"]), 8))
            out[key] = sr.snapshot_active(zones, now)
    return out


def blocked_before_tp1(t, zs):
    tp1 = t.get("tp1")
    if tp1 is None:
        return False
    entry = float(t["entry"])
    tp1 = float(tp1)

    if t["direction"] == "LONG":
        lo, hi = sorted((entry, tp1))
        return any(z["lo"] > lo and z["lo"] < hi for z in zs)

    lo, hi = sorted((tp1, entry))
    return any(z["hi"] > lo and z["hi"] < hi for z in zs)


def annotate(trades, snaps):
    out = []
    for t in trades:
        q = dict(t)
        key = (t["symbol"], t["entry_t"], t["direction"], round(float(t["entry"]), 8))
        zs = snaps.get(key, [])
        q["sr_active_zones"] = len(zs)
        q["sr_block_before_tp1"] = blocked_before_tp1(t, zs)
        out.append(q)
    return out


def by_group(ts, key):
    g = defaultdict(list)
    for t in ts:
        g[t[key]].append(t)
    return {k: alt.summarize(v) for k, v in sorted(g.items())}


def by_year(ts):
    g = defaultdict(list)
    for t in ts:
        y = str(datetime.fromtimestamp(t["entry_t"] / 1000, timezone.utc).year)
        g[y].append(t)
    return {k: alt.summarize(v) for k, v in sorted(g.items())}


def pack(ts):
    return {
        "summary": alt.summarize(ts),
        "symbols": by_group(ts, "symbol"),
        "directions": by_group(ts, "direction"),
        "years": by_year(ts),
        "trades": len(ts),
    }


def main():
    raw = alt.load_market()
    filters = alt.fetch_filters()
    trades = build_trades(raw, filters)
    snaps = zone_snapshots(raw, trades)
    ann = annotate(trades, snaps)
    filtered = [t for t in ann if not t["sr_block_before_tp1"]]

    baseline = pack(ann)
    sr_filtered = pack(filtered)
    removed = [t for t in ann if t["sr_block_before_tp1"]]

    out = {
        "strategy": "TRACK_B_V1_0_FROZEN + 15/25/60 + selected SR clear-to-TP1 filter",
        "test_type": "preselected alt4 symbol OOS; no post-OOS tuning",
        "universe": list(alt.SYMS),
        "rule": "reject Track B trade when any already-confirmed active 4H/1D SR zone lies between entry and Track-B TP1",
        "sr_engine": "SR Reclaim v1 neutral HTF body-edge zones; confirmed information only at entry",
        "evaluation_period": {"start_ms": alt.EVAL_START_MS, "end_ms": alt.EVAL_END_MS},
        "costs": {"fee_bps": alt.FEE_BPS, "slippage_bps": alt.SLIPPAGE_BPS},
        "baseline": baseline,
        "sr_filtered": sr_filtered,
        "removed_count": len(removed),
        "kept_fraction": len(filtered) / len(ann) if ann else None,
        "annotated_trades": ann,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")

    print("BASELINE", json.dumps(baseline["summary"]), flush=True)
    print("FILTERED", json.dumps(sr_filtered["summary"]), flush=True)
    print("KEPT", len(filtered), "/", len(ann), flush=True)


if __name__ == "__main__":
    main()
