"""Stacker v6: preregistered 7-arm ENTRY quality and portfolio-risk study.

Runs US selected stocks and BTC/ETH with identical entry/execution backtest
adapters to prior Stacker v5 (no live integrations).
"""
import argparse,json
from datetime import datetime,timedelta,timezone
from pathlib import Path
import arm_v1_swing_core as arm
from backtest_arm_v1_swing import collect_stocks,collect_crypto,CRYPTO
from backtest_agos_stacker_v1 import funding_history
import stacker_quality_v6_core as strategy


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--market",choices=("stock","crypto"),required=True)
    ap.add_argument("--start",default="2021-09-28")
    ap.add_argument("--end",default=None)
    ap.add_argument("--out",default=None)
    args=ap.parse_args()
    start=datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    end=datetime.fromisoformat(args.end or (
        "2026-09-28" if args.market=="crypto" else "2026-04-01")).replace(tzinfo=timezone.utc)
    if not start<end:raise ValueError("start must be before end")
    warmup=start-timedelta(days=520)
    raw=collect_crypto(warmup,end) if args.market=="crypto" else collect_stocks(warmup,end)
    packs={s:arm.prepare(rows,args.market) for s,rows in raw.items()}
    funding=funding_history(CRYPTO,start,end) if args.market=="crypto" else {}
    lo=int(start.timestamp()*1000)
    hi=int(end.timestamp()*1000)
    report={
      "strategy":"Stacker v6 original predeclared entry-quality, risk-regime and cooldown ablation",
      "market":args.market,"start":args.start,"end_exclusive":end.date().isoformat(),
      "equity_initial":strategy.INITIAL,
      "modes":list(strategy.MODES),
      "frozen_settings":{
        "risk_budget":"0.75% maximum parent planned stop loss including fee reserve",
        "notional_cap":"70% of equity/cycle, two concurrent cycles",
        "entry":"completed 4H Bollinger breakout with yesterday's asset+market EMA200 regime",
        "stop":"confirmed pivot support/resistance with ATR buffer",
        "take_profit":"frozen confirmed 4H EMA20/EMA50 target, no rotation/rebuys",
        "daily_trend":"yesterday asset+benchmark EMA50 vs EMA200 and asset EMA50 improving vs 5 prior days",
        "vol_gate":"4H ATR14/4H close above own preceding 80 observations' 80th percentile",
        "reward_floor":"entry-to-frozen-target vs entry-to-hard-stop >=0.65R",
        "vol_scale":"when high volatility, risk allocation is halved; not an exposure increase",
        "cooldown":"3 portfolio losing closed cycles => skip 72 subsequent crypto hours or 35 stock RTH event hours",
        "quality_combo":"predeclared daily trend+skip high volatility+R floor",
        "costs":"nominal 6bp each side, stress 10bp each side"
      },
      "variants":{},
      "limitations":[
        "2021-2026 data were already seen in previous research, NOT independent OOS",
        "Selected stock universe has survivorship and selection biases",
        "MDD based on hourly closing marks; stop gaps/intrabar excursions may exceed it",
        "Funding uses historical rates and hourly-close notional estimate",
        "No exchange order-book, execution impact, margin/liquidation model",
        "No production integration with Supabase, Binance API, Telegram or Wyckoff tracks"
      ]
    }
    for mode in strategy.MODES:
        nom=strategy.simulate(packs,args.market,mode,lo,hi,fee=.0006,funding=funding)
        stress=strategy.simulate(packs,args.market,mode,lo,hi,fee=.001,funding=funding)
        report["variants"][mode]={"nominal":nom["metrics"],"stress":stress["metrics"],
                                  "trades":nom["trades"],"equity_curve":nom["curve"]}
        m=nom["metrics"]
        print("RESULT",args.market,mode,json.dumps({
            "n":m["trades"],"return_pct":m["net_return_pct"],
            "pf":m["profit_factor"],"dd":m["max_mtm_drawdown_pct"],
            "stress_return_pct":stress["metrics"]["net_return_pct"],
            "checks":m["checked_signals"],"skips":m["skips"],
            "vol_scaled":m["high_vol_scaled_entries"],
            "cooldowns":m["cooldown_events"],
            "years":m["by_year"],"symbol":m["by_symbol"]
        },ensure_ascii=False),flush=True)
    out=Path(args.out or f"data/validation/stacker_quality_v6_{args.market}.json")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,ensure_ascii=False))
    print("COMPLETED",out,flush=True)


if __name__=="__main__":
    main()
