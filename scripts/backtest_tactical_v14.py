"""Strategic V14 risk-on capital budgets on actual spot and US RTH stocks.

All modes fixed before results; exact prior V12 control parity mandatory.
Long-only fully funded OHLC monthly open, severe cost and yearly inspection.
"""
import argparse,json
from datetime import datetime,timedelta,timezone
from pathlib import Path

import arm_v1_swing_core as arm
import tactical_allocation_v12_core as v12
import tactical_v14_core as v14
from verified_spot_v12 import collect_spot
from backtest_arm_v1_swing import collect_stocks

UTC=timezone.utc
CONTROL=("benchmark_hold","equal_monthly","absolute_trend",
         "momentum_top","risk_managed_gate","gate_cap")
MODES=CONTROL+v14.V14_MODES

def get_data(cohort):
    market="stock" if cohort=="stock" else "crypto"
    if cohort=="btc_eth_spot":
        a=datetime(2021,9,28,tzinfo=UTC);b=datetime(2026,9,28,tzinfo=UTC)
        symbols=["BTCUSDT","ETHUSDT"]
        pack=collect_spot(symbols,a-timedelta(days=520),b)
    elif cohort=="five_crypto_spot":
        a=datetime(2022,6,1,tzinfo=UTC);b=datetime(2026,9,28,tzinfo=UTC)
        symbols=["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT"]
        pack=collect_spot(symbols,a-timedelta(days=520),b)
    else:
        a=datetime(2021,9,28,tzinfo=UTC);b=datetime(2026,4,1,tzinfo=UTC)
        raw=collect_stocks(a-timedelta(days=520),b)
        pack={s:arm.prepare(x,"stock") for s,x in raw.items()}
        symbols=sorted(s for s in pack if s!="SPY")
    return market,a,b,symbols,pack

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cohort",choices=("btc_eth_spot","five_crypto_spot","stock"),required=True)
    p.add_argument("--out",default=None)
    args=p.parse_args()
    market,start,end,symbols,packs=get_data(args.cohort)
    bench="SPY" if market=="stock" else "BTCUSDT"
    lo=start.date().isoformat();hi=end.date().isoformat()
    report={
      "research":"Tactical V14 expansion of dynamic gross-risk budgets during verified uptrends",
      "source":"true Binance SPOT 1d" if market=="crypto" else "selected surviving HF RTH stocks",
      "frozen_manifest":"strategy/tactical_v14_frozen.md",
      "cohort":args.cohort,"start":lo,"end_exclusive":hi,
      "market":market,"symbols":symbols,"benchmark":bench,
      "initial_capital":v14.INITIAL,"parameters":v14.PARAMS,
      "control_modes":list(CONTROL),"frozen_modes":list(v14.V14_MODES),
      "variants":{},
      "limitations":[
         "All calendar periods were previously explored v1-v13; there is NO truly unseen calendar OOS.",
         "Survivorship-selected stock universe and imperfect corporate actions: NOT reliable investible stock alpha.",
         "Crypto actual Binance spot only; futures funding, liquidation and margin are NOT simulated.",
         "All fills at next eligible monthly open; spreads, tax, queue and partial fills omitted.",
         "Gross and per-name percentages are monthly target weights, not hard real-time exposure guarantees.",
         "Cash yield 3pct scenario only, not a verified historic available yield.",
         "MDD from daily closing marks not intraday extremes."
       ]
    }
    for mode in MODES:
        x=v14.simulate(packs,market,mode,lo,hi,symbols=symbols,
                       benchmark=bench,cost=.0006)
        stressed=v14.simulate(packs,market,mode,lo,hi,symbols=symbols,
                             benchmark=bench,cost=.0020)
        if mode in ("risk_managed_gate","gate_cap"):
            prior=v12.simulate(packs,market,mode,lo,hi,
                               symbols=symbols,benchmark=bench,cost=.0006)
            for key in ("total_return_pct","mdd_pct","paid_fees",
                        "execution_count","avg_exposure","max_exposure"):
                if abs(x["metrics"][key]-prior["metrics"][key])>1e-9:
                    raise AssertionError(f"v14 broke prior {mode} {key}")
            if x["ledger"]!=prior["ledger"]:
                raise AssertionError(f"v14 prior {mode} original trade ledger mismatch")
        metric=x["metrics"]
        # Independent chronological (NOT unseen OOS) dates/years reporting.
        report["variants"][mode]={
            "nominal":metric,"fee_stress_20bps_side":stressed["metrics"],
            "ledger":x["ledger"],"daily_equity":x["curve"]
        }
        print("RESULT",args.cohort,mode,json.dumps({
          "return_pct":metric["total_return_pct"],
          "cagr_pct":metric["cagr_pct"],"mdd_pct":metric["mdd_pct"],
          "calmar":metric["calmar"],"avg_exposure_pct":100*metric["avg_exposure"],
          "max_exposure_pct":100*metric["max_exposure"],
          "n":metric["execution_count"],"turnover":metric["turnover_gross_over_initial"],
          "fees":metric["paid_fees"],"cost_stress_pct":stressed["metrics"]["total_return_pct"],
          "years":{y:round(z["return_pct"],2) for y,z in metric["by_year"].items()}
        },ensure_ascii=False),flush=True)
    out=Path(args.out or f"data/validation/tactical_v14_{args.cohort}.json")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("COMPLETED",out,flush=True)

if __name__=="__main__":main()
