import json, statistics, sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).parent))
import backtest_stock_track_b_e_cash_to_binance_futures_exec_v1 as src

ROOT=Path("data/validation/stock_cash_to_futures_shards")
OUT=Path("data/validation/stock_track_b_e_cash_to_binance_futures_exec_v1_sharded.json")
TRADES_OUT=Path("data/validation/stock_track_b_e_cash_to_binance_futures_exec_v1_sharded_trades.json")

def main():
    files=sorted(ROOT.glob("trades_*.json"))
    if not files:raise RuntimeError("no shard trade files")
    cash=[];modes={"SAME_BAR_CLOSE":[],"NEXT_BAR_OPEN":[]}
    supported=[];errors={};per={};daily_counts=[]
    for p in files:
        x=json.loads(p.read_text())
        rep=x["report"]
        cash+=x.get("cash_trades",[])
        for m in modes:modes[m]+=x.get("futures_trades",{}).get(m,[])
        supported+=rep.get("futures_supported_stock50",[])
        errors.update(rep.get("errors",{}))
        per.update(rep.get("per_symbol",{}))
        daily_counts.append(rep.get("daily_filter_symbols_available",0))
    # Deduplicate defensively.
    ck={}
    for t in cash:ck[(t["symbol"],t["entry_t"])]=t
    cash=list(ck.values())
    for m in modes:
        mk={}
        for t in modes[m]:
            k=(t["symbol"],t["cash_entry_t"],t.get("entry_t"))
            mk[k]=t
        modes[m]=list(mk.values())

    report_modes={}
    for mode,fts in modes.items():
        fts=[x for x in fts if x.get("status")=="EXECUTED"]
        closed=[x for x in fts if x.get("reason")!="OPEN_MARK"]
        closed_keys={(x["symbol"],x["cash_entry_t"]) for x in closed}
        cb=[t for t in cash if (t["symbol"],t["entry_t"]) in closed_keys]
        bycash={(t["symbol"],t["entry_t"]):t for t in cb}
        diffs=[];signs=0
        for x in closed:
            c=bycash.get((x["symbol"],x["cash_entry_t"]))
            if c:
                diffs.append(x["r"]-c["r"])
                signs+=int((x["r"]>0)==(c["r"]>0))
        basis=[x["basis_bps"] for x in fts]
        report_modes[mode]={
          "futures":src.stats(fts),
          "executed_total":len(fts),"closed_matched":len(closed),
          "cash_benchmark_on_closed_matched":{
             "trades":len(cb),"net_r":sum(t["r"] for t in cb),
             "avg_r":statistics.fmean([t["r"] for t in cb]) if cb else None,
             "win_rate":sum(t["r"]>0 for t in cb)/len(cb) if cb else None},
          "execution_delta_r":{"sum":sum(diffs),"mean":statistics.fmean(diffs) if diffs else None},
          "outcome_sign_match_rate":signs/len(diffs) if diffs else None,
          "entry_basis_bps":{
             "n":len(basis),"mean":statistics.fmean(basis) if basis else None,
             "median":statistics.median(basis) if basis else None,
             "mean_abs":statistics.fmean(abs(x) for x in basis) if basis else None,
             "median_abs":statistics.median(abs(x) for x in basis) if basis else None}
        }
    report={
      "purpose":"Sharded cash Track-B E signal -> Binance TradFi futures execution calibration",
      "period":{"end_exclusive":"2026-09-29T00:00:00Z"},
      "futures_supported_stock50":sorted(set(supported)),
      "cash_signals_total":len(cash),
      "daily_filter_symbols_available_min":min(daily_counts) if daily_counts else None,
      "modes":report_modes,
      "per_symbol":per,"errors":errors,
      "shards":[p.name for p in files],
      "rules":{
        "signal":"cash RTH Track B + E at trigger, LONG only",
        "management":"15/25/60 + mapped cash 4H pivot runner",
        "after_hours_management":True,"fixed_risk_usd":src.RISK}
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    TRADES_OUT.write_text(json.dumps({"report":report,"cash_trades":cash,"futures_trades":modes},ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=="__main__":main()
