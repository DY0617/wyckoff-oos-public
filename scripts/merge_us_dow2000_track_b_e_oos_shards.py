import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).parent))
import backtest_us_30x2_track_b_25y as base

ROOT=Path("data/validation/us_dow2000_track_b_e_oos_shards")
OUT=Path("data/validation/us_dow2000_track_b_e_15_25_60_oos_v1.json")
UTC=timezone.utc

def block_for(t):
    y=datetime.fromtimestamp(t["entry_t"]/1000,UTC).year
    if y<2005:return "2000_2005"
    if y<2010:return "2005_2010"
    if y<2015:return "2010_2015"
    if y<2020:return "2015_2020"
    if y<2024:return "2020_2024"
    return "2024_2026"

def main():
    files=sorted(ROOT.glob("shard_*.json"))
    if not files:raise RuntimeError("no shard outputs")
    trades=[];errors={};raw=0;state_missing=0;symbols=[]
    for p in files:
        o=json.loads(p.read_text())
        trades+=o.get("trades",[])
        errors.update(o.get("errors",{}))
        raw+=o.get("raw_long_candidates",0)
        state_missing+=o.get("state_missing",0)
        symbols+=o.get("symbols",[])
    trades.sort(key=lambda t:(t["exit_t"],t["symbol"]))
    sm=base.trade_summary(trades)
    by_symbol=base.grouped_stats(trades,lambda t:t["symbol"])
    by_year=base.grouped_stats(trades,lambda t:datetime.fromtimestamp(t["entry_t"]/1000,UTC).year)
    blocks={}
    for b in ("2000_2005","2005_2010","2010_2015","2015_2020","2020_2024","2024_2026"):
        blocks[b]=base.trade_summary([t for t in trades if block_for(t)==b])
    positive_blocks=sum(v["net_r"]>0 for v in blocks.values())
    mdd_r=sm["max_drawdown_fixed_20k"]*base.CAP/base.RISK
    flags={
      "net_r_positive":sm["net_r"]>0,
      "profit_factor_gt_1_30":(sm["profit_factor_r"] or 0)>1.30,
      "max_drawdown_lt_25r":mdd_r<25,
      "at_least_4_of_6_blocks_positive":positive_blocks>=4
    }
    out={
      "purpose":"Independent-universe OOS validation of stock Track-B E + 15/25/60",
      "universe":"DJIA constituents frozen at 2000-01",
      "symbols":sorted(set(symbols)),
      "breadth_universe":list(base.DOW2000),
      "period":{"start":base.GLOBAL_EVAL_START.isoformat(),"end_exclusive":base.EVAL_END.isoformat()},
      "strategy":{
        "signal":"TRACK_B_V1_0_FROZEN exact-touch, LONG only",
        "filter":"SPY bull 2/3 + stock ret20>=SPY ret20 + breadth>=50% of available Dow2000",
        "management":"15% TP1=>BE; 25% TP2=>TP1; 60% confirmed RTH 4H pivot runner"
      },
      "costs":{"fee_bps":base.FEE_BPS,"slippage_bps":base.SLIPPAGE_BPS,"risk_usd":base.RISK},
      "raw_long_candidates":raw,"eligible_trades":len(trades),"state_missing":state_missing,
      "summary":sm,"max_drawdown_r":mdd_r,
      "by_symbol":by_symbol,"by_year":by_year,"blocks":blocks,
      "pass_criteria":{
        "required":{"net_r":">0","profit_factor":">1.30","max_drawdown_r":"<25","positive_blocks":">=4/6"},
        "positive_blocks":positive_blocks,"flags":flags,"passed_all":all(flags.values())
      },
      "errors":errors,
      "shard_files":[p.name for p in files],
      "limitations":[
        "Dow2000 membership is frozen at 2000-01; later constituent replacements are not added.",
        "Ticker continuity around mergers/delistings/reorganizations can be imperfect in raw historical data.",
        "Filter E is applied to completed Track-B trade candidates, matching the prior 53-stock filter study."
      ]
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=="__main__":main()
