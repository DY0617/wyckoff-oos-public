"""Entry First v10: new economic hypothesis, 4H directional range expansion.

Breakout after genuine compression/participation is a TREND CONTINUATION
thesis, distinct from the failed mean-reversion sweep & limit v1-v9.
This module only creates causal 1H next-open orders; it delegates all
exit/portfolio accounting to the already regression-tested v8 engine.

Eight parameter-frozen ablations. Research ONLY. No live exchange actions.
"""
from bisect import bisect_right
from collections import Counter

import arm_v1_swing_core as arm
import entry_first_v8_core as engine

MODES=("range_break","compression","volume_confirm","market_regime",
       "relative_strength","compression_volume","triple_gate","followthrough")
PARAMS={
    "donchian_prior_4h":20,
    "break_buffer_4h_atr":0.10,
    "min_directional_clv":0.65,
    "range_window_4h":12,
    "compression_history_4h":60,
    "compression_quantile":0.35,
    "relative_volume_history_4h":20,
    "volume_multiplier":1.30,
    "followthrough_clv":0.55,
    "followthrough_close_atr":0.10,
    "anchor_lookback_1h":7,
    "max_market_risk_frac":0.005,
    "stop_buffer_1h_atr":0.20,
    "tp_r":2.0,
}

def quantile(xs,fraction):
    if not xs:return None
    z=sorted(xs)
    return z[int((len(z)-1)*fraction)]


def normalized_volume(candle):
    return candle["v"]/max(candle.get("count",4),1)


def compression_readings(h4):
    """Fully closed 12x4H price ranges divided by contemporaneous ATR14.

    Window ending at i. A signal at i can ONLY refer to compression[i-1]
    and its historical reference values (ending <= i-2).
    """
    out=[]
    win=PARAMS["range_window_4h"]
    for i in range(len(h4)):
        x=h4[i]
        if i<win-1 or not x.get("atr14") or x["atr14"]<=0:
            out.append(None);continue
        chunk=h4[i-win+1:i+1]
        out.append((max(b["h"] for b in chunk)-
                    min(b["l"] for b in chunk))/x["atr14"])
    return out


def squeeze_at(compressions,i):
    """Read at 4H signal close i: prior 12-bar range vs its prior 60 peers."""
    length=PARAMS["compression_history_4h"]
    prior=i-1
    if prior-length<0 or compressions[prior] is None:return None
    ref=compressions[prior-length:prior]
    if len(ref)!=length or any(x is None for x in ref):return None
    return compressions[prior]<=quantile(ref,PARAMS["compression_quantile"])


def participation_at(h4,i):
    """Use fully closed breakout bar and 20 prior 4H NORMALIZED volumes."""
    n=PARAMS["relative_volume_history_4h"]
    if i<n:return None
    prev=[normalized_volume(x) for x in h4[i-n:i]]
    return normalized_volume(h4[i])>=PARAMS["volume_multiplier"]*sum(prev)/len(prev)


def prior_day_market_ok(benchmark,day,sign):
    d=arm.prev_daily(benchmark,day)
    return bool(d and d.get("ema200") and sign*(d["c"]-d["ema200"])>0)


def prior_day_rs_ok(asset,benchmark,day,sign,is_benchmark=False):
    d=arm.prev_daily(asset,day)
    b=arm.prev_daily(benchmark,day)
    if not d or not b or d.get("ret20") is None or b.get("ret20") is None:return False
    if is_benchmark:
        # BTC cannot have positive relative strength versus itself;
        # enforce positive BTC absolute trailing return instead.
        return sign*d["ret20"]>0
    return sign*(d["ret20"]-b["ret20"])>0


def directional_breakout(h4,i,market):
    """Channel only uses completed previous 20 4H candles, not signal candle."""
    if i<max(PARAMS["donchian_prior_4h"],80):return []
    x=h4[i];atr=x.get("atr14")
    if atr is None or atr<=0 or x["h"]<=x["l"]:return []
    previous=h4[i-PARAMS["donchian_prior_4h"]:i]
    resistance=max(z["h"] for z in previous)
    support=min(z["l"] for z in previous)
    results=[]
    directions=((1,"LONG"),) if market=="stock" else ((1,"LONG"),(-1,"SHORT"))
    for sign,side in directions:
        level=resistance if sign>0 else support
        clv=((x["c"]-x["l"])/(x["h"]-x["l"]) if sign>0
             else (x["h"]-x["c"])/(x["h"]-x["l"]))
        if sign*(x["c"]-level)>=PARAMS["break_buffer_4h_atr"]*atr and (
                clv>=PARAMS["min_directional_clv"]):
            results.append({"side":side,"sign":sign,"breakout_level":level,
                            "signal_t":x["ct"],"signal_c":x["c"],
                            "break_atr":atr,"clv":clv,"day":x["day"]})
    return results


def filters_accept(mode,ctx,asset,benchmark,is_benchmark):
    if mode not in MODES:raise ValueError(mode)
    use_squeeze=mode in ("compression","compression_volume","triple_gate")
    use_volume=mode in ("volume_confirm","compression_volume","triple_gate")
    use_market=mode in ("market_regime","triple_gate")
    if use_squeeze and ctx["compressed"] is not True:return False
    if use_volume and ctx["volume_ok"] is not True:return False
    if use_market and not prior_day_market_ok(benchmark,ctx["day"],ctx["sign"]):
        return False
    if mode=="relative_strength" and not prior_day_rs_ok(
            asset,benchmark,ctx["day"],ctx["sign"],is_benchmark):
        return False
    return True


def make_signal(h,j,ctx,followthrough=False):
    if j<=0 or j>=len(h):return None
    last=h[j-1]
    atr=last.get("atr14")
    if not atr or atr<=0:return None
    anchor_bars=h[max(0,j-PARAMS["anchor_lookback_1h"]):j]
    if len(anchor_bars)<PARAMS["anchor_lookback_1h"]:return None
    sign=ctx["sign"]
    anchor=(min(x["l"] for x in anchor_bars) if sign>0
            else max(x["h"] for x in anchor_bars))
    return {
        "side":ctx["side"],"sign":sign,"anchor":anchor,
        "entry_atr":atr,"source_close":last["c"],
        "signal_t":last["ct"] if followthrough else ctx["signal_t"],
        "kind":"range_expansion_follow" if followthrough else "range_expansion",
        "structure_level":ctx["breakout_level"],
    }


def precompute_signals(asset,benchmark,market,is_benchmark=False):
    """Causal signal-to-next-OPEN adapter, no price adjustment after signals."""
    h=asset["hour"];h4=asset["h4"]
    result={k:{} for k in MODES}
    if len(h)<50 or len(h4)<100:return result
    hour_open=[x["t"] for x in h]
    compressions=compression_readings(h4)
    for i in range(80,len(h4)):
        contexts=directional_breakout(h4,i,market)
        if not contexts:continue
        j=bisect_right(hour_open,h4[i]["ct"])
        if j>=len(h):continue
        squeeze=squeeze_at(compressions,i)
        vol=participation_at(h4,i)
        for ctx in contexts:
            ctx["compressed"]=squeeze
            ctx["volume_ok"]=vol
            for mode in MODES:
                if mode=="followthrough":continue
                if not filters_accept(mode,ctx,asset,benchmark,is_benchmark):
                    continue
                sig=make_signal(h,j,ctx)
                if sig is not None:
                    result[mode].setdefault(h[j]["t"],sig)
            # Separate one-full-1H-bar forward confirmation experiment.
            # At j OPEN, followthrough candle j has NOT closed yet.
            # Only after its CLOSE may a next hour j+1 OPEN be used.
            if j+1>=len(h):continue
            bar=h[j]
            atr=bar.get("atr14")
            if not atr or atr<=0 or bar["h"]<=bar["l"]:continue
            sign=ctx["sign"]
            clv=((bar["c"]-bar["l"])/(bar["h"]-bar["l"]) if sign>0
                 else (bar["h"]-bar["c"])/(bar["h"]-bar["l"]))
            if (sign*(bar["c"]-ctx["breakout_level"])>=
                    PARAMS["followthrough_close_atr"]*atr and
                    clv>=PARAMS["followthrough_clv"]):
                sig=make_signal(h,j+1,ctx,followthrough=True)
                if sig is not None:
                    result["followthrough"].setdefault(h[j+1]["t"],sig)
    return result


def simulate(packs,market,mode,start_ms,end_ms,cost=.0006,
             funding=None,trade_symbols=None,precomputed=None):
    """Reuse exact proven v8 stops, equity, gap handling, funding, cost/MAE.

    v8's simulator expects mode 'sweep'. The supplied data contains v10
    signals in that *named slot*, making comparison of portfolio mechanics
    exact, without monkeypatching or duplication.
    """
    if mode not in MODES:raise ValueError(mode)
    syms=(sorted(s for s in packs if s!="SPY") if market=="stock"
          else sorted(trade_symbols or ["BTCUSDT","ETHUSDT"]))
    benchmark=packs["SPY" if market=="stock" else "BTCUSDT"]
    if precomputed is None:
        precomputed={s:precompute_signals(packs[s],benchmark,market,
                                         is_benchmark=s==("SPY" if market=="stock"
                                                         else "BTCUSDT"))
                     for s in syms}
    shim={s:{"sweep":precomputed[s][mode]} for s in syms}
    results=engine.simulate(packs,market,"sweep",start_ms,end_ms,cost=cost,
                            funding=funding,trade_symbols=trade_symbols,
                            precomputed=shim)
    for tr in results["trades"]:
        tr["mode"]=mode
    results["mode"]=mode
    results["source"]="v10_expansion"
    return results
