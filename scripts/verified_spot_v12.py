"""Verified Binance SPOT monthly daily OHLCV loader for portfolio v12.

Use exchange spot 1d candles, NOT USDT-M futures klines, including 520-day
EMA200 warmup. Fail closed if an expected month or day is missing; never
forward-fill prices, silently substitute futures, or omit dead symbols.
"""
import csv,io
from datetime import datetime,timedelta,timezone

import arm_v1_swing_core as arm
from backtest_arm_v1_swing import month_range,retrieve_zip,normalize_exchange_ts

SPOT_URL="https://data.binance.vision/data/spot/monthly/klines"
UTC=timezone.utc
ONE_DAY=86400000


def rows_from_archive(csv_text,sym,start,end):
    raw=[]
    seen=set()
    for row in csv.reader(io.StringIO(csv_text)):
        if not row or not row[0].strip().isdigit():
            continue
        ts=normalize_exchange_ts(row[0])
        if ts%ONE_DAY:
            raise ValueError(f"spot 1d bar not UTC-midnight {sym} {ts}")
        if not int(start.timestamp()*1000)<=ts<int(end.timestamp()*1000):
            continue
        if ts in seen:
            raise ValueError(f"spot candle duplicate {sym} {ts}")
        seen.add(ts)
        o,h,l,c,v=(float(row[k]) for k in (1,2,3,4,5))
        if not (0<l<=min(o,c)<=max(o,c)<=h and v>=0):
            raise ValueError(f"invalid spot OHLCV {sym} {ts}")
        raw.append({"t":ts,"ct":ts+ONE_DAY-1,
                    "o":o,"h":h,"l":l,"c":c,"v":v,
                    "day":datetime.fromtimestamp(ts/1000,UTC).date().isoformat()})
    return raw


def build_daily_pack(rows,sym,start,end):
    z=sorted(rows,key=lambda x:x["t"])
    if not z:
        raise ValueError(f"empty spot history {sym}")
    for a,b in zip(z,z[1:]):
        if b["t"]-a["t"]!=ONE_DAY:
            raise ValueError(f"spot daily data gap {sym} {a['day']} -> {b['day']}")
    first=int(start.timestamp()*1000)
    last=int(end.timestamp()*1000)-ONE_DAY
    if z[0]["t"]>first or z[-1]["t"]<last:
        raise ValueError(f"spot sample not fully covered {sym}: {z[0]['day']}..{z[-1]['day']}")
    arm.indicators(z)
    return {"daily":z,"day_keys":[x["day"] for x in z],
            "source":"Binance Vision public SPOT 1d","symbol":sym}


def collect_spot(symbols,start,end):
    if start>=end:raise ValueError("bad interval")
    packs={}
    for sym in symbols:
        candles=[]
        for y,m in month_range(start,end-timedelta(milliseconds=1)):
            url=f"{SPOT_URL}/{sym}/1d/{sym}-1d-{y:04d}-{m:02d}.zip"
            csv_text=retrieve_zip(url)
            candles.extend(rows_from_archive(csv_text,sym,start,end))
            print("SPOT_MONTH",sym,y,m,len(candles),flush=True)
        packs[sym]=build_daily_pack(candles,sym,start,end)
    return packs
