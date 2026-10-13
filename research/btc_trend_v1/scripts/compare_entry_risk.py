"""Train-only volatility matching for candidate/benchmark comparison."""
import json
from baseline import Data,ROOT,run,ms
def main():
    d=Data.load();b=json.loads((ROOT/'reports/baseline_v1/metrics.json').read_text())['results'];e=json.loads((ROOT/'reports/entries_1h/metrics.json').read_text())['results'];results=[]
    for candidate in ['D','C_simple']:
        target=next(x['realized_vol_pct'] for x in e if x['strategy']==candidate and x['period']=='train')
        for k in ['hold','trend','vol_hold','vol_trend']:
            basevol=next(x['realized_vol_pct'] for x in b if x['market']=='um' and x['strategy']==k and x['period']=='train' and x['cost_case']=='base')
            scale=min(1.,target/basevol)
            r=run(d,'um',k,ms('2023-01-01'),ms('2025-01-01'),retain=False,exposure_scale=scale)['metrics'];r.update(reference_candidate=candidate,reference_train_vol_pct=target,scale_calibration='train 2020-2022 only');results.append(r)
    report={'note':'Baseline exposure is matched to each candidate training realized volatility, with all scaling frozen from train. Future realized vol is allowed to differ. No holdout candidate performance is evaluated.','results':results}
    (ROOT/'reports/entries_1h/risk_matched_benchmarks.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
