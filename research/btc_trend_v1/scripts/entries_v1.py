"""Frozen 4H entry screening; deliberately refuses candidate periods after 2024."""
import json,math,statistics,bisect
from pathlib import Path
from baseline import Data,ROOT,DAY,H4,ms,iso,indicators,summary,write_csv
LIMIT=ms('2025-01-01')
def features(b):
    atr=[];adx=[];e20=[];e50=[];tr=[];plus=[];minus=[];dx=[];smtr=smp=smm=None;ad=None
    for i,r in enumerate(b):
        pc=b[i-1]['c'] if i else r['c']
        tr.append(max(r['h']-r['l'],abs(r['h']-pc),abs(r['l']-pc)))
        up=r['h']-b[i-1]['h'] if i else 0;down=b[i-1]['l']-r['l'] if i else 0
        plus.append(up if up>0 and up>down else 0);minus.append(down if down>0 and down>up else 0)
        e20.append(r['c'] if not i else e20[-1]+2/21*(r['c']-e20[-1]));e50.append(r['c'] if not i else e50[-1]+2/51*(r['c']-e50[-1]))
        if i<13:atr.append(None);adx.append(None);continue
        if i==13:smtr=statistics.fmean(tr[:14]);smp=statistics.fmean(plus[:14]);smm=statistics.fmean(minus[:14])
        else:smtr=(13*smtr+tr[-1])/14;smp=(13*smp+plus[-1])/14;smm=(13*smm+minus[-1])/14
        atr.append(smtr);pd=100*smp/smtr if smtr else 0;md=100*smm/smtr if smtr else 0;dx.append(100*abs(pd-md)/(pd+md) if pd+md else 0)
        if len(dx)==14:ad=statistics.fmean(dx)
        elif len(dx)>14:ad=(13*ad+dx[-1])/14
        adx.append(ad)
    return {'atr':atr,'adx':adx,'ema20':e20,'ema50':e50}
def flags(b,f):
    out={k:[False]*len(b) for k in ['A','B','C','C_simple','D']};pending=None
    for i in range(200,len(b)):
        r=b[i];a=f['atr'][i];ph=max(x['h'] for x in b[i-20:i]);pl=min(x['l'] for x in b[i-20:i]);bull=f['ema20'][i]>f['ema50'][i]
        out['A'][i]=bull and r['l']<=f['ema20'][i] and r['c']>f['ema20'][i] and r['c']>b[i-1]['h']
        sweep=r['l']<pl and r['c']>pl;out['C_simple'][i]=sweep;out['C'][i]=sweep and r['c']>r['o'] and bull and r['c']>f['ema20'][i]
        out['D'][i]=r['c']>ph and f['adx'][i]>=20 and a>statistics.fmean(f['atr'][i-20:i])
        if pending:
            level,born=pending
            if i-born>6 or r['c']<level-.5*a:pending=None
            elif r['l']<=level+.25*a and r['c']>level and r['c']>r['o']:out['B'][i]=True;pending=None
        # A fresh pending breakout cannot also produce a retest signal in this bar.
        if pending is None and not out['B'][i] and r['c']>ph:pending=(ph,i)
    return out
def simulate(data,b,f,sigs,kind,start,end,risk=.005,fee_bps=5,slip_bps=2,retain=True,execution_1h=None):
    if end>LIMIT:raise ValueError('candidate holdout locked: periods after 2024 are forbidden')
    signal=indicators(data.spot);fee=fee_bps/10000;slip=slip_bps/10000;cash=10000.;q=0.;stop=None;peak_price=None;active=None;trades=[];fills=[];funds=[];marks=[];daily=[];totalfund=fees=slippage=0.;signals=eligible=0;rejected=0;bars_held=0
    mark={r['t']:r for r in data.mark4};fund={int(r[0])//H4*H4:(int(r[0]),float(r[2])) for r in data.funding};st=sorted(signal);startidx=bisect.bisect_left([r['t'] for r in b],start);endidx=bisect.bisect_left([r['t'] for r in b],end)
    assert endidx-startidx==(end-start)//H4
    def execute(t,price,dq,reason):
        nonlocal cash,q,fees,slippage
        fill=price*(1+slip if dq>0 else 1-slip);fc=abs(dq)*fill*fee;sc=abs(dq)*price*slip
        cash-=dq*fill+fc;q+=dq;fees+=fc;slippage+=sc
        if abs(q)<1e-12:q=0.
        if retain:fills.append({'time_ms':t,'time_utc':iso(t),'reason':reason,'side':'BUY' if dq>0 else 'SELL','qty':abs(dq),'reference_price':price,'fill_price':fill,'commission':fc,'slippage_cost':sc})
        return fill
    def close(t,price,reason,terminal=False):
        nonlocal active,stop,peak_price
        fill=execute(t,price,-q,reason);active.update(exit_ms=t,exit_price=fill,exit_reason=reason,net_pnl=cash-active['equity_before'],terminal=terminal);active['net_r']=active['net_pnl']/active['planned_initial_loss'];trades.append(active);active=None;stop=None;peak_price=None
    for i in range(startidx,endidx):
        r=b[i];t=r['t'];m=mark[t];low_before=cash+q*m['l']
        path=[r] if execution_1h is None else [execution_1h[t+k*3600000] for k in range(4) if execution_1h[t+k*3600000]['v']>0]
        if not path:raise ValueError('entire 4H interval has no executable hourly prints')
        trade_t=path[0]['t']
        if t in fund:
            ft,rate=fund[t];payment=q*m['o']*rate;cash-=payment;totalfund+=payment
            if retain:funds.append({'actual_time_ms':ft,'nominal_time_ms':t,'qty':q,'mark_open_proxy':m['o'],'rate':rate,'payment':payment})
        s=signal[st[bisect.bisect_right(st,t)-1]];assert s['available_ms']<=t
        was_open=q>0
        if q and not s['regime']:close(trade_t,r['o'],'REGIME_EXIT')
        elif q and r['o']<=stop:close(trade_t,r['o'],'GAP_STOP')
        # A signal that arose while already in position is not a same-bar re-entry.
        if not was_open and i>0 and sigs[kind][i-1]:
            signals+=1
            if s['regime']:
                eligible+=1;eq=cash;entry=r['o']*(1+slip);sl=r['o']-2*f['atr'][i-1];slfill=sl*(1-slip);loss=entry-slfill+fee*(entry+slfill)
                if sl<=0 or loss<=0:rejected+=1
                else:
                    size=min(eq*risk/loss,eq/(entry*(1+fee)));planned=size*loss
                    if size>0:
                        active={'strategy':kind,'signal_bar_open_ms':b[i-1]['t'],'signal_available_ms':b[i-1]['t']+H4,'entry_ms':trade_t,'entry_utc':iso(trade_t),'entry_price':entry,'initial_sl':sl,'tp':None,'qty':size,'equity_before':eq,'planned_initial_loss':planned,'planned_risk_fraction':planned/eq,'nominal_cap_bound':size<eq*risk/loss-1e-10,'daily_source_open_ms':s['source_open_ms']}
                        assert active['signal_available_ms']<=trade_t and s['source_open_ms']+DAY<=trade_t
                        execute(trade_t,r['o'],size,'ENTRY');stop=sl;peak_price=r['o']
        if q:
            bars_held+=1
            for h in path:
                if not q:break
                if h['o']<=stop:close(h['t'],h['o'],'GAP_STOP' if execution_1h is None else 'GAP_STOP_1H')
                elif h['l']<=stop:close(h['t'],stop,'INTRABAR_STOP' if execution_1h is None else 'INTRABAR_STOP_1H')
            if q:
                peak_price=max(peak_price,r['h']);stop=max(stop,peak_price-3*f['atr'][i])
        eq=cash+q*m['c']
        # 4H close MDD is primary. The low proxy below is not a path-exact trade MDD.
        marks.append({'t':t+H4-1,'equity':eq,'intrabar_low_equity':min(eq,low_before if was_open else eq),'qty':q})
        if (t+H4)%DAY==0:daily.append({'t':t+H4-1,'equity':eq,'weight':None})
    if q:
        close(end-1,b[endidx-1]['c'],'TERMINAL_EXIT',True);daily[-1]['equity']=cash;marks.append({'t':end-1,'equity':cash,'intrabar_low_equity':cash,'qty':0.})
    met=summary(daily,marks,trades,10000.,start,end);rr=[x['net_r'] for x in trades];losses=0;streak=0
    for x in rr:streak=streak+1 if x<0 else 0;losses=max(losses,streak)
    met.update(strategy=kind,start=iso(start),end_exclusive=iso(end),risk_fraction=risk,fee_bps=fee_bps,slip_bps=slip_bps,expectancy_net_r=statistics.fmean(rr) if rr else None,total_net_r=sum(rr),profit_factor_r=sum(x for x in rr if x>0)/-sum(x for x in rr if x<0) if any(x<0 for x in rr) else None,max_losing_streak=losses,signals_while_flat=signals,eligible_signals=eligible,invalid_risk_rejections=rejected,net_funding_paid=totalfund,fees_paid=fees,slippage_cost=slippage,bars_held_fraction=bars_held/(endidx-startidx),candidate_holdout_evaluated=False,execution_resolution='4H' if execution_1h is None else '1H',mdd_sampling='4H mark close',intrabar_low_mdd_note='coarse conservative proxy; not a path-exact execution drawdown')
    return {'metrics':met,'trades':trades,'fills':fills,'funding':funds,'daily_equity':daily}
def main():
    data=Data.load();b=[r for r in data.future4 if r['t']<LIMIT];f=features(b);sigs=flags(b,f);out=ROOT/'reports/entries_v1';out.mkdir(parents=True,exist_ok=True);results=[];curves={}
    for kind in ['A','B','C','C_simple','D']:
        for period,(a,z) in {'train':('2020-01-01','2023-01-01'),'validation':('2023-01-01','2025-01-01')}.items():
            for case,risk,fb,sb in [('base',.005,5,2),('double_cost',.005,10,4),('risk_1pct',.01,5,2)]:
                r=simulate(data,b,f,sigs,kind,ms(a),ms(z),risk,fb,sb,retain=case=='base');r['metrics'].update(period=period,case=case);results.append(r['metrics'])
                if case=='base':
                    for field in ['trades','fills','funding']:write_csv(out/f'{kind}_{period}_{field}.csv',r[field])
                    (out/f'{kind}_{period}_equity.json').write_text(json.dumps(r['daily_equity'],separators=(',',':')))
                    if period=='validation':curves[kind]=r['daily_equity']
    verdict={}
    for kind in ['A','B','C','C_simple','D']:
        v=next(x for x in results if x['strategy']==kind and x['period']=='validation' and x['case']=='base');stress=next(x for x in results if x['strategy']==kind and x['period']=='validation' and x['case']=='double_cost')
        checks={'20_validation_trades':v['episodes']>=20,'positive_net_expectancy':v['expectancy_net_r'] is not None and v['expectancy_net_r']>0,'pf_above_1':v['profit_factor_r'] is not None and v['profit_factor_r']>1,'mdd_below_15pct':v['mdd_pct']>-15,'nonnegative_double_cost_expectancy':stress['expectancy_net_r'] is not None and stress['expectancy_net_r']>=0};verdict[kind]={'screen_pass':all(checks.values()),'checks':checks}
    report={'spec':'ENTRY_SPEC_V1.md','status':'provisional 4H screening only; holdout locked; no live eligibility','results':results,'verdict':verdict}
    (out/'metrics.json').write_text(json.dumps(report,indent=2));write_csv(out/'summary.csv',[{k:v for k,v in x.items() if k!='annual'} for x in results]);print(json.dumps([x for x in results if x['case']=='base'],indent=2));print(json.dumps(verdict,indent=2))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,1,figsize=(10,6),sharex=True)
    from datetime import datetime,timezone
    for kind,c in curves.items():
        xx=[datetime.fromtimestamp(x['t']/1000,timezone.utc) for x in c];y=[x['equity']/10000 for x in c];peak=1.;dd=[]
        for value in y:peak=max(peak,value);dd.append((value/peak-1)*100)
        axes[0].plot(xx,y,label=kind);axes[1].plot(xx,dd)
    axes[0].set(title='Frozen BTC 4H entry screening | Validation 2023-2024 | 0.5% risk',ylabel='Equity / initial capital');axes[1].set(ylabel='Daily-close drawdown (%)');axes[0].legend(ncol=5);[ax.grid(alpha=.2) for ax in axes];fig.tight_layout();fig.savefig(out/'validation_curves.svg');fig.savefig(out/'validation_curves.png',dpi=140);plt.close(fig)
if __name__=='__main__':main()
