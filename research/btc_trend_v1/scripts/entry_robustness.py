"""Fixed contiguous-trade block bootstrap; descriptive, not proof of edge."""
import csv,json,statistics,random
from baseline import ROOT
def main():
    out={}
    for k in ['A','B','C_simple','D']:
        for period in ['train','validation']:
            rows=list(csv.DictReader((ROOT/f'reports/entries_v1/{k}_{period}_trades.csv').open()));rr=[float(x['net_r']) for x in rows];n=len(rr);intervals={}
            for block in [3,5,10]:
                rng=random.Random(20261013);means=[]
                for _ in range(3000):
                    sample=[]
                    while len(sample)<n:
                        i=rng.randrange(n);sample.extend(rr[(i+j)%n] for j in range(block))
                    means.append(statistics.fmean(sample[:n]))
                means.sort();intervals[str(block)]=[means[74],means[2924]]
            ordered=sorted(rr,reverse=True)
            out[k+'_'+period]={'trades':n,'expectancy_R':statistics.fmean(rr),'block_mean_R_CI95':intervals,'largest_trade_R':ordered[0],'total_R':sum(rr),'total_R_excluding_best_trade':sum(rr)-ordered[0],'terminal_trade_count':sum(x['terminal']=='True' for x in rows),'net_R_excluding_terminal':sum(float(x['net_r']) for x in rows if x['terminal']=='False')}
    report={'method':'circular moving-block bootstrap of chronological trade net R, fixed seed 20261013, 3000 replicates per block length. Three block lengths reported without selection. No multiplicity adjustment across entry candidates. May understate regime and model uncertainty.','results':out}
    (ROOT/'reports/entries_v1/robustness.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
