"""Rerun promising v10 stock entries with true long-only CASH reservation.

The original portfolio permits 3 x 70% equity notional without aggregate
100% cap. This isolated auditor asks: are the v10 stock headline returns
still plausible WITHOUT stock leverage/margin? The original simulator
is checked for exact parity in unbounded mode before comparing.

Uses exact same archived HF RTH data adapter and v10 signals; no
production source, live orders or notifications modified.
"""
import json,statistics
from datetime import datetime,timedelta,timezone
from pathlib import Path

import arm_v1_swing_core as arm
import entry_expansion_v10_core as strategy
import entry_first_v8_core as original
import entry_v10_audited_cash_engine as cashmodel
from backtest_arm_v1_swing import collect_stocks


UTC=timezone.utc
START=datetime(2021,9,28,tzinfo=UTC)
END=datetime(2026,4,1,tzinfo=UTC)
ORIGINAL_TARGETS={
  "compression":13.865,
  "relative_strength":12.474,
  "compression_volume":6.568
}
EVAL=("compression","relative_strength","compression_volume","range_break")


def breakdown(x):
    m=x["metrics"]
    t=sorted(x["trades"],key=lambda v:v["pnl"],reverse=True)
    y=m["by_year"]
    return {
      "n":m["trade_count"],"return_pct":m["return_pct"],
      "profit_factor":m["pf"],"mdd_pct":m["max_mtm_dd_pct"],
      "avg_net_r":m["avg_net_r"],"mae_r":m["avg_mae_r"],
      "realized_pnl":m["net_pnl"],
      "entry_year_dollars":y,
      "ex_top5_winners_USD":sum(z["pnl"] for z in t[5:]),
      "ex_top10_winners_USD":sum(z["pnl"] for z in t[10:]),
      "ex_year_2023_USD":m["net_pnl"]-y.get("2023",{}).get("pnl",0),
      "cash_scaled_entries":m["rejects"].get("cash_scaled",0),
      "cash_exhausted_entries":m["rejects"].get("cash_exhausted",0),
      "by_symbol":m["by_symbol"]
    }


def compare():
    raw=collect_stocks(START-timedelta(days=520),END)
    packs={s:arm.prepare(rows,"stock") for s,rows in raw.items()}
    bench=packs["SPY"]
    symbols=sorted(s for s in packs if s!="SPY")
    # Precompute signal bank once. No re-tuning on the known sample.
    sigs={s:strategy.precompute_signals(packs[s],bench,"stock")
          for s in symbols}
    st=int(START.timestamp()*1000)
    end=int(END.timestamp()*1000)
    report={"study":"independent v10 stock cash feasibility audit",
       "start":START.date().isoformat(),"end_exclusive":END.date().isoformat(),
       "starting_cash":20000,
       "research_only":True,
       "variants":{},
       "important_limits":[
          "No margin borrowing; realized available cash reserves all open share purchase cost and entry fees",
          "Allows fractionally sized shares; lot rounding would tighten fills further",
          "Same 1H OHLC stop-first and 2R next-open execution as original v10",
          "Earnings, dividends, split heuristics and selected-stock survivorship uncorrected",
          "No new calendar OOS; these historical instruments and dates already studied many times",
          "A cash-only stock portfolio cannot legally finance 3 times 70% of full equity without borrowing"
       ]}
    for mode in EVAL:
        cache={s:{"sweep":sigs[s][mode]} for s in symbols}
        r=original.simulate(packs,"stock","sweep",st,end,
                             cost=.0006,precomputed=cache)
        nocap=cashmodel.simulate(packs,"stock","sweep",st,end,
                                  cost=.0006,precomputed=cache,
                                  enforce_cash=False)
        if abs(r["metrics"]["return_pct"]-nocap["metrics"]["return_pct"])>1e-9 or (
            r["metrics"]["trade_count"]!=nocap["metrics"]["trade_count"]):
            raise AssertionError("cash auditor does not reproduce old uncapped engine")
        expected=ORIGINAL_TARGETS.get(mode)
        if expected is not None and abs(expected-r["metrics"]["return_pct"])>.06:
            raise AssertionError(
              f"historical v10 result mismatch for {mode}: {r['metrics']['return_pct']} vs {expected}")
        fair=cashmodel.simulate(packs,"stock","sweep",st,end,
                                 cost=.0006,precomputed=cache,
                                 enforce_cash=True)
        fair_stress=cashmodel.simulate(packs,"stock","sweep",st,end,
                                       cost=.0010,precomputed=cache,
                                       enforce_cash=True)
        report["variants"][mode]={
          "original_uncapped":breakdown(r),
          "cash_funded":breakdown(fair),
          "cash_funded_10bps_each_side":breakdown(fair_stress),
          "cash_funded_trades":fair["trades"],
          "cash_funded_equity_curve":fair["curve"]
        }
        print("AUDIT",mode,json.dumps({
          "uncapped":breakdown(r)["return_pct"],
          "cash_only":breakdown(fair)["return_pct"],
          "cash_only_fee_stress":breakdown(fair_stress)["return_pct"],
          "cash_trade_count":fair["metrics"]["trade_count"],
          "sized_down":fair["metrics"]["rejects"].get("cash_scaled",0),
          "no_cash":fair["metrics"]["rejects"].get("cash_exhausted",0),
          "cash_pnl_ex_2023":breakdown(fair)["ex_year_2023_USD"],
          "cash_pnl_ex_10_best":breakdown(fair)["ex_top10_winners_USD"]
        },ensure_ascii=False),flush=True)
    out=Path("data/validation/entry_v10_cash_feasibility.json")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    print("COMPLETED",out,flush=True)

if __name__=="__main__":compare()
