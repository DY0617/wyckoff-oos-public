"""Select from train/validation only. Writes and hashes the frozen registry."""
import json,math,hashlib
from datetime import datetime,timezone
from baseline import ROOT,Data,bars,ms,write_csv
from selection_engine_v2 import Engine,configs,neighbors
PERIODS={'train':(ms('2020-01-01'),ms('2023-01-01')),'validation':(ms('2023-01-01'),ms('2025-01-01'))}
def calmar(m):return m['cagr_pct']/max(abs(m['mdd_pct']),1e-6)
def main():
    out=ROOT/'reports/final_v2';out.mkdir(parents=True,exist_ok=True)
    if (out/'holdout_opened.json').exists():raise RuntimeError('holdout already opened; reselection is prohibited')
    d=Data.load();h=bars('um_1h_train_validation')+bars('um_1h_holdout');e=Engine(d,h);all_results=[];rank=[];center_cache={};neighbor_rows=[]
    for p in configs():
        native={}
        for period,(a,b) in PERIODS.items():
            r=e.simulate(p,a,b,retain=True);native[period]=r['metrics'];center_cache[(p['id'],period)]=r
            for field in ['trades','fills','funding','trail_events']:
                rows=r.get(field,[])
                if rows:write_csv(out/f'{p["id"]}_{period}_{field}.csv',rows)
        vol=native['train']['realized_vol_pct'];scale=min(1.,2/vol) if vol>0 else 0;scaled={};stress={}
        for period,(a,b) in PERIODS.items():
            scaled[period]=e.simulate(p,a,b,scale)['metrics'];stress[period]=e.simulate(p,a,b,scale,10,4)['metrics']
            all_results.append({'model_id':p['id'],'period':period,'native':native[period],'common_train_risk':scaled[period],'double_cost_common_risk':stress[period],'scale':scale})
        checks={'positive_both_periods_base':all(x['return_pct']>0 for x in scaled.values()),'positive_both_periods_double_cost':all(x['return_pct']>0 for x in stress.values()),'enough_trades':p['kind']=='daily' or all(x['episodes']>=20 for x in native.values()),'native_drawdown':p['kind']=='daily' or all(x['mdd_pct']>-10 for x in native.values())}
        ns=neighbors(p);passing=0
        for n in ns:
            vals={}
            for period,(a,b) in PERIODS.items():vals[period]=e.simulate(n,a,b,fee_bps=10,slip_bps=4)['metrics']
            good=all(x['return_pct']>0 for x in vals.values());passing+=good;neighbor_rows.append({'center':p['id'],'neighbor':n,'both_periods_positive_double_cost':good,'periods':vals})
        fraction=passing/len(ns) if ns else 1.;checks['neighbor_75pct_positive']=fraction>=.75
        row={'id':p['id'],'config':p,'scale':scale,'score_min_calmar':min(calmar(x) for x in scaled.values()),'stress_score_min_calmar':min(calmar(x) for x in stress.values()),'neighbor_fraction':fraction,'eligible':all(checks.values()),'checks':checks,'train_native':native['train'],'validation_native':native['validation']};rank.append(row);print('TESTED',p['id'],'eligible',row['eligible'],'score',round(row['score_min_calmar'],4),'neighbor_fraction',fraction,flush=True)
    rank.sort(key=lambda r:(r['eligible'],r['score_min_calmar'],r['stress_score_min_calmar']),reverse=True)
    (out/'selection_training_validation.json').write_text(json.dumps({'spec':'FINAL_SELECTION_SPEC.md','candidate_holdout_evaluated':False,'rankings':rank,'results':all_results,'neighbors':neighbor_rows},indent=2))
    eligible=[x for x in rank if x['eligible']]
    if not eligible:raise RuntimeError('No center passed the predeclared train/validation gates; no holdout winner may be invented')
    win=eligible[0];controls=[]
    for identity in ['daily_vol_trend','D_trail','C_simple_trail']:
        r=next(x for x in rank if x['id']==identity)
        if r['config']!=win['config']:controls.append({'label':identity,'config':r['config'],'scale':r['scale']})
    if len(eligible)>1:
        second=eligible[1]
        controls.append({'label':'runner_up_common_risk','config':second['config'],'scale':second['scale']})
        controls.append({'label':'runner_up_native_risk','config':second['config'],'scale':1.})
    if not math.isclose(win['scale'],1):controls.append({'label':'winner_native_risk','config':win['config'],'scale':1.})
    frozen={'created_utc':datetime.now(timezone.utc).isoformat(),'selection_spec_sha256':hashlib.sha256((ROOT/'FINAL_SELECTION_SPEC.md').read_bytes()).hexdigest(),'engine_sha256':hashlib.sha256((ROOT/'scripts/selection_engine_v2.py').read_bytes()).hexdigest(),'winner':{'label':win['id'],'config':win['config'],'scale':win['scale']},'controls':controls,'ranking_uses_candidate_holdout':False,'primary_common_train_vol_target_pct':2,'declared_native_risk_fraction':.005 if win['config']['kind']!='daily' else None,'winner_score':win['score_min_calmar'],'winner_neighbor_fraction':win['neighbor_fraction']}
    raw=json.dumps(frozen,sort_keys=True,indent=2).encode();(out/'frozen_selection.json').write_bytes(raw);(out/'frozen_selection.sha256').write_text(hashlib.sha256(raw).hexdigest()+'\n');print('FROZEN',json.dumps(frozen,indent=2),flush=True)
if __name__=='__main__':main()
