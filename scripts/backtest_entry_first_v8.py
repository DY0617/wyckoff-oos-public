"""Entry First v8 evaluation on existing, new crypto instruments and US RTH.

Frozen five signal families, 2R target, no averaging, 0.5% risk each,
cost stress, MAE/MFE, per-year and per-symbol metrics. No live orders.
"""
import argparse,json
from datetime import datetime,timedelta,timezone
from pathlib import Path

import arm_v1_swing_core as arm
import entry_first_v8_core as v8
from backtest_arm_v1_swing import collect_stocks,collect_crypto
from backtest_stacker_regime_v7 import collect_new_futures,HOLDOUT,HOLDOUT_WITH_REFERENCE
from backtest_agos_stacker_v1 import funding_history

UTC=timezone.utc

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--cohort",choices=("known_crypto","new_crypto","stock"),required=True)
    ap.add_argument("--out",default=None)
    a=ap.parse_args()
    market="stock" if a.cohort=="stock" else "crypto"
    if a.cohort=="known_crypto":
        start=datetime(2021,9,28,tzinfo=UTC)
        end=datetime(2026,9,28,tzinfo=UTC)
        syms=["BTCUSDT","ETHUSDT"]
        raw=collect_crypto(start-timedelta(days=520),end)
    elif a.cohort=="new_crypto":
        start=datetime(2022,6,1,tzinfo=UTC)
        end=datetime(2026,9,28,tzinfo=UTC)
        syms=list(HOLDOUT)
        raw=collect_new_futures(HOLDOUT_WITH_REFERENCE,start-timedelta(days=520),end)
    else:
        start=datetime(2021,9,28,tzinfo=UTC)
        end=datetime(2026,4,1,tzinfo=UTC)
        syms=None
        raw=collect_stocks(start-timedelta(days=520),end)
    packs={s:arm.prepare(rows,market) for s,rows in raw.items()}
    symbols=(sorted(x for x in packs if x!="SPY") if market=="stock" else syms)
    cache={s:v8.precompute_signals(packs[s],market) for s in symbols}
    for s,bank in cache.items():
        print("SIGNALS",s, {v:len(bank[v]) for v in v8.MODES},flush=True)
    funding=funding_history(symbols,start,end) if market=="crypto" else {}
    lo=int(start.timestamp()*1000)
    hi=int(end.timestamp()*1000)
    report={
        "strategy":"Entry First v8 independent fixed-risk signal-quality research",
        "cohort":a.cohort,"market":market,
        "start":start.date().isoformat(),"end_exclusive":end.date().isoformat(),
        "symbols":symbols,"initial_equity":v8.START_EQUITY,
        "variants":{},"parameters":v8.PARAMS,
        "frozen_modes":list(v8.MODES),
        "common_rules":{
           "position":"no DCA, one fixed stop, single full exit at +2R or stop/time",
           "risk":"0.5% max initially planned loss per trade including stressed fee reserve",
           "max_concurrent":3,"max_gross_notional_per_trade":"70% marked equity",
           "fees_slippage":"6bps each entry/exit side nominal; 10bps cost stress",
           "intrabar":"existing stop first on ambiguous OHLC; no same-entry-bar TP",
           "excursions":"MAE/MFE are OHLC-based proxies; no false favorable wick credited on stop bar",
           "crypto_funding":"settled funding rate charged using hourly close proxy"
        },
        "limitations":[
          "These dates overlap prior strategy research; not an unseen calendar OOS",
          "BNB SOL XRP only are new symbol holdouts, not time-based OOS",
          "Selected contemporary US equity universe is survivorship/postselection biased",
          "Stock split detection heuristic and cash-to-stock-futures basis may be inaccurate",
          "No margin liquidation, precise orderbook, slippage spikes or real gap path",
          "MDD sampled at 1H closes; extreme MAE/MFE order within 1H candle unknown",
          "No Binance API, Telegram, Supabase or live settings are modified"
        ]}
    for mode in v8.MODES:
        x=v8.simulate(packs,market,mode,lo,hi,cost=.0006,funding=funding,
                      trade_symbols=syms,precomputed=cache)
        stress=v8.simulate(packs,market,mode,lo,hi,cost=.001,funding=funding,
                           trade_symbols=syms,precomputed=cache)
        m=x["metrics"];ms=stress["metrics"]
        report["variants"][mode]={
           "baseline":m,"stress":ms,
           "trades":x["trades"],"equity_curve":x["curve"]
        }
        print("RESULT",a.cohort,mode,json.dumps({
            "trades":m["trade_count"],"candidates":m["candidates"],
            "rejected":m["rejects"],
            "return_pct":m["return_pct"],"pf":m["pf"],
            "mdd_pct":m["max_mtm_dd_pct"],"win_rate":m["win_rate"],
            "avg_r":m["avg_net_r"],"avg_mae_r":m["avg_mae_r"],
            "avg_mfe_r":m["avg_mfe_r"],"median_mae_r":m["median_mae_r"],
            "tp_rate":m["tp2_rate"],
            "stress_return":ms["return_pct"],
            "annual":m["by_year"],"by_symbol":m["by_symbol"]
        },ensure_ascii=False),flush=True)
    out=Path(a.out or f"data/validation/entry_first_v8_{a.cohort}.json")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("COMPLETED",out,flush=True)

if __name__=="__main__":main()
