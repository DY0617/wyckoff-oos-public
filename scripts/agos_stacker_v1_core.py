"""Independent AGOS-inspired bounded averaging research engine.

Uses NO AGOS proprietary code. Market data must consist of completed 1H candles.
Portfolio simulator processes all symbols in timestamp order and marks every open
position to market at each event; realised-profit-only summaries are forbidden.
"""
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timezone
from math import sqrt
import statistics

FEE_SLIP = 0.0006   # fee 4bp + slippage 2bp each entry/exit
STARTING_EQUITY = 20000.0

PARAMS = {
    "bb_period": 20, "bb_sigma": 2.0,
    "first_atr_offset": 0.0, "ladder_steps_atr": [0.0, 1.0, 2.0, 3.0],
    "ladder_weights": [1.0, 1.25, 1.5, 1.75],
    "stop_atr": 4.75, "take_profit_atr": 0.70,
    "max_bars": {"crypto": 14*24, "stock": 10*7},
    "risk_fraction_per_cycle": 0.0075,
    "max_open_cycles": 2,
    "gross_notional_limit_per_cycle": 0.70,   # fraction of equity; no 30x leverage
}


def band(arr, end, period=20, sigma=2.0):
    """Only fully closed data up to and INCLUDING arr[end] enter the band."""
    if end < period - 1:
        return None
    x = [float(z["c"]) for z in arr[end-period+1:end+1]]
    mu = statistics.fmean(x)
    sd = sqrt(sum((v - mu)**2 for v in x) / len(x))
    return mu - sigma * sd, mu + sigma * sd


def regime_ok(symbol, sympack, benchmark, market, side, day):
    """Yesterday's complete market/symbol day, never the intraday current day."""
    from arm_v1_swing_core import prev_daily
    s, b = prev_daily(sympack, day), prev_daily(benchmark, day)
    if not s or not b or s.get("ema200") is None or b.get("ema200") is None:
        return False
    if side == "LONG":
        return s["c"] > s["ema200"] and b["c"] > b["ema200"]
    return market == "crypto" and s["c"] < s["ema200"] and b["c"] < b["ema200"]


def build_signals(pack, benchmark, market, symbol, mode, eval_start_ms, eval_end_ms):
    """Return first actionable 1H open for each *confirmed* 4H band cross."""
    h = pack["hour"]
    hh = pack["h4"]
    if not h or not hh:
        return {}
    opens = [b["t"] for b in h]
    out = {}
    # allow one new signal per symbol on the next hour after a closed 4H candle
    for i in range(20, len(hh)):
        a, p = hh[i], hh[i-1]
        ba, bp = band(hh, i), band(hh, i-1)
        if not ba or not bp or not a.get("atr14") or a["atr14"] <= 0:
            continue
        which = []
        if a["c"] < ba[0] and p["c"] >= bp[0]:
            which.append("LONG")
        if market == "crypto" and a["c"] > ba[1] and p["c"] <= bp[1]:
            which.append("SHORT")
        if not which:
            continue
        next_i = bisect_right(opens, a["ct"])
        if next_i >= len(h):
            continue
        bar = h[next_i]
        if not (eval_start_ms <= bar["t"] < eval_end_ms):
            continue
        for side in which:
            if mode == "stacker_regime" and not regime_ok(
                    symbol, pack, benchmark, market, side, bar["day"]):
                continue
            # Restrict same-time opposite conflict / duplicate signals deterministically
            out.setdefault(bar["t"], dict(side=side, atr=a["atr14"],
                                          signal_t=a["ct"], signal_price=a["c"]))
    return out


def entry_cycle(sym, market, side, price, atr, t, equity, mode):
    """Size entire ladder so the WORST pre-specified stop loss is bounded.

    Stop, TP and add grid are frozen at the first fill, with no unlimited averaging.
    """
    sign = 1 if side == "LONG" else -1
    stop = price - sign * PARAMS["stop_atr"] * atr
    if stop <= 0 or price <= 0:
        return None
    steps = PARAMS["ladder_steps_atr"] if mode != "single" else [0.0]
    weights = PARAMS["ladder_weights"] if mode != "single" else [1.0]
    levels = [price - sign * atr * st for st in steps]
    # Ensure all planned levels stay on the profitable/valid side of stop.
    if any(px <= 0 or sign * (px - stop) <= 0 for px in levels):
        return None
    risk_budget = equity * PARAMS["risk_fraction_per_cycle"]
    risk_per_unit = sum(w * sign * (lv - stop) for w, lv in zip(weights, levels))
    qty_unit = risk_budget / risk_per_unit
    proposed_notional = qty_unit * sum(w * lv for w, lv in zip(weights, levels))
    cap = max(0., PARAMS["gross_notional_limit_per_cycle"] * equity)
    if proposed_notional > cap and proposed_notional > 0:
        qty_unit *= cap / proposed_notional
    target_qty = [qty_unit*w for w in weights]
    fee = target_qty[0] * price * FEE_SLIP
    return {
        "symbol": sym, "market": market, "side": side, "sign": sign,
        "mode": mode, "entry_t": t, "entry_price": price, "stop": stop, "atr": atr,
        "levels": levels, "quantities": target_qty, "next_add": 1,
        "qty": target_qty[0], "cost_basis": target_qty[0]*price,
        "avg": price, "tp": price + sign * PARAMS["take_profit_atr"]*atr,
        "fees": fee, "funding": 0.0, "fills": [{"price":price,"qty":target_qty[0],"t":t}],
        "max_risk_budget": risk_budget, "bar_count": 0, "max_adds": 0,
        "entry_equity": equity, "unrealized_trough": 0.0, "entry_fee": fee,
    }


def additional_fill(pos, px, t):
    j = pos["next_add"]
    qty = pos["quantities"][j]
    pos["qty"] += qty
    pos["cost_basis"] += px * qty
    pos["avg"] = pos["cost_basis"] / pos["qty"]
    pos["fees"] += qty * px * FEE_SLIP
    pos["fills"].append(dict(price=px, qty=qty, t=t))
    pos["next_add"] += 1
    pos["max_adds"] = max(pos["max_adds"], pos["next_add"]-1)
    pos["tp"] = pos["avg"] + pos["sign"] * PARAMS["take_profit_atr"] * pos["atr"]


def close_cycle(pos, price, t, reason):
    pnl = pos["sign"] * (pos["qty"]*price - pos["cost_basis"])
    exit_fee = pos["qty"] * price * FEE_SLIP
    pnl -= pos["fees"] + exit_fee + pos["funding"]
    return {
        "symbol":pos["symbol"], "side":pos["side"],"mode":pos["mode"],
        "entry_t":pos["entry_t"],"exit_t":t,"reason":reason,
        "entry":pos["entry_price"],"avg":pos["avg"],"exit":price,
        "stop":pos["stop"],"tp":pos["tp"],"fills":len(pos["fills"]),
        "risk_budget":pos["max_risk_budget"],"pnl":pnl,
        "r":pnl/pos["max_risk_budget"],
        "fees":pos["fees"]+exit_fee,"funding":pos["funding"],
        "floating_trough":pos["unrealized_trough"],
    }


def apply_bar(pos, bar, market, is_entry_bar=False):
    """Return (exit price, reason) if closed. Keep STOP adverse-first.

    On a falling bar, limit additions lie *before* the deep hard stop,
    so additions are charged before a stop touch (except a genuine gap
    already beyond the stop at the open). TP not available in any
    candle in which a position enters or adds, to avoid free same-bar reversals.
    """
    sign = pos["sign"]
    stop = pos["stop"]
    o, hi, lo = bar["o"], bar["h"], bar["l"]
    pos["bar_count"] += 1
    # If already in a position before this bar, a stop gap fills at the opening price.
    if not is_entry_bar and sign * (o - stop) <= 0:
        return o, "GAP_STOP"
    adverse = lo if sign > 0 else hi
    filled = is_entry_bar
    while pos["next_add"] < len(pos["levels"]):
        next_level = pos["levels"][pos["next_add"]]
        if sign * (adverse - next_level) > 0:
            break
        # Opening through a resting limit gives at least the limit price;
        # stop-first gap is handled above.
        price = (min(o, next_level) if sign > 0 else max(o, next_level))
        # Even if gap is directly through stop on the *entry* bar, fill at
        # the conservative nominal limit, not an impossible better price.
        if is_entry_bar and sign * (o-stop) <= 0:
            price = next_level
        additional_fill(pos, price, bar["t"])
        filled = True
    if sign * (adverse - stop) <= 0:
        return stop, "STOP"
    if not filled:
        favorable = hi if sign > 0 else lo
        if sign * (favorable - pos["tp"]) >= 0:
            # Conservative take profit: a limit order is filled at target, not gap-open.
            return pos["tp"], "TP"
    if pos["bar_count"] >= PARAMS["max_bars"][market]:
        return bar["c"], "TIME"
    return None


def metrics(trades, curve, risk_fraction=0.0075):
    vals = [v["pnl"] for v in trades]
    wins = [v for v in vals if v > 0]
    losses = [v for v in vals if v < 0]
    eq = [q["equity"] for q in curve]
    peak = STARTING_EQUITY
    dd = 0
    for x in eq:
        peak = max(peak, x)
        dd = max(dd, (peak-x)/peak)
    return {
        "trades":len(trades),
        "win_rate":len(wins)/len(trades) if trades else None,
        "net_pnl":sum(vals),
        "net_return_pct":(eq[-1]/STARTING_EQUITY-1)*100 if eq else None,
        "profit_factor":sum(wins)/abs(sum(losses)) if losses else None,
        "max_mtm_drawdown_pct":dd*100,
        "worst_floating_pnl":min((t["floating_trough"] for t in trades),default=0.),
        "stop_count":sum("STOP" in t["reason"] for t in trades),
        "time_exit_count":sum(t["reason"]=="TIME" for t in trades),
        "max_add_count":max((t["fills"]-1 for t in trades),default=0),
        "open_equity_included":True,
    }


def simulate(raw_packs, market, mode, start_ms, end_ms, funding=None):
    """One synchronized multi-symbol simulator, portfolio-wide concurrency/risk.

    Position entry at next hour OPEN after completed signal 4H close;
    no lookahead. All simultaneous instruments resolve in alphabetical order.
    MTM includes all open floating losses; funding is settled when accrued.
    """
    if mode not in ("single", "stacker", "stacker_regime"):
        raise ValueError("unknown mode")
    bench = raw_packs["SPY" if market=="stock" else "BTCUSDT"]
    syms = sorted(s for s in raw_packs if s != "SPY") if market=="stock" else ["BTCUSDT","ETHUSDT"]
    signals = {s:build_signals(raw_packs[s],bench,market,s,mode,start_ms,end_ms)
               for s in syms}
    events = defaultdict(list)
    for s in syms:
        for b in raw_packs[s]["hour"]:
            if start_ms <= b["t"] < end_ms:
                events[b["t"]].append((s,b))
    positions, marks, entries, trades, curve = {}, {}, [], [], []
    balance = STARTING_EQUITY
    rates = funding or {}
    previous_bar_end = {s:start_ms-1 for s in syms}
    for timestamp in sorted(events):
        bars = sorted(events[timestamp],key=lambda x:x[0])
        # Close previous holdings first, then admit NEW cycles.
        # Account for hourly settlements using the most recent observed mark.
        for s, b in bars:
            marks[s]=b["c"]
            if s not in positions:
                previous_bar_end[s]=b["ct"]
                continue
            p=positions[s]
            px_reason=apply_bar(p,b,market)
            # Charge funding only while this instrument's position was held.
            # Binance futures funding timestamps are within the bar interval.
            end_t = b["ct"]
            if px_reason is not None:
                end_t = min(end_t,b["ct"])
            if market=="crypto":
                for ft, rate in rates.get(s,[]):
                    if previous_bar_end[s] < ft <= end_t and ft > p["entry_t"]:
                        p["funding"] += p["sign"] * p["qty"] * b["c"] * rate
            previous_bar_end[s]=b["ct"]
            p["unrealized_trough"]=min(p["unrealized_trough"],
                p["sign"]*(p["qty"]*b["c"]-p["cost_basis"])-p["fees"]-p["funding"])
            if px_reason is not None:
                px,reason=px_reason
                completed=close_cycle(p,px,b["ct"],reason)
                balance+=completed["pnl"]
                trades.append(completed)
                del positions[s]
        # Admit entries if account constraints pass and no current position.
        # Mark-to-market risk sizing uses current portfolio equity.
        for s,b in bars:
            if s in positions or s not in signals or timestamp not in signals[s]:
                continue
            if len(positions) >= PARAMS["max_open_cycles"] or balance <= 0:
                continue
            floating = sum(p["sign"]*(p["qty"]*marks.get(k,p["avg"])-p["cost_basis"])
                           -p["fees"]-p["funding"] for k,p in positions.items())
            equity = balance + floating
            if equity <= 0:
                continue
            x=signals[s][timestamp]
            p=entry_cycle(s,market,x["side"],b["o"],x["atr"],timestamp,equity,mode)
            if not p:
                continue
            positions[s]=p
            entries.append(dict(symbol=s,side=x["side"],entry_t=timestamp,
                                signal_t=x["signal_t"],entry=b["o"],stop=p["stop"],
                                planned_tp=p["tp"],risk_budget=p["max_risk_budget"]))
            # ENTRY candle may touch every level; still apply adverse path conservatively.
            closing=apply_bar(p,b,market,is_entry_bar=True)
            p["unrealized_trough"]=min(p["unrealized_trough"],
                 p["sign"]*(p["qty"]*b["c"]-p["cost_basis"])-p["fees"])
            if closing:
                px,reason=closing
                completed=close_cycle(p,px,b["ct"],reason)
                balance+=completed["pnl"]
                trades.append(completed)
                del positions[s]
        float_pnl = sum(p["sign"]*(p["qty"]*marks.get(s,p["avg"])-p["cost_basis"])
                        -p["fees"]-p["funding"] for s,p in positions.items())
        curve.append(dict(t=max(b["ct"] for _,b in bars), equity=balance+float_pnl,
                          realized_equity=balance,open_cycles=len(positions),
                          floating_pnl=float_pnl))
    # Explicitly liquidate all remaining positions at observed final completed bar.
    if curve:
        last_t=curve[-1]["t"]
        for s,p in list(positions.items()):
            x=marks.get(s,p["avg"])
            completed=close_cycle(p,x,last_t,"END_OF_DATA")
            trades.append(completed)
            balance+=completed["pnl"]
        curve[-1].update(equity=balance,realized_equity=balance,
                         floating_pnl=0.0,open_cycles=0)
    trades.sort(key=lambda t:(t["exit_t"],t["symbol"]))
    return {
        "mode":mode, "market":market, "parameters":PARAMS,
        "metrics":metrics(trades,curve),
        "entries":entries, "trades":trades, "equity_curve":curve,
        "limitations":["4H/1H OHLC ambiguity resolved adverse-first",
          "Per-fill 6bps fee/slippage estimated; live depth, basis and liquidations unmodelled",
          "Equity MTM uses hourly CLOSE and can understate within-hour drawdown",
          "Funding uses settled rate and hourly close proxy rather than exact mark",
          "Historical stock universe has survivorship/postselection bias",
          "No dividend, futures basis or exchange-specific leverage margin model"]
    }
