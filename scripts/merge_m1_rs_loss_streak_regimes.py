import json
from collections import defaultdict
from pathlib import Path
ROOT=Path("data/validation/m1_rs_loss_streak_regimes")
OUT=Path("data/validation/m1_rs_loss_streak_regimes.json")
files=sorted(ROOT.glob("*.json"))
if len(files)!=5:raise RuntimeError(f"expected 5 windows got {len(files)}")
rows=[x for p in files for x in json.loads(p.read_text())["rows"]]
rows.sort(key=lambda x:(x["episode"],x["signal_date"],x["symbol"]))
def mean(vals):
    vals=[x for x in vals if x is not None]
    return sum(vals)/len(vals) if vals else None
eps={}
for ep in sorted(set(x["episode"] for x in rows)):
    xs=[x for x in rows if x["episode"]==ep]
    eps[str(ep)]={
      "n":len(xs),
      "spy_below_ema20":sum(not x["spy_above_ema20"] for x in xs),
      "spy_below_ema50":sum(not x["spy_above_ema50"] for x in xs),
      "ema20_below_ema50":sum(not x["spy_ema20_above_ema50"] for x in xs),
      "spy_ret20_negative":sum((x["spy_ret20"] or 0)<0 for x in xs),
      "breadth_falling_5d":sum((x["breadth_chg5"] or 0)<0 for x in xs),
      "breadth_falling_20d":sum((x["breadth_chg20"] or 0)<0 for x in xs),
      "avg_spy_ret20":mean([x["spy_ret20"] for x in xs]),
      "avg_breadth":mean([x["breadth"] for x in xs]),
      "avg_breadth_chg5":mean([x["breadth_chg5"] for x in xs]),
      "avg_breadth_chg20":mean([x["breadth_chg20"] for x in xs])
    }
summary={
  "n":len(rows),
  "spy_below_ema20":sum(not x["spy_above_ema20"] for x in rows),
  "spy_below_ema50":sum(not x["spy_above_ema50"] for x in rows),
  "ema20_below_ema50":sum(not x["spy_ema20_above_ema50"] for x in rows),
  "spy_ret20_negative":sum((x["spy_ret20"] or 0)<0 for x in rows),
  "breadth_falling_5d":sum((x["breadth_chg5"] or 0)<0 for x in rows),
  "breadth_falling_20d":sum((x["breadth_chg20"] or 0)<0 for x in rows),
  "avg_spy_ret20":mean([x["spy_ret20"] for x in rows]),
  "avg_breadth":mean([x["breadth"] for x in rows]),
  "avg_breadth_chg5":mean([x["breadth_chg5"] for x in rows]),
  "avg_breadth_chg20":mean([x["breadth_chg20"] for x in rows])
}
report={"summary":summary,"by_episode":eps,"rows":rows}
OUT.parent.mkdir(parents=True,exist_ok=True)
OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
