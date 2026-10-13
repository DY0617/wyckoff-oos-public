"""Acquire train/validation 1H execution bars; candidate holdout remains locked."""
import json
from concurrent.futures import ThreadPoolExecutor
from audit_data import acquire,audit,ROOT,stamp
def main():
    tasks=[('um','1h',f'{y:04d}-{m:02d}') for y in range(2020,2025) for m in range(1,13)]
    with ThreadPoolExecutor(max_workers=12) as pool:results=list(pool.map(acquire,tasks))
    rows=[[stamp(x[0]),*x[1:6],stamp(x[6]),*x[7:]] for r in results if r['status']=='ok' for x in r['rows']]
    a=audit(rows,'1h');a['missing_months']=[r['month'] for r in results if r['status']!='ok']
    (ROOT/'raw/um_1h_train_validation.json').write_text(json.dumps(rows,separators=(',',':')))
    (ROOT/'reports/execution_1h_audit.json').write_text(json.dumps({'audit':a,'archives':[{k:v for k,v in r.items() if k!='rows'} for r in results]},indent=2))
    print(a,flush=True)
if __name__=='__main__':main()
