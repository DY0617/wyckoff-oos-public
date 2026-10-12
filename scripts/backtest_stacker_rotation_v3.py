"""Compare structural EMA Stacker with one/two TP-rebuy cycles.

The single portfolio simulator reproduces baseline and 3 rotation
policies with same causal data, notional/risk limits and transaction costs.
"""
import argparse,json
from datetime import datetime,timedelta,timezone
from pathlib import Path
import arm_v1_swing_core as arm
from backtest_agos_stacker_v1 import funding_history
from backtest_arm_v1_swing import CRYPTO,collect_stocks,collect_crypto
import stacker_rotation_v3_core as cycle


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--market",choices=("crypto","stock"),required=True)
    ap.add_argument("--start",default="2021-09-28")
    ap.add_argument("--end",default=None)
    ap.add_argument("--out",default=None)
    args=ap.parse_args()
    start=datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    end=datetime.fromisoformat(args.end or (
        "2026-09-28" if args.market=="crypto" else "2026-04-01")).replace(tzinfo=timezone.utc)
    if end<=start:raise ValueError("negative or zero evaluation period")
    warmup=start-timedelta(days=520)
    raw=(collect_crypto(warmup,end) if args.market=="crypto" else collect_stocks(warmup,end))
    packs={s:arm.prepare(rows,args.market) for s,rows in raw.items()}
    funding=funding_history(CRYPTO,start,end) if args.market=="crypto" else {}
    lo=int(start.timestamp()*1000);hi=int(end.timestamp()*1000)
    report={"strategy":"Stacker v3 independent risk-capped TP/rebuy/SL lowering",
        "market":args.market,"start":args.start,"end_exclusive":end.date().isoformat(),
        "initial_capital":20000,"modes":list(cycle.MODES),
        "rotation_contract":{"partial_exit_fraction":cycle.PARTIAL,
          "max_rebuys":cycle.MAX_REBUYS,
          "rebuy_offset_atr":cycle.REBUY_DIST_ATR,
          "sl_step_atr":cycle.STOP_EXTEND_ATR,
          "sl_budget_guard":"net at stressed 10bps per fill at hard stop >= -initial cycle risk budget",
          "existing_stop_effective_on_rebuy_bar":True,
          "runner_tp_extension_atr":cycle.RUNNER_TP_DIST_ATR,
          "absolute_tp_frozen_at_first_signal":True},
        "variants":{},
        "notes":[
         "Research, not AGOS proprietary strategy. No live trades or alerts.",
         "Initial stop based on confirmed 4H S/R, target on confirmed 4H EMA20/50",
         "One-hour OHLC adverse-first; fills and funding based on approximated marks",
         "For rotate_support, skip the rebuy if no lower confirmed pivot or risk not available",
         "For rotate_lower, lower SL by 0.25ATR after rebuy only if floor risk remains safe",
         "Partial exits reduce basis, and all realized partial gains stay in marked equity",
         "Initial and recycled fees priced at 6bp and stressed 10bp per fill side",
         "A pivot is updated from completed 4H candles strictly BEFORE rebuy 1H open",
         "Gross notional cap per cycle 70%; joint cap permits simultaneous exposures",
         "Stock data historical universe has survivorship bias; future OOS required",
         "MTM DD uses hourly CLOSE; exchange liquidation not simulated; stops can gap"
        ]}
    for mode in cycle.MODES:
        v=cycle.simulate(packs,args.market,mode,lo,hi,fee=.0006,funding=funding)
        stress=cycle.simulate(packs,args.market,mode,lo,hi,fee=.001,funding=funding)
        report["variants"][mode]={
          "metrics":v["metrics"],"stress_10bps":stress["metrics"],
          "trades":v["trades"],"equity_curve":v["equity_curve"]}
        print("RESULT",args.market,mode,json.dumps({
          "trades":v["metrics"]["trades"],
          "return_pct":v["metrics"]["net_return_pct"],
          "pf":v["metrics"]["profit_factor"],
          "dd_pct":v["metrics"]["max_mtm_drawdown_pct"],
          "rotations":v["metrics"]["rotation_rebuys"],
          "sl_moves":v["metrics"]["stop_moves"],
          "stress_return_pct":stress["metrics"]["net_return_pct"],
          "years":v["metrics"]["by_year"]
        },ensure_ascii=False),flush=True)
    out=Path(args.out or f"data/validation/stacker_rotation_v3_{args.market}.json")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print("COMPLETED",out,flush=True)


if __name__=="__main__":
    main()
