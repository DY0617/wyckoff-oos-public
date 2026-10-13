"""Evaluate sealed winner/controls without reselection or parameter changes."""
import json,hashlib,math,argparse
from datetime import datetime,timezone
from baseline import ROOT,Data,bars,ms,write_csv
from selection_engine_v2 import Engine
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--replay',action='store_true',help='Replay existing frozen identities into a separate folder; never call this new OOS');args=parser.parse_args()
    registry_dir=ROOT/'reports/final_v2';out=ROOT/'reports/final_v2_replay' if args.replay else registry_dir;out.mkdir(parents=True,exist_ok=True)
    raw=(registry_dir/'frozen_selection.json').read_bytes();f=json.loads(raw);sha=hashlib.sha256(raw).hexdigest()
    assert sha==(registry_dir/'frozen_selection.sha256').read_text().strip()
    assert f['engine_sha256']==hashlib.sha256((ROOT/'scripts/selection_engine_v2.py').read_bytes()).hexdigest()
    assert f['selection_spec_sha256']==hashlib.sha256((ROOT/'FINAL_SELECTION_SPEC.md').read_bytes()).hexdigest()
    marker=out/'holdout_opened.json'
    if marker.exists() and not args.replay:raise RuntimeError('candidate holdout already opened; use --replay only for unchanged-model reproduction')
    audit=json.loads((ROOT/'reports/final_hourly_data_audit.json').read_text());assert not audit['ohlc_discrepancies'] and audit['hours']==59160
    data=Data.load();hours=bars('um_1h_train_validation')+bars('um_1h_holdout');e=Engine(data,hours)
    hashes={name:hashlib.sha256((ROOT/'raw'/name).read_bytes()).hexdigest() for name in ['spot_1d.json','um_1d.json','um_4h_canonical.json','um_mark4h.json','um_funding.json','um_1h_train_validation.json','um_1h_holdout.json']}
    if args.replay:
        original=json.loads((registry_dir/'holdout_opened.json').read_text())
        if hashes!=original['data_sha256']:raise ValueError('replay input hashes changed; original OOS cannot be reproduced on different data')
    opening={'opened_utc':datetime.now(timezone.utc).isoformat(),'frozen_registry_sha256':sha,'data_sha256':hashes,'winner_fixed_before_opening':f['winner'],'kind':'replay of existing holdout' if args.replay else 'retrospective holdout, not provably untouched across earlier projects','no_reselection_after_opening':True,'is_replay':args.replay}
    # Written before first holdout strategy return is calculated.
    marker.write_text(json.dumps(opening,indent=2))
    cases=[f['winner'],*f['controls']];results=[];curves={};native_winner=None
    for case in cases:
        for cost,fb,sb in [('base',5,2),('double_cost',10,4)]:
            detailed=cost=='base';r=e.simulate(case['config'],ms('2025-01-01'),ms('2026-10-01'),case['scale'],fb,sb,retain=detailed,frozen=f);m=r['metrics'];m.update(label=case['label'],cost_case=cost,holdout_start='2025-01-01',holdout_end_exclusive='2026-10-01');results.append(m)
            if detailed:
                for field in ['trades','fills','funding','trail_events']:
                    rows=r.get(field,[])
                    if rows:write_csv(out/f'holdout_{case["label"]}_{field}.csv',rows)
                (out/f'holdout_{case["label"]}_equity.json').write_text(json.dumps(r['daily_equity'],separators=(',',':')));curves[case['label']]=r['daily_equity']
            if case['config']==f['winner']['config'] and math.isclose(case['scale'],1):
                if cost=='base':native_winner=m
                else:native_stress=m
    if native_winner is None:raise RuntimeError('native winner risk case missing from frozen registry')
    gates={'positive_holdout_base':native_winner['return_pct']>0,'nonnegative_double_cost':native_stress['return_pct']>=0,'native_mdd_at_most_10pct':native_winner['mdd_pct']>=-10,'at_least_15_holdout_trades':f['winner']['config']['kind']=='daily' or native_winner['episodes']>=15}
    verdict={'winner_id':f['winner']['label'],'winner_fixed_before_holdout':True,'paper_screen_pass':all(gates.values()),'gates':gates,'live_approved':False,'limitations':['retrospective period previously exposed in other research','assumed fees/slippage and continuous sizes','funding mark is boundary proxy','4H mark-close MDD','no true forward OOS or exchange precision/depth/liquidation validation']}
    full=e.simulate(f['winner']['config'],ms('2020-01-01'),ms('2026-10-01'),1.,retain=True,frozen=f)
    for field in ['trades','fills','funding','trail_events']:
        rows=full.get(field,[])
        if rows:write_csv(out/f'winner_full_{field}.csv',rows)
    (out/'winner_full_equity.json').write_text(json.dumps(full['daily_equity'],separators=(',',':')))
    report={'frozen_registry_sha256':sha,'opening':opening,'holdout_results':results,'winner_full_native':full['metrics'],'verdict':verdict};(out/'final_results.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(2,1,figsize=(11,7),sharex=True,gridspec_kw={'height_ratios':[2,1]})
    cc=full['daily_equity'];xx=[datetime.fromtimestamp(x['t']/1000,timezone.utc) for x in cc];yy=[x['equity']/10000 for x in cc];peak=1.;dd=[]
    for v in yy:peak=max(peak,v);dd.append((v/peak-1)*100)
    ax[0].plot(xx,yy,label=f['winner']['label']);ax[1].plot(xx,dd);ax[0].set(title='Frozen selected BTC strategy | Native risk | Net fees, slippage and funding',ylabel='Equity / initial capital');ax[1].set(ylabel='Daily-close drawdown (%)');ax[0].legend();ax[0].axvline(datetime(2025,1,1,tzinfo=timezone.utc),color='gray',linestyle='--');ax[1].axvline(datetime(2025,1,1,tzinfo=timezone.utc),color='gray',linestyle='--');[a.grid(alpha=.2) for a in ax];fig.tight_layout();fig.savefig(out/'winner_full_curve.svg');fig.savefig(out/'winner_full_curve.png',dpi=150);plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,5))
    for label in [f['winner']['label'],'daily_vol_trend','runner_up_common_risk']:
        if label not in curves:continue
        c=curves[label];ax.plot([datetime.fromtimestamp(x['t']/1000,timezone.utc) for x in c],[x['equity']/10000 for x in c],label=label)
    ax.set(title='Pre-frozen holdout comparison | Same train-volatility reference | 2025-Sep 2026',ylabel='Equity / initial capital');ax.legend();ax.grid(alpha=.2);fig.tight_layout();fig.savefig(out/'holdout_common_risk.svg');fig.savefig(out/'holdout_common_risk.png',dpi=150);plt.close(fig)
if __name__=='__main__':main()
