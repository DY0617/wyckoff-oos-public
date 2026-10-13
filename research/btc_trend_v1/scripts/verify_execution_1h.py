"""Re-run frozen entries with 1H gap/stop sequencing, without opening holdout."""
import json,math
from collections import defaultdict
from baseline import Data,bars,check_sequence,ROOT,ms,write_csv
from entries_v1 import LIMIT,features,flags,simulate
def main():
    data=Data.load();h=bars('um_1h_train_validation');check_sequence(h,3600000);group=defaultdict(list)
    for r in h:group[r['t']//14400000*14400000].append(r)
    b=[r for r in data.future4 if r['t']<LIMIT];diff=[];volume_diff=[]
    for r in b:
        g=group[r['t']];assert len(g)==4
        g=[x for x in g if x['v']>0];assert g
        agg=[g[0]['o'],max(x['h'] for x in g),min(x['l'] for x in g),g[-1]['c']]
        if any(not math.isclose(x,r[k],rel_tol=1e-10,abs_tol=1e-7) for x,k in zip(agg,['o','h','l','c'])):diff.append(r['t'])
        if not math.isclose(sum(x['v'] for x in g),r['v'],rel_tol=1e-10,abs_tol=1e-7):volume_diff.append(r['t'])
    if diff:raise ValueError(f'1H/4H OHLC discrepancies: {diff}')
    f=features(b);sig=flags(b,f);hmap={r['t']:r for r in h};results=[];out=ROOT/'reports/entries_1h';out.mkdir(parents=True,exist_ok=True)
    for k in ['A','B','C','C_simple','D']:
        for period,(a,z) in {'train':('2020-01-01','2023-01-01'),'validation':('2023-01-01','2025-01-01')}.items():
            base=simulate(data,b,f,sig,k,ms(a),ms(z),retain=False)
            r=simulate(data,b,f,sig,k,ms(a),ms(z),execution_1h=hmap)
            v=r['metrics'];v.update(period=period,return_difference_from_4h_pp=v['return_pct']-base['metrics']['return_pct'],net_R_difference_from_4h=v['total_net_r']-base['metrics']['total_net_r']);results.append(v)
            for field in ['trades','fills']:write_csv(out/f'{k}_{period}_{field}.csv',r[field])
    report={'results':results,'ohlc_mismatches':diff,'volume_mismatches':volume_diff,'hours':len(h),'zero_volume_hours_excluded_from_execution':[x['t'] for x in h if x['v']==0],'four_hour_bars_crosschecked':len(b),'candidate_holdout_evaluated':False,'limitations':'1H OHLC resolves hourly gap/stop prices but not tick-level fill latency, depth or historical quantity precision; mark-to-market MDD still sampled at 4H'}
    (out/'metrics.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
