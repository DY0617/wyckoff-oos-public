"""Frozen v2 exit accounting and research-plan parity checks."""
import math,csv,json
from baseline import Data,bars,ms,ROOT
from selection_engine_v2 import Engine,configs
from research_trade_plan import plan_d_fixed3
def main():
    data=Data.load();e=Engine(data,bars('um_1h_train_validation'))
    for p in configs():
        if p['kind']=='daily':continue
        r=e.simulate(p,ms('2023-01-01'),ms('2025-01-01'),retain=True)
        assert math.isclose(sum(t['net_pnl'] for t in r['trades']),r['metrics']['final_equity']-10000,abs_tol=1e-7)
        assert math.isclose(sum(x['payment'] for x in r['funding']),r['metrics']['net_funding_paid'],abs_tol=1e-7)
        for t in r['trades']:
            assert t['signal_available_ms']<=t['entry_ms'] and t['daily_source_open_ms']+86400000<=t['entry_ms']
            assert t['planned_risk_fraction']<=.005+1e-12
            fs=[x for x in r['fills'] if t['entry_ms']<=x['interval_start_ms']<=t['exit_ms']]
            assert math.isclose(sum(x['qty'] for x in fs if x['side']=='SELL'),t['qty'],rel_tol=1e-9,abs_tol=1e-8)
        try:e.simulate(p,ms('2025-01-01'),ms('2026-10-01'))
        except ValueError:pass
        else:raise AssertionError('unfrozen holdout guard failed')
    p=next(x for x in configs() if x['id']=='D_trail');r=e.simulate(p,ms('2023-01-01'),ms('2025-01-01'))
    old=json.loads((ROOT/'reports/entries_1h/metrics.json').read_text());v=next(x for x in old['results'] if x['strategy']=='D' and x['period']=='validation')
    for k in ['return_pct','mdd_pct','total_net_r','net_funding_paid']:assert math.isclose(r['metrics'][k],v[k],rel_tol=1e-10,abs_tol=1e-8)
    source=ROOT/'reports/final_v2/full_control_runner_up_native_risk_trades.csv'
    if source.exists():
        with source.open() as handle:t=next(csv.DictReader(handle))
        plan=plan_d_fixed3(data.spot,data.future4,float(t['entry_price'])/1.0002,float(t['equity_before']),int(t['entry_ms']))
        assert plan['action']=='RESEARCH_PLAN_ONLY' and not plan['live_orders_enabled']
        for key,col in [('assumed_entry_fill','entry_price'),('initial_sl_reference','initial_sl'),('tp_reference','tp2'),('qty_continuous_btc','qty')]:assert math.isclose(plan[key],float(t[col]),rel_tol=1e-10)
    print('PASS: all 12 centers accounting/quantity/risk/causality; original D parity; frozen holdout guard; pure planner parity')
if __name__=='__main__':main()
