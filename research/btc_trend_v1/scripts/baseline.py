"""Frozen daily BTC regime benchmarks; no network, live orders or credentials."""
import argparse,bisect,csv,json,math,statistics
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];DAY=86400000;H4=14400000
def ms(s):return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp()*1000)
def iso(t):return datetime.fromtimestamp(t/1000,timezone.utc).isoformat()
def bars(name):
    return [dict(t=int(r[0]),o=float(r[1]),h=float(r[2]),l=float(r[3]),c=float(r[4]),v=float(r[5]),ct=int(r[6])) for r in json.loads((ROOT/'raw'/f'{name}.json').read_text())]
def normalize_mark(rows):
    # All acquired USD-M mark timestamps are milliseconds.
    return [dict(t=int(r[0]),o=float(r[1]),h=float(r[2]),l=float(r[3]),c=float(r[4]),ct=int(r[6])) for r in rows]
def check_sequence(rows,step):
    assert rows and len({r['t'] for r in rows})==len(rows)
    assert all(b['t']-a['t']==step for a,b in zip(rows,rows[1:]))
    assert all(r['ct']==r['t']+step-1 and 0<r['l']<=min(r['o'],r['c'])<=max(r['o'],r['c'])<=r['h'] for r in rows)
def indicators(d):
    out={};cl=[r['c'] for r in d]
    for i,r in enumerate(d):
        regime=i>=199 and cl[i]>statistics.fmean(cl[i-199:i+1]) and cl[i]>cl[i-90]
        vol=statistics.stdev([cl[j]/cl[j-1]-1 for j in range(i-59,i+1)])*math.sqrt(365) if i>=60 else None
        out[r['t']+DAY]={'available_ms':r['t']+DAY,'source_open_ms':r['t'],'regime':regime,'vol':vol}
    return out
def weight(kind,s):
    if kind in ('trend','vol_trend') and not s['regime']:return 0.
    return min(1.,0.20/s['vol']) if kind.startswith('vol_') and s['vol'] and s['vol']>0 else 1.
def rebalance_delta(q,equity,price,w,fee,slip):
    desired=w*equity/price-q
    cost=slip+fee*(1+slip if desired>=0 else 1-slip)
    return desired/(1+w*cost) if desired>=0 else desired/(1-w*cost)
def summary(daily,marks,episodes,initial,start,end):
    values=[initial]+[x['equity'] for x in daily];returns=[b/a-1 for a,b in zip(values,values[1:])]
    peak=initial;mdd=0.
    for x in marks:peak=max(peak,x['equity']);mdd=min(mdd,x['equity']/peak-1)
    # Low belongs to each bar; use the peak available before its close, avoiding future highs.
    peak=initial;intradd=0.
    for x in marks:intradd=min(intradd,x['intrabar_low_equity']/peak-1);peak=max(peak,x['equity'])
    pnl=[x['net_pnl'] for x in episodes];win=sum(x for x in pnl if x>0);loss=-sum(x for x in pnl if x<0)
    std=statistics.stdev(returns) if len(returns)>1 else 0
    years=(end-start)/DAY/365
    result={'return_pct':(values[-1]/initial-1)*100,'cagr_pct':((values[-1]/initial)**(1/years)-1)*100,'mdd_pct':mdd*100,'intrabar_low_mdd_pct':intradd*100,'sharpe':statistics.fmean(returns)/std*math.sqrt(365) if std else None,'realized_vol_pct':std*math.sqrt(365)*100,'episodes':len(pnl),'win_rate':sum(x>0 for x in pnl)/len(pnl) if pnl else None,'profit_factor':win/loss if loss else None,'avg_episode_pnl':statistics.fmean(pnl) if pnl else None,'final_equity':values[-1]}
    # Calendar-year return includes the preceding period end equity as denominator.
    annual={};prev=initial
    for x in daily:
        y=iso(x['t'])[:4]
        if y not in annual:annual[y]={'starting_equity':prev,'ending_equity':x['equity'],'days':0}
        annual[y]['ending_equity']=x['equity'];annual[y]['days']+=1;prev=x['equity']
    result['annual']={y:{'return_pct':(a['ending_equity']/a['starting_equity']-1)*100,'days':a['days']} for y,a in annual.items()}
    return result
@dataclass
class Data:
    spot:list; future:list; future4:list; mark4:list; funding:list
    @classmethod
    def load(cls):
        future_name='um_4h_canonical' if (ROOT/'raw/um_4h_canonical.json').exists() else 'um_4h'
        d=cls(bars('spot_1d'),bars('um_1d'),bars(future_name),normalize_mark(json.loads((ROOT/'raw/um_mark4h.json').read_text())),json.loads((ROOT/'raw/um_funding.json').read_text()))
        check_sequence(d.spot,DAY);check_sequence(d.future,DAY);check_sequence(d.future4,H4);check_sequence(d.mark4,H4)
        assert [r['t'] for r in d.future4]==[r['t'] for r in d.mark4]
        f=[int(r[0]) for r in d.funding]
        assert len(set(f))==len(f) and all(b//28800000-a//28800000==1 for a,b in zip(f,f[1:]))
        assert all(float(r[1])==8 and math.isfinite(float(r[2])) for r in d.funding)
        assert f[0]//DAY==d.future[0]['t']//DAY and f[-1]//DAY==d.future[-1]['t']//DAY
        return d
def run(data,market,kind,start,end,fee_bps=5,slip_bps=2,funding_order='before',retain=True,exposure_scale=1.):
    if not hasattr(data,'_signal'):data._signal=indicators(data.spot)
    signal=data._signal;fee=fee_bps/10000;slip=slip_bps/10000;initial=10000.;cash=initial;q=0.;fills=[];settlements=[];daily=[];marks=[];episodes=[];active=None;fund_total=fee_total=slip_total=0.;exposure=0.
    d=[r for r in (data.spot if market=='spot' else data.future) if start<=r['t']<end]
    assert len(d)==(end-start)//DAY
    m={r['t']:r for r in data.mark4};h={r['t']:r for r in data.future4}
    fr={int(r[0])//H4*H4:(int(r[0]),float(r[2])) for r in data.funding}
    def pay(t):
        nonlocal cash,fund_total
        if market!='um' or t not in fr:return
        ft,rate=fr[t];mark=m[t]['o'];amount=q*mark*rate;cash-=amount;fund_total+=amount
        if retain:settlements.append({'actual_time_ms':ft,'nominal_time_ms':t,'qty':q,'mark_open_proxy':mark,'rate':rate,'payment':amount})
    def trade(t,price,dq,reason,w=None,s=None):
        nonlocal cash,q,fee_total,slip_total
        if abs(dq)<1e-12:return
        fill=price*(1+slip if dq>0 else 1-slip);f=abs(dq)*fill*fee;sc=abs(dq)*price*slip
        cash-=dq*fill+f;q+=dq;fee_total+=f;slip_total+=sc
        if abs(q)<1e-12:q=0.
        if retain:fills.append({'time_ms':t,'time_utc':iso(t),'reason':reason,'side':'BUY' if dq>0 else 'SELL','qty':abs(dq),'reference_price':price,'fill_price':fill,'fee':f,'slippage_cost':sc,'target_weight':w,'regime_source_open_ms':s['source_open_ms'] if s else None,'signal_available_ms':s['available_ms'] if s else None,'equity_after':cash+q*price})
    for r in d:
        t=r['t'];s=signal[t];assert s['available_ms']<=t and s['source_open_ms']+DAY<=t
        equity_before=cash+q*r['o'];held_before=q>0
        if funding_order=='before':pay(t)
        w=weight(kind,s)*exposure_scale;eq=cash+q*r['o'];dq=rebalance_delta(q,eq,r['o'],w,fee,slip)
        if not held_before and dq>1e-12:active={'entry_ms':t,'entry_price_reference':r['o'],'equity_before':equity_before,'initial_qty':dq}
        trade(t,r['o'],dq,'DAILY_REBALANCE',w,s)
        if held_before and q==0 and active:
            active.update(exit_ms=t,exit_price_reference=r['o'],net_pnl=cash-active['equity_before'],terminal=False);episodes.append(active);active=None
        if funding_order=='after':pay(t)
        assert q>=-1e-10
        exposure+=w
        if market=='um':
            for k in range(6):
                bt=t+k*H4
                if k:pay(bt)
                bm=m[bt]
                marks.append({'t':bt+H4-1,'equity':cash+q*bm['c'],'intrabar_low_equity':cash+q*bm['l'],'qty':q})
            close_equity=cash+q*m[t+5*H4]['c']
        else:
            close_equity=cash+q*r['c'];marks.append({'t':t+DAY-1,'equity':close_equity,'intrabar_low_equity':cash+q*r['l'],'qty':q})
        daily.append({'t':t+DAY-1,'equity':close_equity,'weight':w})
    last=d[-1]
    if q:
        trade(end-1,last['c'],-q,'TERMINAL_EXIT')
        if active:active.update(exit_ms=end-1,exit_price_reference=last['c'],net_pnl=cash-active['equity_before'],terminal=True);episodes.append(active)
        marks.append({'t':end-1,'equity':cash,'intrabar_low_equity':cash,'qty':0.})
        daily[-1]['equity']=cash
    result=summary(daily,marks,episodes,initial,start,end)
    result.update(market=market,strategy=kind,start=iso(start),end_exclusive=iso(end),fee_bps=fee_bps,slip_bps=slip_bps,funding_boundary_convention=funding_order,net_funding_paid=fund_total,fees_paid=fee_total,slippage_cost=slip_total,mean_target_weight=exposure/len(d),exposure_scale=exposure_scale,mdd_sampling='4H mark close' if market=='um' else 'daily traded close')
    return {'metrics':result,'daily_equity':daily,'mark_equity':marks,'fills':fills,'funding':settlements,'episodes':episodes}
def write_csv(path,rows):
    if not rows:return
    with path.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def main():
    data=Data.load();periods={'full':('2020-01-01','2026-10-01'),'claim_window':('2021-01-01','2026-10-01'),'train':('2020-01-01','2023-01-01'),'validation':('2023-01-01','2025-01-01'),'retrospective_holdout':('2025-01-01','2026-10-01')};results=[];curves={}
    out=ROOT/'reports/baseline_v1';out.mkdir(parents=True,exist_ok=True)
    for market in ['spot','um']:
        for kind in ['hold','trend','vol_hold','vol_trend']:
            for pname,(a,b) in periods.items():
                for cost,fb,sb in [('base',5,2),('double',10,4),('zero_execution_cost',0,0)]:
                    detailed=pname=='claim_window' and cost=='base'
                    r=run(data,market,kind,ms(a),ms(b),fb,sb,retain=detailed);r['metrics']['period']=pname;r['metrics']['cost_case']=cost;results.append(r['metrics'])
                    if detailed:
                        key=f'{market}_{kind}';curves[key]=r['daily_equity']
                        for field in ['fills','funding','episodes']:write_csv(out/f'{key}_{field}.csv',r[field])
                        (out/f'{key}_equity.json').write_text(json.dumps(r['daily_equity'],separators=(',',':')))
            r=run(data,market,kind,ms('2021-01-01'),ms('2026-10-01'),funding_order='after',retain=False);r['metrics'].update(period='claim_window',cost_case='funding_after_rebalance');results.append(r['metrics'])
    matched=[];funding_off=[]
    # Train-only scaling to a common 10% annual realized-vol reference. Never fit holdout.
    for kind in ['hold','trend','vol_hold','vol_trend']:
        tr=next(x for x in results if x['market']=='um' and x['strategy']==kind and x['period']=='train' and x['cost_case']=='base')
        scale=min(1.,10/tr['realized_vol_pct'])
        for pn,(a,b) in periods.items():
            z=run(data,'um',kind,ms(a),ms(b),retain=False,exposure_scale=scale)['metrics'];z.update(period=pn,train_reference_vol_target_pct=10,train_unscaled_vol_pct=tr['realized_vol_pct']);matched.append(z)
        nofund=Data(data.spot,data.future,data.future4,data.mark4,[])
        z=run(nofund,'um',kind,ms('2021-01-01'),ms('2026-10-01'),retain=False)['metrics'];z['diagnostic']='funding disabled ONLY to isolate impact; not realistic futures return';funding_off.append(z)
    report={'spec':'BASELINE_SPEC.md','status':'independent benchmark; original numerical claims not authenticated','funding_valuation':'actual rates; 4H mark open at nominal settlement is proxy for 0-47ms delayed settlement mark','matched_train_risk_note':'10% annual reference; constant exposure multipliers estimated ONLY on 2020-2022, capped at 1. This does not force equal future realized risk.','matched_train_risk':matched,'funding_disabled_diagnostic':funding_off,'results':results}
    (out/'metrics.json').write_text(json.dumps(report,indent=2));write_csv(out/'summary.csv',[{k:v for k,v in r.items() if k!='annual'} for r in results])
    print(json.dumps([r for r in results if r['period']=='claim_window' and r['cost_case']=='base'],indent=2))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,1,figsize=(11,7),sharex=True,gridspec_kw={'height_ratios':[2,1]})
    for key in ['um_hold','um_trend','um_vol_hold','um_vol_trend']:
        c=curves[key];x=[datetime.fromtimestamp(v['t']/1000,timezone.utc) for v in c];y=[v['equity']/10000 for v in c];peak=1.;dd=[]
        for v in y:peak=max(peak,v);dd.append((v/peak-1)*100)
        label=key.replace('um_','').replace('_',' ');axes[0].plot(x,y,label=label);axes[1].plot(x,dd,label=label)
    axes[0].set(ylabel='Equity / initial capital',title='BTC USD-M daily benchmarks | Jan 2021 - Sep 2026 | net costs + funding');axes[1].set(ylabel='Daily-close drawdown (%)');axes[0].legend(ncol=2);[ax.grid(alpha=.2) for ax in axes];fig.tight_layout();fig.savefig(out/'equity_drawdown.svg');fig.savefig(out/'equity_drawdown.png',dpi=140);plt.close(fig)
if __name__=='__main__':main()
