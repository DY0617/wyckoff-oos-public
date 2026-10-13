"""Cross-timeframe and repository/archive discrepancy checks, no strategy returns."""
import json, math
from pathlib import Path
from collections import defaultdict
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
def main():
    result={}
    for market in ('spot','um'):
        d=json.loads((ROOT/'raw'/f'{market}_1d.json').read_text())
        h=json.loads((ROOT/'raw'/f'{market}_4h.json').read_text())
        groups=defaultdict(list)
        for r in h:groups[r[0]//86400000*86400000].append(r)
        bad=[];incomplete=[];checked=0
        for r in d:
            g=groups.get(r[0],[])
            if len(g)!=6:incomplete.append(r[0]);continue
            checked+=1
            agg=[float(g[0][1]),max(float(x[2]) for x in g),min(float(x[3]) for x in g),float(g[-1][4]),sum(float(x[5]) for x in g)]
            diff=[i+1 for i,(a,b) in enumerate(zip(agg,map(float,r[1:6]))) if not math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-7)]
            if diff:bad.append({'day_ms':r[0],'fields':diff,'daily':r[1:6],'aggregate':agg})
        result[market]={'checked_days':checked,'incomplete_days':incomplete,'mismatches':bad}
    ref=json.loads((ROOT/'raw/repo_spot_1d.json').read_text());daily={r[0]:r for r in json.loads((ROOT/'raw/spot_1d.json').read_text())}
    diffs=[];n=0
    for r in ref:
        if r[0] not in daily:continue
        n+=1;a=daily[r[0]]
        if any(float(a[i])!=float(r[i]) for i in range(1,6)):diffs.append({'day_ms':r[0],'archive':a[1:6],'repository':r[1:6]})
    result['repo_overlap']={'checked_days':n,'mismatches':diffs}
    funding=json.loads((ROOT/'raw/um_funding.json').read_text())
    result['funding_schema_samples']=funding[:3]
    if funding:
        ts=[int(r[0]) for r in funding]
        result['funding']={'rows':len(ts),'duplicates':len(ts)-len(set(ts)),'nonincreasing':sum(b<=a for a,b in zip(ts,ts[1:])), 'interval_counts':dict(__import__('collections').Counter((b-a)//1000 for a,b in zip(ts,ts[1:])))}
    (ROOT/'reports/crosscheck.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
