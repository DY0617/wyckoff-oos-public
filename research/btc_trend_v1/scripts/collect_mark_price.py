"""Pin USD-M 4H mark-price archives for funding valuation."""
import csv,io,json,hashlib,zipfile,urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def get(url):
    with urllib.request.urlopen(url,timeout=20) as r:return r.read()
def fetch(month):
    url=f'https://data.binance.vision/data/futures/um/monthly/markPriceKlines/BTCUSDT/4h/BTCUSDT-4h-{month}.zip'
    p=ROOT/'raw/um/mark4h'/f'{month}.zip';p.parent.mkdir(parents=True,exist_ok=True)
    try:
        raw=p.read_bytes() if p.exists() else get(url)
        sha=get(url+'.CHECKSUM').decode().split()[0]
        if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('checksum mismatch')
        p.write_bytes(raw)
        with zipfile.ZipFile(io.BytesIO(raw)) as z:rows=list(csv.reader(io.StringIO(z.read(z.namelist()[0]).decode('utf-8-sig'))))
        if rows and not rows[0][0].isdigit():rows=rows[1:]
        return {'month':month,'url':url,'sha256':sha,'status':'ok','rows':rows}
    except Exception as e:return {'month':month,'url':url,'status':'failed','error':str(e)}
def main():
    months=[f'{y:04d}-{m:02d}' for y in range(2020,2027) for m in range(1,13) if (y,m)<=(2026,9)]
    with ThreadPoolExecutor(max_workers=12) as pool:r=list(pool.map(fetch,months))
    rows=[x for a in r if a['status']=='ok' for x in a['rows']]
    expected={int(x[0]) for x in json.loads((ROOT/'raw/um_4h.json').read_text())}
    bytime={int(x[0]):x for x in rows}
    from datetime import datetime,timezone
    missing_days=sorted({datetime.fromtimestamp(t/1000,timezone.utc).strftime('%Y-%m-%d') for t in expected-set(bytime)})
    daily_manifest=[]
    def daily(day):
        url=f'https://data.binance.vision/data/futures/um/daily/markPriceKlines/BTCUSDT/4h/BTCUSDT-4h-{day}.zip'
        p=ROOT/'raw/um/mark4h_daily'/f'{day}.zip';p.parent.mkdir(parents=True,exist_ok=True)
        try:
            raw=p.read_bytes() if p.exists() else get(url);sha=get(url+'.CHECKSUM').decode().split()[0]
            if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('checksum mismatch')
            p.write_bytes(raw)
            with zipfile.ZipFile(io.BytesIO(raw)) as z:q=list(csv.reader(io.StringIO(z.read(z.namelist()[0]).decode('utf-8-sig'))))
            if q and not q[0][0].isdigit():q=q[1:]
            return {'day':day,'url':url,'sha256':sha,'status':'ok','rows':q}
        except Exception as e:return {'day':day,'url':url,'status':'failed','error':str(e)}
    with ThreadPoolExecutor(max_workers=12) as pool:daily_manifest=list(pool.map(daily,missing_days))
    for a in daily_manifest:
        for row in a.get('rows',[]):
            t=int(row[0])
            if t not in bytime:bytime[t]=row
    rows=[bytime[t] for t in sorted(bytime)]
    (ROOT/'raw/um_mark4h.json').write_text(json.dumps(rows,separators=(',',':')))
    (ROOT/'reports/mark_manifest.json').write_text(json.dumps([{k:v for k,v in a.items() if k!='rows'} for a in r],indent=2))
    (ROOT/'reports/mark_daily_repairs.json').write_text(json.dumps([{k:v for k,v in a.items() if k!='rows'} for a in daily_manifest],indent=2))
    print({'rows':len(rows),'monthly_missing_bars':len(expected)-sum(len(a.get('rows',[])) for a in r),'remaining_missing_bars':len(expected-set(bytime)),'daily_failed':[a for a in daily_manifest if a['status']!='ok'],'failed':[a for a in r if a['status']!='ok']},flush=True)
if __name__=='__main__':main()
