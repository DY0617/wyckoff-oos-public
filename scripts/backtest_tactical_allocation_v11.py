"""V11 evaluate cash-only long tactical allocation against buy/hold baselines.

The BTC/ETH (known) and all-5 (BTC/ETH/BNB/SOL/XRP) and selected US
RTH stock universes run as SEPARATE hypothetical 20K accounts.
No leverage, no borrowing, no shorting, no futures funding included.
Prices come from USDT-M futures OHLC for the crypto *spot-like proxy*;
therefore NOT an actually executable spot/futures PnL claim.
"""
import argparse,json
from datetime import datetime,timedelta,timezone
from pathlib import Path

import arm_v1_swing_core as arm
import tactical_allocation_v11_core as core
from backtest_arm_v1_swing import collect_crypto,collect_stocks
from backtest_stacker_regime_v7 import collect_new_futures,HOLDOUT_WITH_REFERENCE

UTC=timezone.utc

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cohort",choices=["btc_eth","five_crypto","stock"],required=True)
    p.add_argument("--out",default=None)
    a=p.parse_args()
    market="stock" if a.cohort=="stock" else "crypto"
    if a.cohort=="btc_eth":
        start=datetime(2021,9,28,tzinfo=UTC)
        end=datetime(2026,9,28,tzinfo=UTC)
        syms=["BTCUSDT","ETHUSDT"]
        raw=collect_crypto(start-timedelta(days=520),end)
    elif a.cohort=="five_crypto":
        start=datetime(2022,6,1,tzinfo=UTC)
        end=datetime(2026,9,28,tzinfo=UTC)
        syms=["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT"]
        raw=collect_new_futures(tuple(sorted(set(HOLDOUT_WITH_REFERENCE+("ETHUSDT",)))),
                               start-timedelta(days=520),end)
    else:
        start=datetime(2021,9,28,tzinfo=UTC)
        end=datetime(2026,4,1,tzinfo=UTC)
        syms=None
        raw=collect_stocks(start-timedelta(days=520),end)
    packs={s:arm.prepare(rows,market) for s,rows in raw.items()}
    benchmark="SPY" if market=="stock" else "BTCUSDT"
    traded=sorted(s for s in packs if s!="SPY") if market=="stock" else syms
    start_day=start.date().isoformat();end_day=end.date().isoformat()
    print("UNIVERSE",a.cohort,start_day,end_day,",".join(traded),flush=True)
    report={"strategy":"V11 cash-funded trend and dual-momentum monthly portfolio research",
      "study":"standalone tactical asset allocation distinct from v1-v10 entry timing",
      "cohort":a.cohort,"start_day":start_day,"end_exclusive":end_day,
      "symbols":traded,"benchmark":benchmark,"initial_capital":core.INITIAL,
      "frozen_modes":list(core.MODES),"parameters":core.PARAMS,"variants":{},
      "costs_each_side":{"nominal":0.0006,"stress":0.0010,"severe":0.0020},
      "limitations":[
       "Historical evaluation date ranges repeatedly explored in previous research; NOT new future-date OOS",
       "Crypto OHLC proxy is Binance USDT-M future prices, but simulates unlevered SPOT-LIKE ownership",
       "No perpetual futures funding, mark price, margin liquidation; numbers are NOT executable USDT-M returns",
       "Cash yield is ZERO even during cash-only regime, conservative vs interest-bearing funds",
       "All holdings cash-funded with <=100% notional; trading fills at next monthly session OPEN",
       "Selected surviving US equities suffer severe survivorship/selection and dividend/split estimation biases",
       "No queue/spread-depth, taxes, brokerage fractional-share constraints, settlement T+1 buying-power restrictions",
       "Annual 1D close marked DD understates possible intraday equity troughs and crash gaps",
       "Strategy threshold tuning on these already-seen dates cannot manufacture independent OOS"
      ]}
    for mode in core.MODES:
        nom=core.simulate(packs,market,mode,start_day,end_day,
                          symbols=traded,benchmark=benchmark,cost=.0006)
        stress=core.simulate(packs,market,mode,start_day,end_day,
                             symbols=traded,benchmark=benchmark,cost=.0010)
        severe=core.simulate(packs,market,mode,start_day,end_day,
                             symbols=traded,benchmark=benchmark,cost=.0020)
        m=nom["metrics"]
        report["variants"][mode]={
             "nominal":m,"cost_stress_10bps":stress["metrics"],
             "cost_severe_20bps":severe["metrics"],
             "ledger":nom["ledger"],"daily_marked_equity":nom["curve"]
        }
        print("RESULT",a.cohort,mode,json.dumps({
           "trades":m["execution_count"],
           "return_pct":m["total_return_pct"],
           "cagr_pct":m["cagr_pct"],
           "mdd_pct":m["mdd_pct"],
           "calmar":m["calmar"],
           "exposure_pct":m["avg_exposure"]*100,
           "max_exposure_pct":m["max_exposure"]*100,
           "stress10_return_pct":stress["metrics"]["total_return_pct"],
           "stress20_return_pct":severe["metrics"]["total_return_pct"],
           "turnover":m["turnover_gross_over_initial"],
           "years":m["by_year"]
        },ensure_ascii=False),flush=True)
    pth=Path(a.out or f"data/validation/tactical_allocation_v11_{a.cohort}.json")
    pth.parent.mkdir(parents=True,exist_ok=True)
    pth.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    print("COMPLETED",pth,flush=True)

if __name__=="__main__":main()
