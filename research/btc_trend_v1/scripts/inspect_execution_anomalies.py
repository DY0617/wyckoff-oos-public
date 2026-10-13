"""Preserve official daily counterparts for identified monthly OHLC anomalies."""
import json,csv,io,zipfile,hashlib,urllib.request
from concurrent.futures import ThreadPoolExecutor
from baseline import ROOT
def fetch(task):
    day,tf=task;url=f'https://data.binance.vision/data/futures/um/daily/klines/BTCUSDT/{tf}/BTCUSDT-{tf}-{day}.zip';p=ROOT/f'raw/um/anomaly_daily/{tf}/{day}.zip';p.parent.mkdir(parents=True,exist_ok=True)
    try:
        def get(u):
            with urllib.request.urlopen(u,timeout=20) as r:return r.read()
        raw=p.read_bytes() if p.exists() else get(url);sha=get(url+'.CHECKSUM').decode().split()[0];assert hashlib.sha256(raw).hexdigest()==sha;p.write_bytes(raw)
        with zipfile.ZipFile(io.BytesIO(raw)) as z:q=list(csv.reader(io.StringIO(z.read(z.namelist()[0]).decode('utf-8-sig'))))
        if not q[0][0].isdigit():q=q[1:]
        return {'day':day,'tf':tf,'url':url,'sha256':sha,'status':'ok','rows':q}
    except Exception as e:return {'day':day,'tf':tf,'url':url,'status':'failed','error':str(e)}
def main():
    with ThreadPoolExecutor(max_workers=4) as pool:r=list(pool.map(fetch,[(d,t) for d in ['2023-11-10','2024-10-28'] for t in ['1h','4h']]))
    (ROOT/'reports/execution_anomaly_daily.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))
if __name__=='__main__':main()
