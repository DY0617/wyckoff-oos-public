"""Read-only Binance archive acquisition and strict candle audit (stdlib only)."""
import csv, io, json, hashlib, math, zipfile, urllib.request
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
CUTOFF = int(datetime(2026,10,1,tzinfo=timezone.utc).timestamp()*1000)
def get(url):
    with urllib.request.urlopen(url, timeout=20) as r: return r.read()
def stamp(x):
    t=int(x)
    return t//1000 if t>10**14 else t
def acquire(task):
    market, tf, month = task
    kind='fundingRate' if tf=='funding' else 'klines'
    prefix='spot' if market=='spot' else 'futures/um'
    tail=f'BTCUSDT/{tf}/BTCUSDT-{tf}-{month}.zip' if tf!='funding' else f'BTCUSDT/BTCUSDT-fundingRate-{month}.zip'
    url=f'https://data.binance.vision/data/{prefix}/monthly/{kind}/{tail}'
    p=ROOT/'raw'/market/tf/(month+'.zip');p.parent.mkdir(parents=True,exist_ok=True)
    try:
        raw=p.read_bytes() if p.exists() else get(url)
        checksum=get(url+'.CHECKSUM').decode().split()[0]
        if hashlib.sha256(raw).hexdigest()!=checksum: raise ValueError('checksum mismatch')
        p.write_bytes(raw)
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            rows=list(csv.reader(io.StringIO(z.read(z.namelist()[0]).decode('utf-8-sig'))))
        if rows and not rows[0][0].isdigit(): rows=rows[1:]
        return dict(market=market,tf=tf,month=month,url=url,sha256=checksum,rows=rows,status='ok')
    except Exception as e: return dict(market=market,tf=tf,month=month,url=url,status='failed',error=str(e))
def audit(rows,tf):
    duration={'1d':86400000,'4h':14400000,'1h':3600000}[tf]
    times=[stamp(r[0]) for r in rows];bad=[];gaps=[]
    for i,r in enumerate(rows):
        t=times[i];o,h,l,c,v=map(float,r[1:6]);ct=stamp(r[6])
        if not all(math.isfinite(x) for x in (o,h,l,c,v)) or min(o,h,l,c)<=0 or v<0 or l>min(o,c) or h<max(o,c) or h<l or t%duration or ct!=t+duration-1 or ct>=CUTOFF: bad.append(i)
        if i and t-times[i-1]!=duration:gaps.append({'before':times[i-1],'after':t,'missing':(t-times[i-1])//duration-1})
    return dict(rows=len(rows),first_ms=times[0] if times else None,last_ms=times[-1] if times else None,duplicates=len(times)-len(set(times)),invalid_rows=bad,gaps=gaps,pass_audit=bool(rows) and not bad and not gaps and len(times)==len(set(times)))
def main():
    tasks=[]
    for market,start in [('spot',(2017,8)),('um',(2019,9))]:
        for tf in ['1d','4h']+(['funding'] if market=='um' else []):
            for y in range(start[0],2027):
                for m in range(1,13):
                    if (y,m)<start or (y,m)>(2026,9):continue
                    tasks.append((market,tf,f'{y:04d}-{m:02d}'))
    results=[]
    with ThreadPoolExecutor(max_workers=12) as pool:
        for n,r in enumerate(pool.map(acquire,tasks),1):
            results.append(r)
            if n%40==0:print('ARCHIVES',n,'/',len(tasks),flush=True)
    report={'cutoff_exclusive_utc':'2026-10-01','archives':[{k:v for k,v in r.items() if k!='rows'} for r in results], 'datasets':{}}
    for market,tf in sorted(set((r['market'],r['tf']) for r in results)):
        selected=[r for r in results if r['market']==market and r['tf']==tf]
        rows=[row for r in selected if r['status']=='ok' for row in r['rows']]
        if tf!='funding':
            normalized=[[stamp(r[0]),*r[1:6],stamp(r[6]),*r[7:]] for r in rows]
            a=audit(normalized,tf)
        else:
            normalized=rows;a={'rows':len(rows),'status':'requires settlement schedule and schema audit'}
        a['missing_months']=[r['month'] for r in selected if r['status']!='ok']
        report['datasets'][market+'_'+tf]=a
        (ROOT/'raw'/f'{market}_{tf}.json').write_text(json.dumps(normalized,separators=(',',':')))
    repo=json.loads((ROOT/'raw/repo_spot_1d.json').read_text())
    report['repository_spot_1d']=audit(repo,'1d') if repo[-1][6]<CUTOFF else {'rows':len(repo),'first_ms':repo[0][0],'last_ms':repo[-1][0],'note':'contains post-study-cutoff rows; audit truncated study subset','study_subset':audit([r for r in repo if r[6]<CUTOFF],'1d')}
    (ROOT/'reports/data_audit.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='archives'},indent=2),flush=True)
if __name__=='__main__': main()
