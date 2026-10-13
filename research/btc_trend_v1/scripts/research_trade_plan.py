"""Pure D-fixed3 research planner. Produces a plan, never sends an order."""
import statistics,math
from entries_v1 import features
from baseline import DAY,H4
def plan_d_fixed3(daily,closed_4h,next_open_reference,equity,asof_ms,risk_fraction=.005,fee_bps=5,slippage_bps=2):
    if not (0<risk_fraction<=.01 and equity>0 and next_open_reference>0):raise ValueError('invalid risk/equity/reference price')
    d=[r for r in daily if r['t']+DAY<=asof_ms];b=[r for r in closed_4h if r['t']+H4<=asof_ms]
    if len(d)<200 or len(b)<201:return {'action':'WAIT','reason':'WARMUP_INCOMPLETE'}
    # A stale signal cannot be carried into an arbitrary future execution window.
    if not (b[-1]['t']+H4<=asof_ms<b[-1]['t']+2*H4):return {'action':'WAIT','reason':'STALE_4H_SIGNAL'}
    regime=d[-1]['c']>statistics.fmean(r['c'] for r in d[-200:]) and d[-1]['c']>d[-91]['c']
    if not regime:return {'action':'WAIT','reason':'DAILY_REGIME_FALSE'}
    f=features(b);i=len(b)-1;r=b[i]
    if not (r['c']>max(x['h'] for x in b[i-20:i]) and f['adx'][i]>=20 and f['atr'][i]>statistics.fmean(f['atr'][i-20:i])):return {'action':'WAIT','reason':'NO_FROZEN_D_BREAKOUT'}
    fee=fee_bps/10000;slip=slippage_bps/10000;entry=next_open_reference*(1+slip);sl=next_open_reference-2*f['atr'][i]
    if sl<=0:return {'action':'WAIT','reason':'INVALID_STOP'}
    stop_fill=sl*(1-slip);loss_per_btc=entry-stop_fill+fee*(entry+stop_fill);qty=min(equity*risk_fraction/loss_per_btc,equity/(entry*(1+fee)));tp=entry+3*(entry-sl)
    return {'action':'RESEARCH_PLAN_ONLY','strategy':'D_fixed3','signal_available_ms':r['t']+H4,'daily_available_ms':d[-1]['t']+DAY,'entry_reference':next_open_reference,'assumed_entry_fill':entry,'initial_sl_reference':sl,'tp_reference':tp,'qty_continuous_btc':qty,'notional_at_assumed_fill':qty*entry,'planned_loss_including_stop_fill_cost':qty*loss_per_btc,'risk_fraction_used':qty*loss_per_btc/equity,'exit_rules':['initial stop','fixed 3R target','closed daily regime invalidation'],'live_orders_enabled':False,'qualification':'pre-frozen runner-up/control; requires new forward validation before promotion'}
