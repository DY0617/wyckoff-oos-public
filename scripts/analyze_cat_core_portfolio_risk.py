import json, math
from pathlib import Path
from collections import defaultdict

ROOT=Path(__file__).resolve().parents[1]
CONFIGS=[
    {"target_risk":0.005,"class_cap":0.02,"total_cap":0.03},
    {"target_risk":0.0035,"class_cap":0.015,"total_cap":0.025},
    {"target_risk":0.0025,"class_cap":0.01,"total_cap":0.02},
]
SETS={
    "v0.3":(
        ROOT/"data/validation/cat_core_v0_3_crypto_5y.json",
        ROOT/"data/validation/cat_core_v0_3_stock30_5y.json",
    ),
    "v0.4":(
        ROOT/"data/validation/cat_core_v0_4_er20_crypto_5y.json",
        ROOT/"data/validation/cat_core_v0_4_er20_stock30_5y.json",
    ),
}
OUT=ROOT/"data/validation/cat_core_portfolio_risk_compare.json"

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))["trades"]

def simulate(crypto,stock,target_risk,class_cap,total_cap):
    trades=[]
    for i,t in enumerate(crypto):
        q=dict(t);q["asset_class"]="crypto";q["_id"]=f"c{i}";trades.append(q)
    for i,t in enumerate(stock):
        q=dict(t);q["asset_class"]="stock";q["_id"]=f"s{i}";trades.append(q)
    trades.sort(key=lambda x:(x["entry_t"],x["asset_class"],x["symbol"]))

    groups=defaultdict(list)
    for t in trades:groups[t["entry_t"]].append(t)

    equity=1.0;peak=1.0;max_dd=0.0
    open_pos=[];accepted=skipped=wins=losses=0

    def settle(until):
        nonlocal equity,peak,max_dd,open_pos,wins,losses
        due=sorted((p for p in open_pos if p["exit_t"]<=until),key=lambda p:p["exit_t"])
        for p in due:
            equity += p["risk_dollar"]*p["r"]
            wins += p["r"]>0
            losses += p["r"]<0
            peak=max(peak,equity)
            max_dd=min(max_dd,equity/peak-1)
        open_pos=[p for p in open_pos if p["exit_t"]>until]

    for et in sorted(groups):
        settle(et)
        group=groups[et]
        for cls in ("crypto","stock"):
            g=[x for x in group if x["asset_class"]==cls]
            if not g:continue
            open_class=sum(p["risk_dollar"] for p in open_pos if p["asset_class"]==cls)
            open_total=sum(p["risk_dollar"] for p in open_pos)
            avail_class=max(0.0,class_cap*equity-open_class)
            avail_total=max(0.0,total_cap*equity-open_total)
            each=max(0.0,min(target_risk*equity,avail_class/len(g),avail_total/len(g)))
            for t in g:
                if each<=1e-12:
                    skipped+=1;continue
                q=dict(t);q["risk_dollar"]=each;open_pos.append(q);accepted+=1

    settle(float("inf"))
    years=(max(t["exit_t"] for t in trades)-min(t["entry_t"] for t in trades))/(365.25*24*3600*1000)
    total_return=equity-1
    cagr=equity**(1/years)-1 if years>0 else None
    return {
        "target_risk":target_risk,
        "class_cap":class_cap,
        "total_cap":total_cap,
        "accepted":accepted,
        "skipped":skipped,
        "final_equity":equity,
        "total_return":total_return,
        "cagr":cagr,
        "max_realized_drawdown":max_dd,
        "return_over_dd":total_return/abs(max_dd) if max_dd<0 else None,
        "wins":wins,"losses":losses,
    }

def main():
    result={
        "note":"Realized-equity portfolio simulation. Existing position initial risk is conservatively held against the cap until exit; no mark-to-market intratrade equity path is reconstructed.",
        "allocation":"At each same-timestamp entry group, available class/total initial-risk budget is split equally; target risk is a per-trade ceiling.",
        "versions":{}
    }
    for name,(cp,sp) in SETS.items():
        c,s=load(cp),load(sp)
        result["versions"][name]=[simulate(c,s,**cfg) for cfg in CONFIGS]
    OUT.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))

if __name__=="__main__":
    main()

# workflow-trigger
