"""Run v10 range-expansion study on 3 disjoint instrument cohorts.

Fully predeclared 8 signal families, equal v8 portfolio execution,
6bp vs 10bp per side cost, per-year / symbol / long-short attribution.
"""
import argparse,json
from datetime import datetime,timedelta,timezone
from pathlib import Path
from collections import defaultdict

import arm_v1_swing_core as arm
import entry_expansion_v10_core as core
from backtest_arm_v1_swing import collect_stocks,collect_crypto
from backtest_stacker_regime_v7 import collect_new_futures,HOLDOUT,HOLDOUT_WITH_REFERENCE
from backtest_agos_stacker_v1 import funding_history

UTC=timezone.utc


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cohort",choices=("known_crypto","new_crypto","stock"),required=True)
    p.add_argument("--out",default=None)
    args=p.parse_args()
    market="stock" if args.cohort=="stock" else "crypto"
    if args.cohort=="known_crypto":
        start=datetime(2021,9,28,tzinfo=UTC)
        end=datetime(2026,9,28,tzinfo=UTC)
        syms=["BTCUSDT","ETHUSDT"]
        raw=collect_crypto(start-timedelta(days=520),end)
    elif args.cohort=="new_crypto":
        start=datetime(2022,6,1,tzinfo=UTC)
        end=datetime(2026,9,28,tzinfo=UTC)
        syms=list(HOLDOUT)
        raw=collect_new_futures(HOLDOUT_WITH_REFERENCE,start-timedelta(days=520),end)
    else:
        start=datetime(2021,9,28,tzinfo=UTC)
        end=datetime(2026,4,1,tzinfo=UTC)
        syms=None
        raw=collect_stocks(start-timedelta(days=520),end)
    packs={s:arm.prepare(z,market) for s,z in raw.items()}
    symbols=sorted(s for s in packs if s!="SPY") if market=="stock" else syms
    benchmark=packs["SPY" if market=="stock" else "BTCUSDT"]
    cache={}
    for s in symbols:
        cache[s]=core.precompute_signals(packs[s],benchmark,market,
                                         is_benchmark=(s=="BTCUSDT" and market=="crypto"))
        print("SIGNALS",args.cohort,s,{mode:len(cache[s][mode]) for mode in core.MODES},
              flush=True)
    funding=funding_history(symbols,start,end) if market=="crypto" else {}
    start_ms=int(start.timestamp()*1000)
    end_ms=int(end.timestamp()*1000)
    duration_years=(end-start).total_seconds()/(365.25*86400)
    report={
        "strategy":"Entry First v10 new confirmed 4H range expansion and participation research",
        "frozen_manifest":"strategy/entry_expansion_v10_frozen.md",
        "cohort":args.cohort,"market":market,
        "period":{"start":start.date().isoformat(),"end_exclusive":end.date().isoformat()},
        "symbols":symbols,"parameters":core.PARAMS,
        "initial_equity":20000.,
        "variants":{},
        "design_restrictions":[
            "Same v8 portfolio with frozen 2R TP, 0.5% maximum planned stop risk including fee stress",
            "No DCA, leverage expansion, chasing, partial profits or live order routing",
            "Same symbol calendar data seen in past work; early-late cohorts are chronological diagnostics NOT blind OOS",
            "Stock survivorship, corporate actions and underlying execution proxy limitations",
            "Funding and crypto mark prices approximate, 1H OHLC stop-first but not intrahour order replay",
            "1H-close marked drawdown can understate actual intrahour extremes",
            "Binance queue depth, spread spikes, forced liquidation and outages not simulated",
            "Only retrospective research; no Supabase/Telegram/exchange code touched",
        ]
    }
    for mode in core.MODES:
        base=core.simulate(packs,market,mode,start_ms,end_ms,cost=.0006,
                           funding=funding,trade_symbols=syms,precomputed=cache)
        stress=core.simulate(packs,market,mode,start_ms,end_ms,cost=.001,
                             funding=funding,trade_symbols=syms,precomputed=cache)
        b=base["metrics"];s=stress["metrics"]
        years=b["by_year"]
        early=sum(v["pnl"] for k,v in years.items() if int(k)<2024)
        late=sum(v["pnl"] for k,v in years.items() if int(k)>=2024)
        count_early=sum(v["n"] for k,v in years.items() if int(k)<2024)
        count_late=sum(v["n"] for k,v in years.items() if int(k)>=2024)
        sides={}
        for side in ("LONG","SHORT"):
            xx=[x for x in base["trades"] if x["side"]==side]
            sides[side]={"trades":len(xx),"pnl":sum(x["pnl"] for x in xx)}
        ret=b["return_pct"]
        cagr_pct=100*((1+ret/100)**(1/duration_years)-1) if ret>-100 else -100
        attrs={"early_trade_entry_year_profit":early,"early_trade_count":count_early,
               "late_trade_entry_year_profit":late,"late_trade_count":count_late,
               "by_side":sides,"cagr_pct":cagr_pct}
        report["variants"][mode]={"nominal":b,"cost_stress":s,"audit":attrs,
                                   "trades":base["trades"],"marked_curve":base["curve"]}
        print("RESULT",args.cohort,mode,json.dumps({
            "n":b["trade_count"],"return_pct":ret,"cagr_pct":cagr_pct,
            "pf":b["pf"],"drawdown_pct":b["max_mtm_dd_pct"],
            "cost_stress_pct":s["return_pct"],"avg_r":b["avg_net_r"],
            "mae":b["avg_mae_r"],"mfe":b["avg_mfe_r"],
            "hit_2r":b["tp2_rate"],"rejects":b["rejects"],
            "early_pnl":early,"late_pnl":late,
            "sides":sides,"years":years,
            "symbols":b["by_symbol"],
        },ensure_ascii=False),flush=True)
    out=Path(args.out or f"data/validation/entry_expansion_v10_{args.cohort}.json")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("COMPLETED",out,flush=True)


if __name__=="__main__":main()
