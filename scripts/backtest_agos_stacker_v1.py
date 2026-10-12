"""Run AGOS-inspired Stacker v1, risk-matched non-DCA and trend-gated variant.

Reuses the existing ARM-v1 stock RTH DuckDB/HF and Binance Vision data adapters.
No keys, orders, Supabase or Telegram. Raw reports are GH Actions artifacts.
"""
import argparse
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import arm_v1_swing_core as arm
from backtest_arm_v1_swing import (
    STOCKS, CRYPTO, VISION, month_range, retrieve_zip,
    funding_rows, collect_stocks, collect_crypto
)
import agos_stacker_v1_core as stack

UTC=timezone.utc


def funding_history(symbols, start, end):
    data={}
    for symbol in symbols:
        rates=[]
        for year, month in month_range(start, end-timedelta(milliseconds=1)):
            url=f"{VISION}/fundingRate/{symbol}/{symbol}-fundingRate-{year:04d}-{month:02d}.zip"
            text=retrieve_zip(url)
            values=funding_rows(text)
            if not values:
                raise RuntimeError("Missing funding settlement history: "+url)
            rates.extend(values)
        data[symbol]=sorted(set(rates))
        print("FUNDING",symbol,len(data[symbol]),flush=True)
    return data


def by_year(trades):
    groups=defaultdict(list)
    for t in trades:
        year=datetime.fromtimestamp(t["entry_t"]/1000,UTC).year
        groups[str(year)].append(t)
    return {year:dict(trades=len(rows),pnl=sum(x["pnl"] for x in rows),
                      worst=sum(sorted((x["pnl"] for x in rows))[:5]))
            for year,rows in sorted(groups.items())}


def reduce_report(report):
    curve=report["equity_curve"]
    metric=dict(report["metrics"])
    metric["yearly_by_entry"]=by_year(report["trades"])
    metric["max_simultaneous"]=max((x["open_cycles"] for x in curve),default=0)
    metric["worst_hourly_floating"]=min((x["floating_pnl"] for x in curve),default=0.0)
    metric["fees_total"]=sum(x["fees"] for x in report["trades"])
    metric["funding_total"]=sum(x["funding"] for x in report["trades"])
    metric["top10_pnl"]=sum(sorted((x["pnl"] for x in report["trades"]),reverse=True)[:10])
    metric["net_without_top10"]=metric["net_pnl"]-metric["top10_pnl"]
    metric["by_symbol"]={}
    for sym in sorted({x["symbol"] for x in report["trades"]}):
        rows=[x for x in report["trades"] if x["symbol"]==sym]
        metric["by_symbol"][sym]=dict(n=len(rows),net_pnl=sum(x["pnl"] for x in rows),
                                      win_rate=sum(x["pnl"]>0 for x in rows)/len(rows))
    return metric


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--market",required=True,choices=["stock","crypto"])
    parser.add_argument("--start",default="2021-09-28")
    parser.add_argument("--end",default=None)
    parser.add_argument("--out",default=None)
    args=parser.parse_args()
    start=datetime.fromisoformat(args.start).replace(tzinfo=UTC)
    end=datetime.fromisoformat(args.end or ("2026-04-01" if args.market=="stock"
                                          else "2026-09-28")).replace(tzinfo=UTC)
    if not start<end:
        raise ValueError("invalid evaluation bounds")
    warmup=start-timedelta(days=520)
    raw=(collect_stocks(warmup,end) if args.market=="stock"
         else collect_crypto(warmup,end))
    packs={sym:arm.prepare(bars,args.market) for sym,bars in raw.items()}
    funding=(funding_history(CRYPTO,start,end) if args.market=="crypto" else {})
    modes=("single","stacker","stacker_regime")
    reports={}
    for mode in modes:
        full=stack.simulate(packs,args.market,mode,int(start.timestamp()*1000),
                            int(end.timestamp()*1000),funding=funding)
        reports[mode]={"summary":reduce_report(full),
                       "trades":full["trades"],
                       "entries":full["entries"],
                       "equity_curve":full["equity_curve"]}
        print("RESULT",args.market,mode,
              json.dumps(reports[mode]["summary"],ensure_ascii=False),flush=True)
    result={
      "strategy":"AGOS-inspired Stacker v1 (independent, not proprietary AGOS logic)",
      "period":{"start":start.date().isoformat(),"end_exclusive":end.date().isoformat()},
      "market":args.market,"baseline":"single = SAME full cycle risk budget without DCA",
      "variants":reports,"parameters":stack.PARAMS,
      "comparison_rule":"Do not select one variant only by total PnL. Inspect MTM DD, worst trade, symbol/year breadth and sensitivity.",
      "warnings":[
        "Historical current stock selection has survivorship bias; not live-ready.",
        "Funding is included using historical rate, approximate mark, fees/slippage 6bps each side.",
        "Only 1H close MTM is measured, not intrabar drawdown; STOP first in ambiguous candles.",
        "Exchange-specific margin, funding mark and forced liquidations require further validation.",
        "No after-the-fact threshold tuning allowed on this evaluation set."
      ]
    }
    out=Path(args.out or f"data/validation/agos_stacker_v1_{args.market}.json")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print("COMPLETED",str(out),flush=True)


if __name__=="__main__":
    main()
