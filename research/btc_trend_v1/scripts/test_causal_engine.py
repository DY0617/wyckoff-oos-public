"""Meaningful deterministic accounting/availability checks using acquired data."""
import copy,math,csv
from baseline import ROOT,Data,bars,indicators,ms,run,rebalance_delta
from entries_v1 import features,flags,LIMIT,simulate
def main():
    for q,e,p,w in [(0,10000,100,1),(100,10000,100,0),(20,10000,100,.5),(90,10000,100,.5)]:
        dq=rebalance_delta(q,e,p,w,.0005,.0002);fill=p*(1.0002 if dq>0 else .9998);cost=abs(dq)*p*.0002+abs(dq)*fill*.0005
        assert abs((q+dq)*p-w*(e-cost))<1e-8
    s=bars('spot_1d');a=ms('2021-01-01');r=run(Data(s,[],[],[],[]),'spot','hold',a,a+86400000);bar=next(x for x in s if x['t']==a)
    expected=10000/(bar['o']*1.0002*1.0005)*bar['c']*.9998*.9995
    assert math.isclose(expected,r['metrics']['final_equity'],rel_tol=1e-12)
    old=indicators(s);c=copy.deepcopy(s);cut=ms('2023-01-01')
    for x in c:
        if x['t']>=cut:x['c']*=7
    new=indicators(c);assert all(old[t]==new[t] for t in old if t<=cut)
    d=Data.load();b=[x for x in d.future4 if x['t']<LIMIT];f=features(b);sig=flags(b,f);c=copy.deepcopy(b)
    for x in c:
        if x['t']>=cut:
            for k in ['o','h','l','c']:x[k]*=3
    fc=features(c);sc=flags(c,fc)
    for i,x in enumerate(b):
        if x['t']<cut:
            assert all(f[k][i]==fc[k][i] for k in f)
            assert all(sig[k][i]==sc[k][i] for k in sig)
    try:simulate(d,b,f,sig,'D',cut,ms('2026-01-01'))
    except ValueError:pass
    else:raise AssertionError('candidate holdout lock failed')
    for k in ['A','B','C_simple','D']:
        for period in ['train','validation']:
            p=ROOT/f'reports/entries_v1/{k}_{period}_trades.csv'
            if not p.exists():continue
            with p.open() as handle:tr=list(csv.DictReader(handle))
            assert all(float(x['planned_risk_fraction'])<=.005+1e-12 for x in tr)
            assert all(int(x['signal_available_ms'])<=int(x['entry_ms']) and int(x['daily_source_open_ms'])+86400000<=int(x['entry_ms']) for x in tr)
    print('PASS: independent fill arithmetic, cost-aware sizing, causal daily/4H signals, initial risk cap, candidate holdout lock')
if __name__=='__main__':main()
