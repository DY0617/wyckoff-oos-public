from bisect import bisect_left
import importlib

import backtest_trend_structure_v0_1_crypto as core

CONFIGS = {
    "baseline": {"vol_mult": 1.20, "retest_atr": 0.35, "break_buf_atr": 0.10, "rsi_long": 50.0, "rsi_short": 50.0},
    "vol_100": {"vol_mult": 1.00, "retest_atr": 0.35, "break_buf_atr": 0.10, "rsi_long": 50.0, "rsi_short": 50.0},
    "vol_140": {"vol_mult": 1.40, "retest_atr": 0.35, "break_buf_atr": 0.10, "rsi_long": 50.0, "rsi_short": 50.0},
    "retest_025": {"vol_mult": 1.20, "retest_atr": 0.25, "break_buf_atr": 0.10, "rsi_long": 50.0, "rsi_short": 50.0},
    "retest_050": {"vol_mult": 1.20, "retest_atr": 0.50, "break_buf_atr": 0.10, "rsi_long": 50.0, "rsi_short": 50.0},
    "break_005": {"vol_mult": 1.20, "retest_atr": 0.35, "break_buf_atr": 0.05, "rsi_long": 50.0, "rsi_short": 50.0},
    "break_015": {"vol_mult": 1.20, "retest_atr": 0.35, "break_buf_atr": 0.15, "rsi_long": 50.0, "rsi_short": 50.0},
    "rsi_loose": {"vol_mult": 1.20, "retest_atr": 0.35, "break_buf_atr": 0.10, "rsi_long": 48.0, "rsi_short": 52.0},
    "rsi_strict": {"vol_mult": 1.20, "retest_atr": 0.35, "break_buf_atr": 0.10, "rsi_long": 52.0, "rsi_short": 48.0},
}


def _find_breakout_retest(h1, pivots, i, side, cfg):
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
            ln = core.trendline(pivots, j, Aj, "falling")
            if ln is None:
                continue
            prev_ln = core.line_value(ln, j - 1)
            now_ln = core.line_value(ln, j)
            broke = (
                h1[j - 1]["c"] <= prev_ln
                and h1[j]["c"] > now_ln + cfg["break_buf_atr"] * Aj
            )
            vol_ok = h1[j]["v"] >= cfg["vol_mult"] * vma
            if not (broke and vol_ok):
                continue
            cur_ln = core.line_value(ln, i)
            retest = (
                h1[i]["l"] <= cur_ln + cfg["retest_atr"] * A
                and h1[i]["c"] > cur_ln
                and h1[i]["rsi14"] >= cfg["rsi_long"]
            )
            if retest:
                return {"line": ln, "line_now": cur_ln, "breakout_i": j}
        else:
            ln = core.trendline(pivots, j, Aj, "rising")
            if ln is None:
                continue
            prev_ln = core.line_value(ln, j - 1)
            now_ln = core.line_value(ln, j)
            broke = (
                h1[j - 1]["c"] >= prev_ln
                and h1[j]["c"] < now_ln - cfg["break_buf_atr"] * Aj
            )
            vol_ok = h1[j]["v"] >= cfg["vol_mult"] * vma
            if not (broke and vol_ok):
                continue
            cur_ln = core.line_value(ln, i)
            retest = (
                h1[i]["h"] >= cur_ln - cfg["retest_atr"] * A
                and h1[i]["c"] < cur_ln
                and h1[i]["rsi14"] <= cfg["rsi_short"]
            )
            if retest:
                return {"line": ln, "line_now": cur_ln, "breakout_i": j}
    return None


def make_signal_factory(cfg):
    def make_signal(h1, h4, ct4, low_pivots, high_pivots, i):
        x = h1[i]
        if i < max(core.REG_WINDOW - 1, 55):
            return None

        k4 = bisect_left(ct4, x["ct"] + 1) - 1
        if k4 < 0:
            return None
        side = core.regime4(h4[k4])
        if side is None:
            return None

        A = x["atr14"]
        if A is None or A <= 0:
            return None

        if side == "LONG":
            br = _find_breakout_retest(h1, high_pivots, i, "LONG", cfg)
            if br is None:
                return None
            entry = x["h"] + core.ENTRY_BUFFER_ATR * A
            lp = x.get("last_pivot_low")
            bases = [br["line_now"] - 0.40 * A, x["l"] - 0.20 * A]
            if lp is not None:
                bases.append(lp - 0.20 * A)
            sl = min(bases)
        else:
            br = _find_breakout_retest(h1, low_pivots, i, "SHORT", cfg)
            if br is None:
                return None
            entry = x["l"] - core.ENTRY_BUFFER_ATR * A
            hp = x.get("last_pivot_high")
            bases = [br["line_now"] + 0.40 * A, x["h"] + 0.20 * A]
            if hp is not None:
                bases.append(hp + 0.20 * A)
            sl = max(bases)

        risk = (entry - sl) if side == "LONG" else (sl - entry)
        if risk <= 0:
            return None
        risk_atr = risk / A
        if not (core.RISK_MIN_ATR <= risk_atr <= core.RISK_MAX_ATR):
            return {"rejected": "risk", "track": "B_BREAK_RETEST", "risk_atr": risk_atr}

        tp1 = entry + core.TP1_R * risk if side == "LONG" else entry - core.TP1_R * risk
        tp2 = entry + core.TP2_R * risk if side == "LONG" else entry - core.TP2_R * risk
        return {
            "rejected": None,
            "track": "B_BREAK_RETEST",
            "side": side,
            "entry": entry,
            "sl": sl,
            "risk": risk,
            "risk_atr": risk_atr,
            "tp1": tp1,
            "tp2": tp2,
            "meta": {
                "line": br["line_now"],
                "line_score": br["line"]["score"],
                "breakout_i": br["breakout_i"],
            },
        }

    return make_signal


def run_symbol(sym, b15, config_name, h1_override=None, h4_override=None, eval_start=None, eval_end=None):
    cfg = CONFIGS[config_name]
    original = core.make_signal
    core.make_signal = make_signal_factory(cfg)
    try:
        return core.simulate_symbol(
            sym,
            b15,
            h1_override=h1_override,
            h4_override=h4_override,
            eval_start=eval_start,
            eval_end=eval_end,
        )
    finally:
        core.make_signal = original


def metrics(ts):
    return core.metrics(ts)
