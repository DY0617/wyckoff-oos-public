"""Source-only reconciliation; preserve original monthly files unchanged."""
import json,hashlib
from baseline import ROOT
def main():
    original=json.loads((ROOT/'raw/um_4h.json').read_text());bytime={int(r[0]):r for r in original};daily=json.loads((ROOT/'reports/execution_anomaly_daily.json').read_text());changes=[]
    for a in daily:
        if a['status']!='ok':raise ValueError('required daily counterpart unavailable')
        if a['tf']!='4h':continue
        for r in a['rows']:
            t=int(r[0]);r=[t,*r[1:6],int(r[6]),*r[7:]]
            old=bytime[t]
            if any(float(old[i])!=float(r[i]) for i in range(1,6)):
                changes.append({'time_ms':t,'monthly':old[:7],'daily':r[:7],'source_url':a['url'],'sha256':a['sha256']});bytime[t]=r
    dest=ROOT/'raw/um_4h_canonical.json';dest.write_text(json.dumps([bytime[t] for t in sorted(bytime)],separators=(',',':')))
    report={'policy':'Use verified daily 4H counterparts only on identified anomaly dates. Preserve monthly originals. For cross-timeframe aggregation and execution, zero-volume 1H bars provide no tradable print; skip them and use first nonzero-volume hourly open. This changes source handling, not entry thresholds. No holdout strategy evaluation.','changes':changes,'canonical_sha256':hashlib.sha256(dest.read_bytes()).hexdigest()}
    (ROOT/'reports/execution_source_policy.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
