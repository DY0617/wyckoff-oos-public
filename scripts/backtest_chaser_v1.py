"""Original Chaser-inspired v1: 3 variants + identical execution cost stress.

Data adapters taken from the existing, separate ARM research branch.
No exchange credentials, no live trading, no production paths changed.
"""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import arm_v1_swing_core as arm
import chaser_v1_core as chaser
from backtest_arm_v1_swing import (
    STOCKS, CRYPTO, VISION, month_range, retrieve_zip, funding_rows,
    collect_stocks, collect_crypto
)

UTC=timezone.utc


def funding_history(start,end):
    out={}
    for sym in CRYPTO:
        values=[]
        for y,m in month_range(start,end-timedelta(milliseconds=1)):
            url=f"{VISION}/fundingRate/{sym}/{sym}-fundingRate-{y:04d}-{m:02d}.zip"
            raw=retrieve_zip(url)
            q=funding_rows(raw)
            if not q:
                raise RuntimeError("Missing/empty funding archive "+url)
            values.extend(q)
        out[sym]=sorted(set(values))
        print("FUNDING",sym,len(out[sym]),flush=True)
    return out


def summarize_splits(trades):
    mid=datetime(2024,1,1,tzinfo=UTC).timestamp()*1000
    forafter=lambda ts:ts>=mid
    splits={}
    for name,pred in (("pre2024",lambda ts:ts<mid),("2024plus",forafter)):
        rows=[x for x in trades if pred(x["entry_t"])]
        gain=sum(x["pnl"] for x in rows if x["pnl"]>0)
        loss=-sum(x["pnl"] for x in rows if x["pnl"]<0)
        splits[name]={"trades":len(rows),"pnl":sum(x["pnl"] for x in rows),
                      "pf":gain/loss if loss else None,
                      "avg_r":sum(x["r"] for x in rows)/len(rows) if rows else None}
    return splits


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--market",choices=("crypto","stock"),required=True)
    parser.add_argument("--start",default="2021-09-28")
    parser.add_argument("--end",default=None)
    parser.add_argument("--out",default=None)
    args=parser.parse_args()
    end_str=args.end or ("2026-04-01" if args.market=="stock" else "2026-09-28")
    start=datetime.fromisoformat(args.start).replace(tzinfo=UTC)
    end=datetime.fromisoformat(end_str).replace(tzinfo=UTC)
    if end<=start:
        raise ValueError("Invalid evaluation period")
    warmup=start-timedelta(days=520)
    print("SOURCE",args.market,start.isoformat(),end.isoformat(),flush=True)
    raw=collect_stocks(warmup,end) if args.market=="stock" else collect_crypto(warmup,end)
    packs={sym:arm.prepare(arr,args.market) for sym,arr in raw.items()}
    funding=funding_history(start,end) if args.market=="crypto" else {}
    low=int(start.timestamp()*1000);high=int(end.timestamp()*1000)
    result={"name":"chaser_inspired_v1_frozen","market":args.market,
            "period":{"start":args.start,"end_exclusive":end_str},
            "initial_cash":20000,"description":"Independent price breakout continuation: not AGOS Chaser logic",
            "variants":{}, "parameters":chaser.PARAMS,
            "costs":{"default_fee_slippage_each_fill":0.0006,
                     "stress_fee_slippage_each_fill":0.001,
                     "funding": "historical rate, hourly-close proxy" if args.market=="crypto" else None},
            "limitations":["No claim of AGOS Chaser proprietary strategy replication.",
                           "Current stock universe is post-selected and cannot establish 20-year OOS robustness.",
                           "Subperiod reports are diagnostics only; no claim of unseen untouched OOS.",
                           "Crypto mark/funding, gap and intra-hour ambiguity require higher-resolution checks.",
                           "No live order execution or production integrations."]}
    for variant in chaser.VARIANTS:
        report=chaser.simulate(packs,args.market,variant,low,high,cost=.0006,funding=funding)
        stress=chaser.simulate(packs,args.market,variant,low,high,cost=.0010,funding=funding)
        result["variants"][variant]={
            "baseline":report["metrics"],
            "extra_4bps_per_side":stress["metrics"],
            "period_splits":summarize_splits(report["trades"]),
            "trades":report["trades"],
            "equity_curve":report["curve"]
        }
        print("RESULT",args.market,variant,json.dumps({
            "trades":report["metrics"]["trades"],
            "return_pct":report["metrics"]["net_return_pct"],
            "mtm_dd":report["metrics"]["max_mtm_dd_pct"],
            "pf":report["metrics"]["profit_factor"],
            "avg_r":report["metrics"]["avg_r"],
            "stress_return_pct":stress["metrics"]["net_return_pct"],
            "splits":result["variants"][variant]["period_splits"]},ensure_ascii=False),
            flush=True)
    path=Path(args.out or f"data/validation/chaser_inspired_v1_{args.market}.json")
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print("COMPLETED",path,flush=True)


if __name__=="__main__":
    main()
