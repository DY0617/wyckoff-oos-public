"""ARM v1 Swing -- deterministic candle-close engine. Research only; no live orders."""
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import datetime, timezone
import math

COST = 0.0006  # 4 bps fee + 2 bps slippage EACH fill side
ONE_DAY_MS = 86_400_000
PARAMS = dict(rank_fraction=0.30, pullback_lookback=8, entry_life=3,
              entry_buffer_atr=0.05, stop_buffer_atr=0.25,
              min_risk_atr=0.50, max_risk_atr=4.00,
              tp1_r=2.0, tp2_r=3.5, tp1_fraction=0.50,
              max_hold_days=10, risk_fraction=0.005, portfolio_risk_cap=0.015)


def ema(values, n):
    alpha = 2.0 / (n + 1)
    out = []
    state = None
    for v in values:
        state = v if state is None else state + alpha * (v - state)
        out.append(state)
    return out


def indicators(bars):
    if not bars:
        return bars
    closes = [b["c"] for b in bars]
    for n in (20, 50, 200):
        values = ema(closes, n)
        for i, bar in enumerate(bars):
            bar["ema" + str(n)] = values[i] if i >= n else None
    atr = None
    for i, bar in enumerate(bars):
        prev_close = closes[i - 1] if i else bar["c"]
        tr = max(bar["h"] - bar["l"], abs(bar["h"] - prev_close), abs(bar["l"] - prev_close))
        atr = tr if atr is None else (13 * atr + tr) / 14
        bar["atr14"] = atr if i >= 14 else None
        for n in (20, 60):
            bar["ret" + str(n)] = closes[i] / closes[i - n] - 1 if i >= n and closes[i - n] > 0 else None
    return bars


def aggregate(bars, key):
    """OHLCV grouping preserves the final candle close time, without partial future candles."""
    groups = defaultdict(list)
    for b in bars:
        groups[key(b)].append(b)
    out = []
    for _, chunk in sorted(groups.items(), key=lambda kv: kv[1][0]["t"]):
        x = chunk[0]
        out.append(dict(t=x["t"], ct=chunk[-1]["ct"], o=x["o"],
                        h=max(b["h"] for b in chunk), l=min(b["l"] for b in chunk),
                        c=chunk[-1]["c"], v=sum(b["v"] for b in chunk),
                        day=x["day"], count=len(chunk)))
    return out


def prepare(bars, market):
    bars.sort(key=lambda b: b["t"])
    indicators(bars)
    daily = aggregate(bars, lambda b: b["day"])
    indicators(daily)
    if market == "stock":
        h4 = aggregate(bars, lambda b: (b["day"], b["session_hour"] // 4))
    else:
        h4 = aggregate(bars, lambda b: b["t"] // (4 * 3_600_000))
        h4 = [b for b in h4 if b["count"] == 4]
    indicators(h4)
    return {"hour": bars, "daily": daily, "h4": h4,
            "day_keys": [b["day"] for b in daily],
            "h4_closes": [b["ct"] for b in h4]}


def prev_daily(pack, day):
    idx = bisect_left(pack["day_keys"], day) - 1
    return pack["daily"][idx] if idx >= 0 else None


def confirmed_h4(pack, at_ms):
    idx = bisect_right(pack["h4_closes"], at_ms) - 1
    return pack["h4"][idx] if idx >= 0 else None


def stock_rank_dates(universe, benchmark):
    """Calculate the rank using only completed prior-day bars; not today's closing prices."""
    days = sorted(set(b["day"] for p in universe.values() for b in p["daily"]))
    allowed = {}
    for day in days:
        bench = prev_daily(benchmark, day)
        if bench is None or bench["ret20"] is None or bench["ret60"] is None:
            continue
        ranks = []
        for sym, pack in universe.items():
            d = prev_daily(pack, day)
            if d and d["ret20"] is not None and d["ret60"] is not None:
                ranks.append((d["ret20"] + d["ret60"], sym))
        ranks.sort(reverse=True)
        n = max(1, math.ceil(len(ranks) * PARAMS["rank_fraction"]))
        allowed[day] = set(sym for _, sym in ranks[:n]) if len(ranks) >= 10 else set()
    return allowed


def qualifies(sym, pack, benchmark, market, side, day, h4_time, stock_ranks=None):
    d = prev_daily(pack, day)
    b = prev_daily(benchmark, day)
    h4 = confirmed_h4(pack, h4_time)
    if not d or not b or not h4:
        return False
    if any(x is None for x in (d["ema50"], d["ema200"], d["ret20"], d["ret60"],
                               b["ema200"], b["ret20"], b["ret60"], h4["ema20"], h4["ema50"])):
        return False
    sign = 1 if side == "LONG" else -1
    if market == "stock" and side != "LONG":
        return False
    if sign * (b["c"] - b["ema200"]) <= 0:
        return False
    if not (sign * (d["c"] - d["ema50"]) > 0 and
            sign * (d["ema50"] - d["ema200"]) > 0):
        return False
    if not (sign * (h4["c"] - h4["ema20"]) > 0 and
            sign * (h4["ema20"] - h4["ema50"]) > 0):
        return False
    # BTC is the market benchmark, so do not require its return to beat itself.
    if not (market == "crypto" and sym == "BTCUSDT"):
        if not (sign * (d["ret20"] - b["ret20"]) > 0 and
                sign * (d["ret60"] - b["ret60"]) > 0):
            return False
    if market == "stock" and sym not in (stock_ranks or {}).get(day, set()):
        return False
    return True


def signal(bars, i, market, sym, pack, benchmark, stock_ranks):
    x = bars[i]
    if i < 200 or not x["atr14"] or not x["ema20"] or not x["ema50"]:
        return None
    prev = bars[i - 1]
    if not prev["ema20"]:
        return None
    spread = x["h"] - x["l"]
    if spread <= 0:
        return None
    atr = x["atr14"]
    for side, sign in (("LONG", 1), ("SHORT", -1)):
        if market == "stock" and sign < 0:
            continue
        if not qualifies(sym, pack, benchmark, market, side, x["day"], x["ct"], stock_ranks):
            continue
        if sign > 0:
            crosses = prev["c"] <= prev["ema20"] and x["c"] > x["ema20"] and x["c"] > prev["h"]
            clv = (x["c"] - x["l"]) / spread
            pulled = any(z.get("ema20") and z["l"] <= z["ema20"] for z in bars[max(0, i-8):i])
            entry = x["h"] + 0.05 * atr
            stop = min(z["l"] for z in bars[i-4:i+1]) - 0.25 * atr
        else:
            crosses = prev["c"] >= prev["ema20"] and x["c"] < x["ema20"] and x["c"] < prev["l"]
            clv = (x["h"] - x["c"]) / spread
            pulled = any(z.get("ema20") and z["h"] >= z["ema20"] for z in bars[max(0, i-8):i])
            entry = x["l"] - 0.05 * atr
            stop = max(z["h"] for z in bars[i-4:i+1]) + 0.25 * atr
        if not (crosses and clv >= 0.65 and pulled and stop > 0 and entry > 0):
            continue
        risk = sign * (entry - stop)
        if not (0.5 * atr <= risk <= 4.0 * atr):
            continue
        return dict(side=side, sign=sign, trigger=entry, stop=stop,
                    atr=atr, signal_t=x["ct"], until=i+3)
    return None


def record_leg(pos, fraction, price, time_ms, reason):
    pos["r"] += fraction * (pos["sign"] * (price - pos["entry"]) - COST * price) / pos["risk"]
    pos["remaining"] -= fraction
    pos["legs"].append(dict(fraction=fraction, exit_px=price, exit_t=time_ms, reason=reason))


def update_position(pos, bar, i, market):
    sign = pos["sign"]
    stop = pos["active_stop"]
    # GAP: if the stop was passed at the open, fill at actual open, not planned stop.
    if sign * (bar["o"] - stop) <= 0:
        record_leg(pos, pos["remaining"], bar["o"], bar["ct"], "GAP_STOP")
    elif (bar["l"] <= stop if sign > 0 else bar["h"] >= stop):
        record_leg(pos, pos["remaining"], stop, bar["ct"], "STOP")
    else:
        high_side = bar["h"] if sign > 0 else bar["l"]
        if pos["stage"] == 0 and sign * (high_side - pos["tp1"]) >= 0:
            record_leg(pos, 0.50, pos["tp1"], bar["ct"], "TP1")
            pos["stage"] = 1
        if pos["remaining"] > 1e-8 and sign * (high_side - pos["tp2"]) >= 0:
            record_leg(pos, pos["remaining"], pos["tp2"], bar["ct"], "TP2")
        # Move to BE after candle close only; never retroactively stop out within TP1 bar.
        if pos["remaining"] > 1e-8 and pos["stage"] == 1:
            pos["active_stop"] = pos["entry"]
    if pos["remaining"] > 1e-8:
        expired = ((i - pos["entry_index"] >= 70) if market == "stock"
                   else (bar["ct"] - pos["entry_t"] >= 10 * ONE_DAY_MS))
        if expired:
            record_leg(pos, pos["remaining"], bar["c"], bar["ct"], "TIME_10D")
    return pos["remaining"] <= 1e-8


def run_symbol(sym, pack, benchmark, market, stock_ranks=None):
    bars = pack["hour"]
    trades = []
    pos = pending = None
    for i, bar in enumerate(bars):
        if pos is not None:
            if update_position(pos, bar, i, market):
                pos["exit_t"] = bar["ct"]
                trades.append(pos)
                pos = None
            # Do not re-enter on the same candle as an exit.
            continue
        if pending is not None:
            if i > pending["until"]:
                pending = None
            else:
                hit = (bar["h"] >= pending["trigger"] if pending["sign"] > 0
                       else bar["l"] <= pending["trigger"])
                if hit:
                    # Recheck regime at the bar OPEN, before the entry could have filled.
                    if qualifies(sym, pack, benchmark, market, pending["side"],
                                 bar["day"], bar["t"] - 1, stock_ranks):
                        entry = (max(bar["o"], pending["trigger"]) if pending["sign"] > 0
                                 else min(bar["o"], pending["trigger"]))
                        risk = pending["sign"] * (entry - pending["stop"])
                        if entry > 0 and 0.5 * pending["atr"] <= risk <= 4 * pending["atr"]:
                            pos = dict(symbol=sym, market=market, side=pending["side"],
                                       sign=pending["sign"], entry=entry, entry_t=bar["t"],
                                       entry_index=i, signal_t=pending["signal_t"],
                                       stop=pending["stop"], active_stop=pending["stop"],
                                       risk=risk, tp1=entry+pending["sign"]*2*risk,
                                       tp2=entry+pending["sign"]*3.5*risk,
                                       stage=0, remaining=1.0, r=-COST*entry/risk, legs=[])
                            if update_position(pos, bar, i, market):
                                pos["exit_t"] = bar["ct"]
                                trades.append(pos)
                                pos = None
                    pending = None
                # While order is pending, don't scan for new signals.
                if pending is not None or hit:
                    continue
        pending = signal(bars, i, market, sym, pack, benchmark, stock_ranks)
    if pos is not None and bars:
        bar = bars[-1]
        record_leg(pos, pos["remaining"], bar["c"], bar["ct"], "END_OF_DATA")
        pos["exit_t"] = bar["ct"]
        trades.append(pos)
    return trades


def apply_funding(trades, by_symbol):
    """Binance settlement-rate approximation using entry notional; mark variation unavailable."""
    from bisect import bisect_left, bisect_right
    for trade in trades:
        if trade["market"] != "crypto":
            trade["funding_r"] = 0.0
            trade["net_r"] = trade["r"]
            continue
        rates = by_symbol.get(trade["symbol"], [])
        times = [x[0] for x in rates]
        total = 0.0
        for leg in trade["legs"]:
            i = bisect_left(times, trade["entry_t"])
            j = bisect_right(times, leg["exit_t"])
            total -= trade["sign"] * (trade["entry"] / trade["risk"]) * leg["fraction"] * sum(v for _, v in rates[i:j])
        trade["funding_r"] = total
        trade["net_r"] = trade["r"] + total


def portfolio(trades, risk_fraction=0.005, max_positions=3):
    """Enforce at most three overlapping positions with 0.5% initial-equity risk each."""
    accepted = []
    open_positions = []
    for tr in sorted(trades, key=lambda x: (x["entry_t"], x["symbol"])):
        open_positions = [x for x in open_positions if x["exit_t"] > tr["entry_t"]]
        if len(open_positions) >= max_positions:
            continue
        accepted.append(tr)
        open_positions.append(tr)
    ordered = sorted(accepted, key=lambda x: (x["exit_t"], x["symbol"]))
    equity = peak = 1.0
    max_dd = 0.0
    curve = []
    for tr in ordered:
        equity += risk_fraction * tr["net_r"]
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak)
        curve.append(dict(t=tr["exit_t"], equity=equity))
    return accepted, dict(equity_multiple=equity, return_pct=(equity-1)*100,
                          max_drawdown_pct=max_dd*100, curve=curve,
                          caveat="fixed initial-equity risk; closed-trade equity; portfolio cap is post-simulation")


def summary(trades):
    p = [t["net_r"] for t in trades]
    win = sum(v > 0 for v in p)
    gain = sum(v for v in p if v > 0)
    loss = -sum(v for v in p if v < 0)
    return dict(trades=len(trades), win_rate=(win/len(p) if p else None),
                net_r=sum(p), avg_r=(sum(p)/len(p) if p else None),
                profit_factor=(gain/loss if loss else None),
                negative_trades=len(p)-win)
