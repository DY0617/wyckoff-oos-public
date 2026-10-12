"""Run frozen Stacker v2 structure exits versus the original ATR baseline.

No trading keys, no live signals. Reuses RTH/HF equity and Binance USDT-M
hourly-data adapters; executes four variants across identical date ranges.
"""
import argparse
import json
from collections import Counter
from datetime import datetime,timedelta,timezone
from pathlib import Path

import arm_v1_swing_core as arm
from backtest_agos_stacker_v1 import reduce_report, funding_history
from backtest_arm_v1_swing import STOCKS,CRYPTO,collect_stocks,collect_crypto
import stacker_structure_v2_core as core

UTC=timezone.utc
MODES=("baseline","sr_ema","sr_sr","hybrid")


def enriched(report):
    metric=reduce_report(report)
    trades=report["trades"]
    metric["by_stop_source"]=dict(Counter(x.get("stop_source","unknown") for x in trades))
    metric["by_tp_source"]=dict(Counter(x.get("tp_source","unknown") for x in trades))
    for side in ("LONG","SHORT"):
        selected=[x for x in trades if x["side"]==side]
        metric["by_side_"+side.lower()]={"n":len(selected),"pnl":sum(x["pnl"] for x in selected)}
    metric["largest_loss"]=min((x["pnl"] for x in trades),default=0.)
    metric["mean_win"]=sum(x["pnl"] for x in trades if x["pnl"]>0)/max(
        1,sum(x["pnl"]>0 for x in trades))
    metric["mean_loss"]=sum(x["pnl"] for x in trades if x["pnl"]<0)/max(
        1,sum(x["pnl"]<0 for x in trades))
    return metric


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--market",required=True,choices=["crypto","stock"])
    parser.add_argument("--start",default="2021-09-28")
    parser.add_argument("--end",default=None)
    parser.add_argument("--out",default=None)
    args=parser.parse_args()
    end_s=args.end or ("2026-09-28" if args.market=="crypto" else "2026-04-01")
    start=datetime.fromisoformat(args.start).replace(tzinfo=UTC)
    end=datetime.fromisoformat(end_s).replace(tzinfo=UTC)
    if end<=start:
        raise ValueError("positive date window required")
    raw=(collect_crypto(start-timedelta(days=520),end) if args.market=="crypto"
         else collect_stocks(start-timedelta(days=520),end))
    packs={s:arm.prepare(arr,args.market) for s,arr in raw.items()}
    funding=funding_history(CRYPTO,start,end) if args.market=="crypto" else {}
    lo=int(start.timestamp()*1000);hi=int(end.timestamp()*1000)
    report={
        "strategy":"Independent AGOS-inspired bounded Stacker v2 with support/resistance and EMA exits",
        "period":{"start":args.start,"end_exclusive":end_s},
        "market":args.market,
        "modes":MODES,
        "params":core.PARAMS,
        "initial_capital":20000,
        "variants":{},
        "provenance":"Original rules, not AGOS proprietary implementation",
        "limits":[
            "Uses frozen confirmed 4H pivots and EMAs only; no post-entry future indicators",
            "Initial stop remains fixed throughout averaging; TP absolute structure level freezes at signal",
            "Some structure variants SKIP trades with no viable structural TP and SL",
            "Benchmark is the identical initial band trigger with the original EMA200 regime gate",
            "Transaction costs 6bps/side, plus stress 10bps/side",
            "Gross marked equity includes floating PnL only at 1H CLOSE",
            "Fixed 0.75% planned total stop risk per averaging cycle, max 70% notional and two cycles",
            "No intrahour book-depth or liquidation model; weekend/overnight gap risks remain",
            "Stock universe postselected and affected by survivorship bias"
        ]
    }
    for mode in MODES:
        core.FEE_SLIP=0.0006
        first=core.simulate(packs,args.market,mode,lo,hi,funding=funding)
        core.FEE_SLIP=0.0010
        stress=core.simulate(packs,args.market,mode,lo,hi,funding=funding)
        core.FEE_SLIP=0.0006
        report["variants"][mode]={
            "baseline":enriched(first),
            "cost_plus_4bps_each_side":enriched(stress),
            "trades":first["trades"],
            "equity_curve":first["equity_curve"]
        }
        print("RESULT",args.market,mode,json.dumps({
           "trades":first["metrics"]["trades"],
           "win_rate":first["metrics"]["win_rate"],
           "ret_pct":first["metrics"]["net_return_pct"],
           "mdd_pct":first["metrics"]["max_mtm_drawdown_pct"],
           "pf":first["metrics"]["profit_factor"],
           "stress_ret_pct":stress["metrics"]["net_return_pct"],
           "stop_sources":report["variants"][mode]["baseline"]["by_stop_source"],
           "target_sources":report["variants"][mode]["baseline"]["by_tp_source"],
           "by_year":report["variants"][mode]["baseline"]["yearly_by_entry"]
           },ensure_ascii=False),flush=True)
    out=Path(args.out or f"data/validation/stacker_structure_v2_{args.market}.json")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    print("COMPLETED",out,flush=True)


if __name__=="__main__":
    main()
