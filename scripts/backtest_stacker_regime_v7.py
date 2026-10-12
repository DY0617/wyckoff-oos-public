"""Stacker v7: regime innovation + never-before-tested asset HOLDOUTS.

Known crypto: BTC/ETH 2021-09..2026-09.
New holdout: BNB/SOL/XRP 2022-06..2026-09, with BTC reference.
Stocks: selected US RTH 2021-09..2026-03, validation only.

All datasets monthly archive OHLC, historic Binance funding proxy.
"""
import argparse,csv,io,json
from datetime import datetime,timedelta,timezone
from pathlib import Path

import arm_v1_swing_core as arm
import stacker_regime_v7_core as strategy
from backtest_arm_v1_swing import (
    collect_crypto,collect_stocks,month_range,retrieve_zip,VISION,
    normalize_exchange_ts
)
from backtest_agos_stacker_v1 import funding_history

UTC=timezone.utc
HOLDOUT=("BNBUSDT","SOLUSDT","XRPUSDT")
HOLDOUT_WITH_REFERENCE=("BTCUSDT",)+HOLDOUT


def collect_new_futures(symbols,start,end):
    """Hard fail on missing/malformed OHLC archives. No silent zero-fills."""
    result={}
    for symbol in symbols:
        arr=[]
        for y,m in month_range(start,end-timedelta(milliseconds=1)):
            url=f"{VISION}/klines/{symbol}/1h/{symbol}-1h-{y:04d}-{m:02d}.zip"
            raw=retrieve_zip(url)
            if raw is None:
                raise RuntimeError("missing monthly exchange OHLC "+url)
            count=0
            for row in csv.reader(io.StringIO(raw)):
                if not row or not row[0].isdigit():continue
                ts=normalize_exchange_ts(row[0])
                if ts<int(start.timestamp()*1000) or ts>=int(end.timestamp()*1000):
                    continue
                d=datetime.fromtimestamp(ts/1000,UTC)
                arr.append({
                  "t":ts,"ct":ts+3_600_000-1,"o":float(row[1]),
                  "h":float(row[2]),"l":float(row[3]),"c":float(row[4]),
                  "v":float(row[5]),"day":d.date().isoformat()
                })
                count+=1
            print("NEW_ASSET_MONTH",symbol,y,m,count,flush=True)
        arr.sort(key=lambda x:x["t"])
        if not arr:raise RuntimeError("No historical candles "+symbol)
        for i in range(1,len(arr)):
            # Binance monthly archive may have missing bars; do not hallucinate.
            if arr[i]["t"]<=arr[i-1]["t"]:
                raise RuntimeError("duplicate / unsorted timestamps for "+symbol)
        result[symbol]=arr
    return result


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--cohort",choices=("known_crypto","heldout_crypto","stock"),required=True)
    ap.add_argument("--out",default=None)
    a=ap.parse_args()
    market="stock" if a.cohort=="stock" else "crypto"
    if a.cohort=="known_crypto":
        start=datetime(2021,9,28,tzinfo=UTC)
        end=datetime(2026,9,28,tzinfo=UTC)
        symbols=("BTCUSDT","ETHUSDT")
        raw=collect_crypto(start-timedelta(days=520),end)
    elif a.cohort=="heldout_crypto":
        start=datetime(2022,6,1,tzinfo=UTC)
        end=datetime(2026,9,28,tzinfo=UTC)
        symbols=HOLDOUT
        raw=collect_new_futures(HOLDOUT_WITH_REFERENCE,start-timedelta(days=520),end)
    else:
        start=datetime(2021,9,28,tzinfo=UTC)
        end=datetime(2026,4,1,tzinfo=UTC)
        symbols=None
        raw=collect_stocks(start-timedelta(days=520),end)
    packs={sym:arm.prepare(rows,market) for sym,rows in raw.items()}
    funding=(funding_history(symbols,start,end) if market=="crypto" else {})
    st=int(start.timestamp()*1000)
    en=int(end.timestamp()*1000)
    print("EVALUATION",a.cohort,start.isoformat(),end.isoformat(),
          "TRADED",symbols or "29-stock RTH",flush=True)
    report={
      "strategy":"Stacker v7 frozen predeclared regime/4H rejection innovation",
      "cohort":a.cohort,"market":market,
      "from":start.date().isoformat(),"end_exclusive":end.date().isoformat(),
      "symbols":list(symbols) if symbols else "selected current US stock RTH universe",
      "starting_equity":strategy.INITIAL,
      "variant_codes":list(strategy.MODES),
      "independent_new_asset_test":a.cohort=="heldout_crypto",
      "warning":"New symbols are instrument holdout, NOT unseen future dates or independent optimized strategy",
      "costs":{"nominal_side":.0006,"stressed_side":.0010},
      "variants":{},
      "limitations":[
        "No claim to replicate proprietary AGOS Stacker settings",
        "BTC/ETH history already repeatedly researched, exploratory calibration dataset only",
        "BNB/SOL/XRP are never-before-tested in this strategy series, but same calendar period",
        "Selected US stock symbols suffer survivorship and corporate-action biases",
        "Funding historical settlement rates use 1H close mark proxy, not exact fill mark",
        "1H-close marked equity misses intrahour floating max drawdown",
        "Simulated hard stops can suffer gaps, exchange mark liquidations and order book impact",
        "No live trading, alerts, Supabase or Telegram integration"
      ]}
    for mode in strategy.MODES:
        x=strategy.simulate(packs,market,mode,st,en,fee=.0006,
                            funding=funding,trade_symbols=symbols)
        stress=strategy.simulate(packs,market,mode,st,en,fee=.0010,
                                 funding=funding,trade_symbols=symbols)
        m=x["metrics"];m2=stress["metrics"]
        report["variants"][mode]={
            "nominal":m,"stress":m2,"trades":x["trades"],
            "marked_curve":x["curve"]
        }
        print("RESULT",a.cohort,mode,json.dumps({
           "n":m["trades"],
           "ret_pct":m["net_return_pct"],
           "pf":m["profit_factor"],
           "dd":m["max_mtm_drawdown_pct"],
           "stress_ret_pct":m2["net_return_pct"],
           "skips":m["skips"],"scaled":m["lower_size_entries"],
           "annual":m["by_year"],"by_symbol":m["by_symbol"]
        },ensure_ascii=False),flush=True)
    out=Path(a.out or f"data/validation/stacker_regime_v7_{a.cohort}.json")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print("COMPLETED",out,flush=True)

if __name__=="__main__":main()
