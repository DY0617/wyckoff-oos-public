"""Compare original static exit and fresh independently risked post-TP retest variants.

Only reads existing trusted Binance Vision / HuggingFace historical adapters.
No production integration; include full trade ledger and cost-stress results.
"""
import argparse,json
from datetime import datetime,timedelta,timezone
from pathlib import Path
import arm_v1_swing_core as arm
from backtest_arm_v1_swing import collect_crypto,collect_stocks,CRYPTO
from backtest_agos_stacker_v1 import funding_history
import stacker_retest_v5_core as model


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--market",required=True,choices=("stock","crypto"))
    ap.add_argument("--start",default="2021-09-28")
    ap.add_argument("--end",default=None)
    ap.add_argument("--out",default=None)
    a=ap.parse_args()
    start=datetime.fromisoformat(a.start).replace(tzinfo=timezone.utc)
    end=datetime.fromisoformat(a.end or (
        "2026-09-28" if a.market=="crypto" else "2026-04-01")).replace(tzinfo=timezone.utc)
    if start>=end:raise ValueError("start must precede end")
    warmup=start-timedelta(days=520)
    raw=(collect_crypto(warmup,end) if a.market=="crypto" else collect_stocks(warmup,end))
    packs={s:arm.prepare(rows,a.market) for s,rows in raw.items()}
    funding=funding_history(CRYPTO,start,end) if a.market=="crypto" else {}
    lo=int(start.timestamp()*1000);hi=int(end.timestamp()*1000)
    report={"strategy":"Stacker v5 independent post-TP retest",
            "period":{"start":a.start,"end_exclusive":end.date().isoformat()},
            "market":a.market,"initial_equity":model.START_EQUITY,
            "modes":list(model.MODES),"variants":{},
            "research_contract":{
                "entry":"old frozen structural 4H BB and confirmed daily EMA200 gate",
                "parent_exit":"100% at frozen EMA TP; no stop widening, initial bounded DCA",
                "retest":"After parent TP: 1H retest of original TP -/+ 1ATR, directional CLV>=.65, EMA20 reclaim and 0.25ATR recovery",
                "execution":"New separate trade no earlier than NEXT 1H OPEN after retest closes",
                "fresh_stop":"past six COMPLETED 1H swing lows/highs +/-0.25 1H ATR",
                "fresh_tp":"full exit at +2R, BE on close beyond +1R, time-limited",
                "fresh_risk":"0.375% of marked account equity INCLUDING estimated 10bp exit + entry fees",
                "max_concurrent":2,"max_retests_per_parent":1,
                "retest_expiry_candles":model.WATCH_HOURS[a.market],
                "child_expiry_candles":model.CHILD_MAX_HOURS[a.market],
                "costs_per_side":{"nominal":.0006,"stress":.0010}
            },
            "limitations":[
                "Only known past periods; results are NOT untouched OOS",
                "Stock current-universe lookahead/survivorship bias; no survivorship correction",
                "Hourly-close MTM MDD misses intrahour excursion and stop gaps",
                "Futures funding charged with historic rates and hourly close quantity proxy",
                "Live order book, market impact, liquidations, exact futures margin absent",
                "No exchange orders/Telegram/Supabase code changed"
            ]}
    for mode in model.MODES:
        nominal=model.simulate(packs,a.market,mode,lo,hi,cost=.0006,funding=funding)
        stressed=model.simulate(packs,a.market,mode,lo,hi,cost=.0010,funding=funding)
        report["variants"][mode]={
            "nominal":nominal["metrics"],"cost_stress_10bps":stressed["metrics"],
            "trades":nominal["trades"],"curve":nominal["curve"]
        }
        print("RESULT",a.market,mode,json.dumps({
             "trade_count":nominal["metrics"]["trades"],
             "parents":nominal["metrics"]["parents"],
             "children":nominal["metrics"]["children"],
             "return_pct":nominal["metrics"]["return_pct"],
             "profit_factor":nominal["metrics"]["pf"],
             "mtm_dd":nominal["metrics"]["max_mtm_dd_pct"],
             "stress_return_pct":stressed["metrics"]["return_pct"],
             "child_pnl":nominal["metrics"]["child_pnl"],
             "child_pf":nominal["metrics"]["child_pf"],
             "retest_signals":nominal["metrics"]["confirmed_retests"],
             "years":nominal["metrics"]["by_year"]
        },ensure_ascii=False),flush=True)
    path=Path(a.out or f"data/validation/stacker_retest_v5_{a.market}.json")
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print("COMPLETED",path,flush=True)

if __name__=="__main__":main()
