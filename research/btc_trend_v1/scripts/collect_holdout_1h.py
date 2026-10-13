"""Holdout acquisition only; does not calculate any strategy return."""
import json
from concurrent.futures import ThreadPoolExecutor
from audit_data import acquire,audit,ROOT,stamp
def main():
    tasks=[('um','1h',f'{y:04d}-{m:02d}') for y in [2025,2026] for m in range(1,13) if (y,m)<=(2026,9)]
    with ThreadPoolExecutor(max_workers=12) as pool:r=list(pool.map(acquire,tasks))
    q=[[stamp(x[0]),*x[1:6],stamp(x[6]),*x[7:]] for a in r if a['status']=='ok' for x in a['rows']]
    check=audit(q,'1h');check['missing_months']=[a['month'] for a in r if a['status']!='ok']
    if not check['pass_audit'] or check['missing_months']:raise ValueError(check)
    (ROOT/'raw/um_1h_holdout.json').write_text(json.dumps(q,separators=(',',':')))
    (ROOT/'reports/holdout_1h_acquisition.json').write_text(json.dumps({'audit':check,'archives':[{k:v for k,v in a.items() if k!='rows'} for a in r]},indent=2));print(check)
if __name__=='__main__':main()
