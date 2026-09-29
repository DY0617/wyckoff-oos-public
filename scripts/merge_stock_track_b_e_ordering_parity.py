import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).parent))
import backtest_us_30x2_track_b_25y as base

ROOT=Path("data/validation/stock_track_b_e_ordering_parity_shards")
OUT=Path("data/validation/stock_track_b_e_ordering_parity_26y.json")

def key(t):
    return (t["symbol"],int(t["entry_t"]),round(float(t["entry"]),8),round(float(t["stop"]),8),
            round(float(t["target"]),8),round(float(t.get("tp1") or 0),8))

def main():
    files=sorted(ROOT.glob("shard_*.json"))
    if not files:raise RuntimeError("no shards")
    modes={"POST":[],"PRE_TRIGGER":[],"PRE_SETUP":[]}
    errors={};audit={"PRE_TRIGGER":{"filtered":0},"PRE_SETUP":{"filtered":0}}
    for p in files:
        o=json.loads(p.read_text())
        for m in modes:modes[m]+=o["trades"][m]
        errors.update(o.get("errors",{}))
        for m in audit:audit[m]["filtered"]+=o.get("filter_audit",{}).get(m,{}).get("filtered",0)

    summaries={m:base.trade_summary([{**t,"direction":"LONG"} for t in ts]) for m,ts in modes.items()}
    sets={m:{key(t) for t in ts} for m,ts in modes.items()}
    parity={}
    maps={m:{key(t):t for t in ts} for m,ts in modes.items()}
    for m in ("PRE_TRIGGER","PRE_SETUP"):
        common=sets["POST"]&sets[m]
        only_post=sets["POST"]-sets[m];only_pre=sets[m]-sets["POST"]
        parity[m]={
          "exact_trade_set_match":sets["POST"]==sets[m],
          "common_trades":len(common),
          "only_post":len(only_post),
          "only_pre":len(only_pre),
          "max_abs_pnl_diff_common":max([abs(maps["POST"][k]["pnl"]-maps[m][k]["pnl"]) for k in common] or [0.0]),
          "only_post":[list(k) for k in sorted(only_post)[:200]],
          "only_pre":[list(k) for k in sorted(only_pre)[:200]]
        }
    out={
      "purpose":"Stock Track-B E live-ordering parity, Dow2000 frozen universe",
      "period":{"start":"2000-01-01","end_exclusive":"2026-01-01"},
      "management":"15/25/60 + confirmed RTH 4H pivot runner",
      "modes":{
        "POST":"original research semantics: create/suppress trades first, then E-filter completed LONG trades at entry time",
        "PRE_TRIGGER":"live-like: keep setup pending, apply LONG+E filter at actual trigger bar before entry",
        "PRE_SETUP":"strict live-like: apply LONG+E filter when actionable setup creates the pending order"
      },
      "summaries":summaries,"parity":parity,"filter_audit":audit,"errors":errors,
      "shards":[p.name for p in files]
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=="__main__":main()
