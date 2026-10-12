"""V12 audited SPOT revalidation and new capped/risk-off allocation arms.

Old v11 strategies are replayed WITHOUT changing their signal weights,
fill / fee structure or date cutoffs; requires exact cross-engine parity
on these original modes when cash interest is 0. New arms are separately
predeclared, never retroactively calibrated to v11 outcomes.
"""
import argparse,json,statistics
from datetime import datetime,timedelta,timezone
from pathlib import Path

import arm_v1_swing_core as arm
import tactical_allocation_v11_core as v11
import tactical_allocation_v12_core as v12
from verified_spot_v12 import collect_spot
from backtest_arm_v1_swing import collect_stocks

UTC=timezone.utc
BASELINE=tuple(v11.MODES)
NEW=("gate_weekly","gate_cap","gate_crashguard")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cohort",choices=("btc_eth_spot","five_crypto_spot","stock"),required=True)
    p.add_argument("--out",default=None)
    args=p.parse_args()
    market="stock" if args.cohort=="stock" else "crypto"
    if args.cohort=="btc_eth_spot":
        start=datetime(2021,9,28,tzinfo=UTC)
        end=datetime(2026,9,28,tzinfo=UTC)
        symbols=["BTCUSDT","ETHUSDT"]
        packs=collect_spot(symbols,start-timedelta(days=520),end)
    elif args.cohort=="five_crypto_spot":
        start=datetime(2022,6,1,tzinfo=UTC)
        end=datetime(2026,9,28,tzinfo=UTC)
        symbols=["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT"]
        packs=collect_spot(symbols,start-timedelta(days=520),end)
    else:
        start=datetime(2021,9,28,tzinfo=UTC)
        end=datetime(2026,4,1,tzinfo=UTC)
        raw=collect_stocks(start-timedelta(days=520),end)
        packs={s:arm.prepare(rows,"stock") for s,rows in raw.items()}
        symbols=sorted(s for s in packs if s!="SPY")
    benchmark="SPY" if market=="stock" else "BTCUSDT"
    lo=start.date().isoformat();hi=end.date().isoformat()
    result={"study":"V12 independent actual SPOT price audit, risk-concentration defenses",
        "cohort":args.cohort,"market":market,"start":lo,"end_exclusive":hi,
        "symbols":symbols,"benchmark":benchmark,
        "price_source":("Binance Vision MONTHLY spot 1d OHLCV" if market=="crypto"
                        else "original selected HF RTH equity intraday, aggregated"),
        "baseline_modes":list(BASELINE),"new_modes":list(NEW),
        "frozen_v12_parameters":v12.PARAMS,
        "initial_equity":20000.0,"variants":{},
        "caveats":[
          "2021-26 historical dates and all these instruments were explored v1-v11: NO independent calendar OOS",
          "Binance real spot 1d candles are now used, not price proxy from futures",
          "SPOT cash-funded long ownership does not model Binance perpetual futures funding or margin",
          "SPOT USDT trading risk, delisting/exchange access, spreads/slippage and tax remain unmodelled",
          "Contemporary selected US equity universe has severe survivorship, dividends and splits biases",
          "RTH stock settlement, true fractional share access, market impact, overnight gaps unmodelled",
          "Interest on idle cash is an illustrative flat 3% scenario, not real historic available yields",
          "Rebalance only at next observed daily OPEN; no intraday stop protection",
          "Daily close MDD may understate intraday crash and execution risk",
          "Tests and source code do not touch production, Binance order routing, Supabase or Telegram",
        ]}
    for mode in v12.MODES:
        nom=v12.simulate(packs,market,mode,lo,hi,
                          symbols=symbols,benchmark=benchmark,cost=.0006)
        stress=v12.simulate(packs,market,mode,lo,hi,
                             symbols=symbols,benchmark=benchmark,cost=.0020)
        with_yield=v12.simulate(packs,market,mode,lo,hi,
                             symbols=symbols,benchmark=benchmark,cost=.0006,
                             cash_annual_yield=.03)
        if mode in BASELINE:
            old=v11.simulate(packs,market,mode,lo,hi,
                              symbols=symbols,benchmark=benchmark,cost=.0006)
            lhs=old["metrics"];rhs=nom["metrics"]
            for metric in ("total_return_pct","mdd_pct","paid_fees","execution_count"):
                if abs(lhs[metric]-rhs[metric])>1e-7:
                    raise AssertionError(f"v11/v12 parity broken: {mode} {metric}: {lhs[metric]} vs {rhs[metric]}")
        m=nom["metrics"]; ms=stress["metrics"];yield_m=with_yield["metrics"]
        max_month_loss=0.
        last=None
        for point in nom["curve"]:
            if last is None:last=point
            # One-day closing-mark loss; does not imply intraday / gap-stop size.
            max_month_loss=min(max_month_loss,point["equity"]/last["equity"]-1)
            last=point
        result["variants"][mode]={
          "nominal":m,"higher_cost_20bps_side":ms,
          "idle_cash_3pct_scenario":yield_m,
          "max_single_day_close_loss_pct":max_month_loss*100,
          "ledger":nom["ledger"],"daily_equity":nom["curve"]
        }
        print("RESULT",args.cohort,mode,json.dumps({
           "n":m["execution_count"],"return_pct":m["total_return_pct"],
           "cagr_pct":m["cagr_pct"],"drawdown_pct":m["mdd_pct"],
           "max_equity_exposure_pct":m["max_exposure"]*100,
           "avg_exposure_pct":m["avg_exposure"]*100,
           "stress20_pct":ms["total_return_pct"],
           "cash_yield3_pct":yield_m["total_return_pct"],
           "years":{k:round(v["return_pct"],2) for k,v in m["by_year"].items()}
        },ensure_ascii=False),flush=True)
    out=Path(args.out or f"data/validation/tactical_v12_{args.cohort}.json")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding="utf-8")
    print("COMPLETED",out,flush=True)


if __name__=="__main__":main()
