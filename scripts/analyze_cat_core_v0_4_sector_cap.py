import json,math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
C=ROOT/"data/validation/cat_core_v0_4_funding_only.json"
S=ROOT/"data/validation/cat_core_v0_4_er20_stock30_5y.json"
OUT=ROOT/"data/validation/cat_core_v0_4_sector_cap_compare.json"

SECTOR={
"AAPL":"MEGATECH","MSFT":"MEGATECH","GOOGL":"MEGATECH","META":"MEGATECH","AMZN":"MEGATECH","NFLX":"MEGATECH","CRM":"MEGATECH","ORCL":"MEGATECH","CSCO":"MEGATECH","IBM":"MEGATECH",
"AVGO":"SEMIS","MU":"SEMIS","AMD":"SEMIS","INTC":"SEMIS","NVDA":"SEMIS","AMAT":"SEMIS","TSM":"SEMIS",
"COST":"CONSUMER","WMT":"CONSUMER","HD":"CONSUMER","DIS":"CONSUMER","TSLA":"CONSUMER","UBER":"CONSUMER",
"JPM":"FINANCIAL","V":"FINANCIAL","SPY":"INDEX","QQQ":"INDEX","COIN":"CRYPTO_BETA","MSTR":"CRYPTO_BETA","CAT":"INDUSTRIAL"
}
TARGET=.0035;CLASS_CAP=.015;TOTAL_CAP=.025

def load():
    c=json.loads(C.read_text())["trades"]
    s=json.loads(S.read_text())["trades"]
    cc=[{**x,"r_use":x["r_adj"],"asset_class":"crypto"} for x in c]
    ss=[{**x,"r_use":x["r"],"asset_class":"stock"} for x in s]
    return cc+ss

def sim(max_sector):
    trades=sorted(load(),key=lambda x:(x["entry_t"],x["asset_class"],x["symbol"]))
    groups={}
    for t in trades:groups.setdefault(t["entry_t"],[]).append(t)
    eq=1.;peak=1.;dd=0.;openp=[];acc=skipb=skips=w=l=0
    for et in sorted(groups):
        due=sorted([p for p in openp if p["exit_t"]<=et],key=lambda p:p["exit_t"])
        for p in due:
            eq+=p["risk"]*p["r_use"];peak=max(peak,eq);dd=min(dd,eq/peak-1)
            if p["r_use"]>0:w+=1
            else:l+=1
        openp=[p for p in openp if p["exit_t"]>et]
        for cls in ("crypto","stock"):
            for t in sorted([x for x in groups[et] if x["asset_class"]==cls],key=lambda x:x["symbol"]):
                if cls=="stock" and max_sector is not None:
                    sec=SECTOR.get(t["symbol"],"OTHER")
                    if sum(1 for p in openp if p["asset_class"]=="stock" and SECTOR.get(p["symbol"],"OTHER")==sec)>=max_sector:
                        skips+=1;continue
                cr=sum(p["risk"] for p in openp if p["asset_class"]==cls)
                tr=sum(p["risk"] for p in openp)
                risk=min(TARGET*eq,max(0.,CLASS_CAP*eq-cr),max(0.,TOTAL_CAP*eq-tr))
                if risk<=1e-12:skipb+=1;continue
                openp.append({**t,"risk":risk});acc+=1
    for p in sorted(openp,key=lambda x:x["exit_t"]):
        eq+=p["risk"]*p["r_use"];peak=max(peak,eq);dd=min(dd,eq/peak-1)
        if p["r_use"]>0:w+=1
        else:l+=1
    return {"max_stock_sector_positions":max_sector,"accepted":acc,"skipped_budget":skipb,"skipped_sector":skips,
            "final_equity":eq,"total_return":eq-1,"max_realized_dd":dd,
            "return_over_dd":(eq-1)/abs(dd) if dd<0 else None,"wins":w,"losses":l}

def main():
    out={"portfolio":{"target_risk":TARGET,"class_cap":CLASS_CAP,"total_cap":TOTAL_CAP},
         "note":"Risk-layer diagnostic only; signal rules unchanged. Static broad buckets are intentionally coarse.",
         "base":sim(None),"max2":sim(2),"max1":sim(1),"sector_map":SECTOR}
    OUT.write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
if __name__=="__main__":main()
