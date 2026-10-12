"""Run v13 causal daily cap drift control vs v12 and passive cash-mixes.

Whole-sample output only. No live signal order routing, no post-result
parameter tuning, no implied out-of-sample status.
"""
import argparse,json
from datetime import datetime,timedelta,timezone
from pathlib import Path

import arm_v1_swing_core as arm
import tactical_allocation_v12_core as v12
import tactical_allocation_v13_core as core
from verified_spot_v12 import collect_spot
from backtest_arm_v1_swing import collect_stocks

UTC=timezone.utc
MODES=("risk_managed_gate","gate_cap","gate_cap_daily",
       "passive_25_bench","passive_50_bench")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cohort",choices=("btc_eth_spot","five_crypto_spot","stock"),required=True)
    p.add_argument("--out",default=None)
    a=p.parse_args()
    market="stock" if a.cohort=="stock" else "crypto"
    if a.cohort=="btc_eth_spot":
        start=datetime(2021,9,28,tzinfo=UTC)
        end=datetime(2026,9,28,tzinfo=UTC)
        symbols=["BTCUSDT","ETHUSDT"]
        packs=collect_spot(symbols,start-timedelta(days=520),end)
    elif a.cohort=="five_crypto_spot":
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
    report={
      "study":"V13 next-session-reactive drift cap vs passive cash benchmarks",
      "cohort":a.cohort,"market":market,"start":lo,"end_exclusive":hi,
      "price_source":("strict Binance official spot 1d archives"
                      if market=="crypto" else "selected HF stock RTH, survivorship biased"),
      "symbols":symbols,"benchmark":benchmark,
      "risk_controls":core.PARAMS,"modes":list(MODES),
      "initial_equity":core.INITIAL,"variants":{},
      "costs_per_side":{"nominal":.0006,"severe":.002},
      "cash_yield_scenario":.03,
      "limits":[
        "Not independent out-of-sample: prior v1-v12 already mined periods and assets.",
        "Daily close breach triggers sell at next day's OPEN, does not guarantee cap intraday/overnight.",
        "BTC 25 and SPY 50 cash passive are preregistered nominal-exposure proxies not exact risk-matched controls.",
        "Stock data survivorship bias, corporate action / dividends not independently repaired.",
        "No futures funding/loan/liquidation, only cash long spot for crypto.",
        "No order book, gaps beyond limits, forced liquidation, shares rounding, partial fills, market depth or taxes.",
        "3% cash yield scenario purely illustrative not real historic cash rates.",
        "Daily close MDD misses extreme intra-day drawdown."
      ]
    }
    for mode in MODES:
        nom=core.simulate(packs,market,mode,lo,hi,symbols=symbols,
                          benchmark=benchmark,cost=.0006)
        high_cost=core.simulate(packs,market,mode,lo,hi,symbols=symbols,
                                benchmark=benchmark,cost=.002)
        yield_case=core.simulate(packs,market,mode,lo,hi,symbols=symbols,
                                 benchmark=benchmark,cost=.0006,cash_annual_yield=.03)
        m=nom["metrics"]
        if mode in ("risk_managed_gate","gate_cap"):
            old=v12.simulate(packs,market,mode,lo,hi,symbols=symbols,
                             benchmark=benchmark,cost=.0006)
            for name in ("total_return_pct","cagr_pct","mdd_pct","paid_fees",
                         "execution_count","avg_exposure","max_exposure"):
                if abs(m[name]-old["metrics"][name])>1e-9:
                    raise AssertionError(f"v12 parity mismatch {mode}:{name}")
            if old["ledger"]!=nom["ledger"]:
                raise AssertionError("v12 trade ledger mismatch")
        drift=[z for z in nom["ledger"] if z.get("reason")=="PRIOR_CLOSE_DRIFT_CAP"]
        report["variants"][mode]={
          "nominal":m,"severe_20bps_side":high_cost["metrics"],
          "illustrative_idle_cash_3pct":yield_case["metrics"],
          "drift_sale_events":len(drift),
          "ledger":nom["ledger"],"daily_closing_equity":nom["curve"]
        }
        print("RESULT",a.cohort,mode,json.dumps({
          "ret":m["total_return_pct"],"cagr":m["cagr_pct"],"mdd":m["mdd_pct"],
          "n":m["execution_count"],"turnover":m["turnover_gross_over_initial"],
          "avg_exp_pct":100*m["avg_exposure"],"max_exp_pct":100*m["max_exposure"],
          "max_name_pct":100*m["max_single_name_weight"],
          "days_over_50pct":m["days_above_50pct"],
          "days_single_over_20pct":m["days_name_above_20pct"],
          "drift_sells":len(drift),
          "drift_signals":m["events"].get("drift_signals",0),
          "drift_halted":m["events"].get("drift_halted_symbol",0),
          "fee_stress_ret":high_cost["metrics"]["total_return_pct"],
          "cash_yield_ret":yield_case["metrics"]["total_return_pct"],
          "annual":{k:round(v["return_pct"],2) for k,v in m["by_year"].items()}
        },ensure_ascii=False),flush=True)
    out=Path(a.out or f"data/validation/tactical_v13_{a.cohort}.json")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    print("COMPLETED",out,flush=True)


if __name__=="__main__":
    main()
