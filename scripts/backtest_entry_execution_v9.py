"""Historical v9 entry-execution study on BTC/ETH, BNB/SOL/XRP, US stocks.

The v8 sweep signal is frozen; only ORDER EXECUTION changes.
Never infer unfilled limit profits. Conservative first-bar stop/TP path.
"""
import argparse,json
from datetime import datetime,timedelta,timezone
from pathlib import Path

import arm_v1_swing_core as arm
import entry_first_v8_core as v8
import entry_execution_v9_core as model
from backtest_arm_v1_swing import collect_stocks,collect_crypto
from backtest_stacker_regime_v7 import collect_new_futures,HOLDOUT,HOLDOUT_WITH_REFERENCE
from backtest_agos_stacker_v1 import funding_history

UTC=timezone.utc


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--cohort",choices=["known_crypto","new_crypto","stock"],required=True)
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
    names=(sorted(x for x in packs if x!="SPY") if market=="stock" else syms)
    signals={s:v8.precompute_signals(packs[s],market)["sweep"] for s in names}
    for name in names:
        print("SWEEP_SIGNALS",name,len(signals[name]),flush=True)
    funding=funding_history(names,start,end) if market=="crypto" else {}
    lo=int(start.timestamp()*1000);hi=int(end.timestamp()*1000)
    result={
       "research":"Entry First v9 frozen sweep-order placement alternatives",
       "market":market,"cohort":a.cohort,"start":start.date().isoformat(),
       "end_exclusive":end.date().isoformat(),
       "symbols":names,"starting_capital":v8.START_EQUITY,
       "frozen_variants":list(model.MODES),
       "study_contract":{
          "signal":"unaltered confirmed 4H pivot liquidity sweep from Entry First v8",
          "stop":"unchanged 4H swept extreme +/-0.20 1H ATR",
          "target":"full exit at precisely +2R from actual entry fill",
          "entry_risk":"0.5% of then-marked account including 10bps each side stress allowance",
          "order_max_concurrent":"3 open positions PLUS reserved pending limits",
          "order_validity":"8 complete 1H bars by default, 2 bars special sensitivity",
          "limit_fill":"at open if open better than limit; else at resting limit when OHLC touch",
          "same_bar_ambiguous":"STOP first, no entry-hour TP, cancel if open beyond stop",
          "no_pyramiding":True,"no_dca":True,
          "fee_slip_each_side":{"normal":.0006,"stress":.0010},
          "funding":"Binance historical funding rates using hourly close position proxy",
          "MAE_MFE":"1H OHLC excursion with stop-first, not tick replay"
       },
       "variants":{},
       "limitations":[
          "No live trading / no Supabase, Telegram or production edits",
          "Every evaluation calendar period has been viewed during v1-v8; no untouched OOS",
          "Stock universe selected with survivorship bias; individual stocks not real futures fill prices",
          "Limit price touches are assumed full fills, ignoring queue priority and partial execution",
          "No exchange order book or variable spreads, liquidation, stressed depth, stop gap fill model",
          "Same 1H candle touch sequence unknown; assume stop first when both touched",
          "Waiting limit order RESERVES exposure and can miss new signals; results include nonfills",
          "Crypto funding charged with hourly close notional proxy, approximate exit-hour settlement",
          "MTM DD only sampled at each 1H close, could understate intrahour drawdown"
       ]
    }
    for mode in model.MODES:
        x=model.simulate(packs,market,mode,lo,hi,cost=.0006,funding=funding,
                          trade_symbols=syms,precomputed=signals)
        st=model.simulate(packs,market,mode,lo,hi,cost=.001,funding=funding,
                           trade_symbols=syms,precomputed=signals)
        m=x["metrics"];ms=st["metrics"]
        result["variants"][mode]={
            "baseline":m,"higher_cost":ms,
            "trades":x["trades"],"equity_curve":x["curve"]
        }
        print("RESULT",a.cohort,mode,json.dumps({
            "trades":m["trade_count"],
            "candidates":m["candidates"],
            "submitted":m["submitted_orders"],
            "filled":m["filled_orders"],
            "fill_rate":m["fill_rate"],
            "unfilled":m["cancels"],
            "return_pct":m["return_pct"],"pf":m["pf"],
            "drawdown_pct":m["max_mtm_dd_pct"],
            "stress_return_pct":ms["return_pct"],
            "avg_net_r":m["avg_net_r"],"mae":m["avg_mae_r"],
            "mfe":m["avg_mfe_r"],"tp_rate":m["tp2_rate"],
            "years":m["by_year"],"symbols":m["by_symbol"]
        },ensure_ascii=False),flush=True)
    outfile=Path(a.out or f"data/validation/entry_execution_v9_{a.cohort}.json")
    outfile.parent.mkdir(parents=True,exist_ok=True)
    outfile.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print("COMPLETED",outfile,flush=True)


if __name__=="__main__":main()
