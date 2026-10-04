import json
from collections import defaultdict
from pathlib import Path

import backtest_track_b_crypto_runner_ratio_exact_v1 as base
import backtest_wyckoff_crypto_exact_conservative as bt
import wyckoff_status as w
import backtest_sr_reclaim_v1_crypto as sr

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/validation/track_b_sr_filter_ab_core4_v1.json"

F1, F2 = 0.15, 0.25  # frozen selected 15/25/60 management


def build_track_b_trades(raw):
    cache = {}
    for s in base.SYMS:
        D = w.enrich([dict(x) for x in raw[s]["1d"]])
        H = w.enrich([dict(x) for x in raw[s]["4h"]])
        M = [dict(x) for x in raw[s]["15m"]]
        cache[s] = (D, H, M)

    bt._CACHE.clear()
    bt.dataset = lambda sym: cache[sym]
    bt.symbol_filters = lambda sym: base.FUTURES_FILTERS[sym]
    old = bt.RISK
    bt.RISK = base.RISK
    trades = []
    try:
        for s in base.SYMS:
            r = bt.simulate(
                s, base.A_OFF, {}, base.EVAL_START_MS, base.EVAL_END_MS,
                base.FEE_BPS, base.SLIPPAGE_BPS,
                a_mode="snapshot", b_runner_mode="pivot", b_scale_mode="30_30_40"
            )
            ts = [
                {"symbol": s, **t}
                for t in r["trades"]
                if t["track"] == "B" and t["reason"] != "OPEN_MARK"
            ]
            trades += ts
            print("BASE_TRADES", s, len(ts), flush=True)
    finally:
        bt.RISK = old
    return sorted(trades, key=lambda x: (x["entry_t"], x["symbol"]))


def zone_snapshots_for_trades(raw, trades):
    by_sym = defaultdict(list)
    for t in trades:
        by_sym[t["symbol"]].append(t)

    out = {}
    for sym, ts in by_sym.items():
        m15 = [
            {**x, "ct": x["t"] + 15 * 60_000}
            for x in raw[sym]["15m"]
        ]
        events = sr.zone_events(m15)
        zones = []
        eidx = 0
        next_zone_id = 1
        for t in sorted(ts, key=lambda x: x["entry_t"]):
            now = t["entry_t"]
            while eidx < len(events) and events[eidx]["known_t"] <= now:
                next_zone_id = sr.add_event(zones, events[eidx], next_zone_id)
                eidx += 1
            out[(sym, t["entry_t"], t["direction"], round(float(t["entry"]), 8))] = sr.snapshot_active(zones, now)
    return out


def overlaps(z, a, b):
    lo, hi = sorted((a, b))
    return not (z["hi"] < lo or z["lo"] > hi)


def zone_between_long(z, a, b):
    lo, hi = sorted((a, b))
    return z["lo"] > lo and z["lo"] < hi


def zone_between_short(z, a, b):
    lo, hi = sorted((a, b))
    return z["hi"] < hi and z["hi"] > lo


def annotate(trades, snapshots):
    out = []
    for t in trades:
        q = dict(t)
        key = (t["symbol"], t["entry_t"], t["direction"], round(float(t["entry"]), 8))
        zs = snapshots.get(key, [])
        entry = float(t["entry"])
        stop = float(t["stop"])
        tp1 = float(t["tp1"]) if t.get("tp1") is not None else None
        tp2 = float(t["target"])

        backing = any(overlaps(z, entry, stop) for z in zs)

        if t["direction"] == "LONG":
            block_tp1 = any(zone_between_long(z, entry, tp1) for z in zs) if tp1 is not None else False
            block_tp2 = any(zone_between_long(z, entry, tp2) for z in zs)
        else:
            block_tp1 = any(zone_between_short(z, entry, tp1) for z in zs) if tp1 is not None else False
            block_tp2 = any(zone_between_short(z, entry, tp2) for z in zs)

        target_in_zone = any(z["lo"] <= tp2 <= z["hi"] for z in zs)

        q["sr_active_zones"] = len(zs)
        q["sr_backing_zone"] = backing
        q["sr_block_before_tp1"] = block_tp1
        q["sr_block_before_tp2"] = block_tp2
        q["sr_tp2_in_zone"] = target_in_zone
        out.append(q)
    return out


def summarize_selected(raw_trades):
    replayed = [base.replay(t, F1, F2) for t in raw_trades]
    return base.summarize(replayed)


def grouped(raw_trades, key):
    g = defaultdict(list)
    for t in raw_trades:
        g[t[key]].append(t)
    return {k: summarize_selected(v) for k, v in sorted(g.items())}


def result(name, ts, pred_desc):
    return {
        "name": name,
        "rule": pred_desc,
        "summary": summarize_selected(ts),
        "symbols": grouped(ts, "symbol"),
        "directions": grouped(ts, "direction"),
        "kept_fraction": None,
        "trades": len(ts),
    }


def main():
    raw = base.load_market()
    base_trades = build_track_b_trades(raw)
    snaps = zone_snapshots_for_trades(raw, base_trades)
    ann = annotate(base_trades, snaps)

    variants = []
    variants.append(result("baseline", ann, "no SR filter"))
    variants.append(result("backing_zone", [t for t in ann if t["sr_backing_zone"]],
                           "at least one active HTF SR zone overlaps the initial Entry-SL risk corridor"))
    variants.append(result("clear_to_tp1", [t for t in ann if not t["sr_block_before_tp1"]],
                           "no active HTF SR zone blocks price between Entry and Track-B TP1"))
    variants.append(result("clear_to_tp2", [t for t in ann if not t["sr_block_before_tp2"]],
                           "no active HTF SR zone blocks price between Entry and Track-B TP2"))
    variants.append(result("backing_and_clear_tp1",
                           [t for t in ann if t["sr_backing_zone"] and not t["sr_block_before_tp1"]],
                           "backing zone present AND no blocking SR before TP1"))
    variants.append(result("tp2_in_sr_zone", [t for t in ann if t["sr_tp2_in_zone"]],
                           "Track-B TP2 lies inside an already-active HTF SR zone"))
    variants.append(result("backing_and_tp2_in_zone",
                           [t for t in ann if t["sr_backing_zone"] and t["sr_tp2_in_zone"]],
                           "backing zone present AND Track-B TP2 lies inside active HTF SR zone"))

    n0 = len(ann)
    for v in variants:
        v["kept_fraction"] = v["trades"] / n0 if n0 else None
        print("RESULT", v["name"], json.dumps({
            "kept_fraction": v["kept_fraction"],
            "summary": v["summary"]
        }), flush=True)

    counts = {
        "total": n0,
        "with_backing": sum(t["sr_backing_zone"] for t in ann),
        "block_before_tp1": sum(t["sr_block_before_tp1"] for t in ann),
        "block_before_tp2": sum(t["sr_block_before_tp2"] for t in ann),
        "tp2_in_zone": sum(t["sr_tp2_in_zone"] for t in ann),
        "zero_active_zones": sum(t["sr_active_zones"] == 0 for t in ann),
    }

    out = {
        "strategy": "Frozen Track B signal logic + structural SR filter A/B v1",
        "management": "15/25/60 frozen selected runner allocation",
        "sr_engine": "SR Reclaim v1 zone engine; 4H+1D body-edge pivot clusters; only confirmed/known zones at trade entry",
        "period": {"start_ms": base.EVAL_START_MS, "end_ms": base.EVAL_END_MS},
        "costs": {"fee_bps": base.FEE_BPS, "slippage_bps": base.SLIPPAGE_BPS},
        "counts": counts,
        "variants": variants,
        "annotated_trades": ann,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
