"""Finite frozen-exit experiment engine. Original v1 holdout lock is unchanged."""
import bisect,json,math,statistics
from baseline import ROOT,Data,DAY,H4,ms,iso,indicators,summary,run as daily_run
from entries_v1 import features
HOLDOUT=ms('2025-01-01')
class Engine:
    def __init__(self,data,hours):
        self.data=data;self.b=data.future4;self.bt=[x['t'] for x in self.b];self.f=features(self.b);self.h={x['t']:x for x in hours};self.m={x['t']:x for x in data.mark4};self.fr={int(x[0])//H4*H4:(int(x[0]),float(x[2])) for x in data.funding};self.signal=indicators(data.spot);self.st=sorted(self.signal);self.flag_cache={}
    def flags(self,kind,lookback=20,adx=20):
        key=(kind,lookback,adx)
        if key in self.flag_cache:return self.flag_cache[key]
        out=[False]*len(self.b)
        for i in range(200,len(self.b)):
            r=self.b[i]
            if kind=='D':out[i]=r['c']>max(x['h'] for x in self.b[i-lookback:i]) and self.f['adx'][i]>=adx and self.f['atr'][i]>statistics.fmean(self.f['atr'][i-20:i])
            elif kind=='C_simple':
                level=min(x['l'] for x in self.b[i-lookback:i]);out[i]=r['l']<level and r['c']>level
            else:raise ValueError(kind)
        self.flag_cache[key]=out;return out
    def simulate(self,p,start,end,scale=1.,fee_bps=5,slip_bps=2,retain=False,frozen=None):
        if end>HOLDOUT:
            if frozen is None:raise ValueError('v2 holdout locked until identity registry is frozen')
            permitted=[frozen['winner'],*frozen['controls']]
            if not any(x['config']==p and math.isclose(x['scale'],scale,rel_tol=1e-12) for x in permitted):raise ValueError('model or risk scale differs from frozen holdout registry')
        if p['kind']=='daily':return daily_run(self.data,'um',p['daily_rule'],start,end,fee_bps,slip_bps,retain=retain,exposure_scale=scale)
        b=self.b;f=self.f;flags=self.flags(p['kind'],p.get('lookback',20),p.get('adx',20));fee=fee_bps/10000;slip=slip_bps/10000;cash=10000.;qty=0.;active=None;stop=None;high=None;stage=0;trades=[];fills=[];funding=[];trail_events=[];marks=[];daily=[];fees=slippage=fundtotal=0.;rejected=0
        lo=bisect.bisect_left(self.bt,start);hi=bisect.bisect_left(self.bt,end);assert hi-lo==(end-start)//H4
        def execute(t,price,dq,reason):
            nonlocal cash,qty,fees,slippage
            fill=price*(1+slip if dq>0 else 1-slip);fc=abs(dq)*fill*fee;sc=abs(dq)*price*slip;cash-=dq*fill+fc;qty+=dq;fees+=fc;slippage+=sc
            if abs(qty)<1e-12:qty=0.
            if retain:fills.append({'interval_start_ms':t,'time_utc':iso(t),'side':'BUY' if dq>0 else 'SELL','qty':abs(dq),'reference_price':price,'fill_price':fill,'fee':fc,'slippage_cost':sc,'reason':reason})
            return fill
        def sell(t,price,amount,reason,terminal=False):
            nonlocal active,stop,high
            amount=min(amount,qty);fill=execute(t,price,-amount,reason);active['exit_value']+=amount*fill
            if qty==0:
                active.update(exit_ms=t,exit_utc=iso(t),weighted_exit_price=active['exit_value']/active['qty'],exit_reason=reason,net_pnl=cash-active['equity_before'],terminal=terminal);active['net_r']=active['net_pnl']/active['planned_initial_loss'];trades.append(active);active=None;stop=None;high=None
        for i in range(lo,hi):
            r=b[i];t=r['t'];m=self.m[t];path=[self.h[t+k*3600000] for k in range(4) if self.h[t+k*3600000]['v']>0]
            if not path:raise ValueError('entire execution interval has zero-volume hours')
            trade_t=path[0]['t'];low_proxy=cash+qty*m['l']
            if t in self.fr:
                ft,rate=self.fr[t];amount=qty*m['o']*rate;cash-=amount;fundtotal+=amount
                if retain:funding.append({'actual_time_ms':ft,'nominal_time_ms':t,'qty':qty,'mark_open_proxy':m['o'],'rate':rate,'payment':amount})
            s=self.signal[self.st[bisect.bisect_right(self.st,t)-1]];was_open=qty>0
            if qty and not s['regime']:sell(trade_t,r['o'],qty,'REGIME_EXIT')
            elif qty and r['o']<=stop:sell(trade_t,r['o'],qty,'GAP_STOP')
            if not was_open and i>0 and flags[i-1] and s['regime']:
                eq=cash;entry=r['o']*(1+slip)
                if p['mode']=='structure':sl=min(x['l'] for x in b[i-p.get('structure_window',5):i])-.25*f['atr'][i-1]
                else:sl=r['o']-p.get('initial_atr',2)*f['atr'][i-1]
                stopfill=sl*(1-slip);loss=entry-stopfill+fee*(entry+stopfill)
                if sl<=0 or sl>=entry or loss<=0:rejected+=1
                else:
                    amount=min(eq*.005*scale/loss,eq/(entry*(1+fee)))
                    if amount>0:
                        pr=entry-sl;active={'model_id':p['id'],'signal_available_ms':b[i-1]['t']+H4,'entry_ms':trade_t,'entry_utc':iso(trade_t),'daily_source_open_ms':s['source_open_ms'],'entry_price':entry,'initial_sl':sl,'tp1':entry+pr if p['mode']=='split' else None,'tp2':entry+2*pr if p['mode']=='split' else entry+float(p['mode'][-1])*pr if p['mode'] in ('fixed2','fixed3') else None,'qty':amount,'equity_before':eq,'planned_initial_loss':amount*loss,'planned_risk_fraction':amount*loss/eq,'exit_value':0.}
                        assert active['signal_available_ms']<=trade_t and s['source_open_ms']+DAY<=trade_t and active['planned_risk_fraction']<=.005*scale+1e-12
                        execute(trade_t,r['o'],amount,'ENTRY');stop=sl;high=r['o'];stage=0
            if qty:
                for h in path:
                    if not qty:break
                    if h['o']<=stop:sell(h['t'],h['o'],qty,'GAP_STOP_1H');continue
                    if h['l']<=stop:sell(h['t'],stop,qty,'STOP_1H');continue
                    if p['mode'] in ('fixed2','fixed3') and h['h']>=active['tp2']:sell(h['t'],active['tp2'],qty,'FIXED_TP');continue
                    newstop=stop
                    if p['mode']=='split':
                        if stage==0 and h['h']>=active['tp1']:
                            sell(h['t'],active['tp1'],.2*active['qty'],'TP1_20PCT');stage=1;newstop=max(newstop,active['entry_price'])
                        if stage==1 and h['h']>=active['tp2']:
                            sell(h['t'],active['tp2'],.2*active['qty'],'TP2_20PCT');stage=2;newstop=max(newstop,active['tp1'])
                    if qty and newstop>stop:
                        stop=newstop
                        if retain:trail_events.append({'available_ms':h['t']+3600000,'new_sl':stop,'reason':'PARTIAL_TARGET_CLOSE'})
                if qty:
                    high=max(high,r['h'])
                    if p['mode'] in ('trail','structure') or (p['mode']=='split' and stage==2):
                        newstop=max(stop,high-p.get('trail_atr',3)*f['atr'][i])
                        if newstop>stop:
                            stop=newstop
                            if retain:trail_events.append({'available_ms':t+H4,'new_sl':stop,'reason':'CLOSED_4H_ATR_TRAIL'})
            eq=cash+qty*m['c'];marks.append({'t':t+H4-1,'equity':eq,'intrabar_low_equity':min(eq,low_proxy if was_open else eq),'qty':qty})
            if (t+H4)%DAY==0:daily.append({'t':t+H4-1,'equity':eq,'weight':None})
        if qty:
            sell(end-1,b[hi-1]['c'],qty,'TERMINAL_EXIT',True);daily[-1]['equity']=cash;marks.append({'t':end-1,'equity':cash,'intrabar_low_equity':cash,'qty':0.})
        met=summary(daily,marks,trades,10000,start,end);rr=[x['net_r'] for x in trades]
        met.update(model_id=p['id'],config=p,scale=scale,risk_fraction=.005*scale,expectancy_net_r=statistics.fmean(rr) if rr else None,total_net_r=sum(rr),profit_factor_r=sum(x for x in rr if x>0)/-sum(x for x in rr if x<0) if any(x<0 for x in rr) else None,fees_paid=fees,slippage_cost=slippage,net_funding_paid=fundtotal,invalid_stop_rejections=rejected,fee_bps=fee_bps,slip_bps=slip_bps,candidate_holdout_evaluated=end>HOLDOUT)
        return {'metrics':met,'trades':trades,'fills':fills,'funding':funding,'trail_events':trail_events,'daily_equity':daily,'mark_equity':marks}
def configs():
    out=[]
    for kind in ['D','C_simple']:
        for mode in ['trail','fixed2','fixed3','structure','split','regime']:
            out.append({'id':kind+'_'+mode,'kind':kind,'mode':mode,'lookback':20,'adx':20,'initial_atr':2,'trail_atr':3,'structure_window':5})
    out.extend({'id':'daily_'+x,'kind':'daily','daily_rule':x} for x in ['trend','vol_trend']);return out
def neighbors(p):
    if p['kind']=='daily':return []
    out=[]
    changes=[('lookback',16),('lookback',24)]
    if p['mode']=='structure':changes +=[('structure_window',3),('structure_window',7)]
    else:changes +=[('initial_atr',1.75),('initial_atr',2.25)]
    if p['mode'] in ['trail','structure','split']:changes +=[('trail_atr',2.5),('trail_atr',3.5)]
    if p['kind']=='D':changes +=[('adx',18),('adx',22)]
    for key,value in changes:
        z=dict(p);z[key]=value;z['id']=p['id']+'__'+key+'_'+str(value);out.append(z)
    return out
