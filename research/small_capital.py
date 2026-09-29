"""THB30k lot-constrained price-only research. Not certified auction execution.

Provider split-reversal and stock entitlements are assumptions, not a repaired
exchange tape. Cash dividends are deliberately excluded (both strategy/basket).
"""
from dataclasses import dataclass, asdict
import hashlib
import json
from fractions import Fraction
import numpy as np
import pandas as pd
from research.portfolio import Panel, FeeSchedule, summarize
from research.candidates import Factory


@dataclass(frozen=True)
class SmallSpec:
    family: str = 'capital_aware_buffered_momentum'
    top_n: int = 8
    reserve: float = .10
    daily_exit: int = 0
    rank_buffer: int = 5
    rebalance: int = 21
    skip: int = 21
    trend: int = 200
    market_window: int = 200
    min_turnover_thb: int = 10_000_000
    affordability_filter: bool = True

    @property
    def identity(self):
        if not self.affordability_filter and self.top_n==15 and self.reserve==.05 and self.daily_exit==0 and self.rank_buffer==5 and self.rebalance==21:
            return 'e9a522bb24938501'  # Same frozen recipe, new execution/capital context.
        return hashlib.sha256(json.dumps(asdict(self),sort_keys=True,separators=(',',':')).encode()).hexdigest()[:16]


class LotData:
    def __init__(self, panel):
        self.panel=panel
        opens={};closes={};actions={};dividends={}
        for s,f in panel.frames.items():
            ratios=f.get('stock_splits',pd.Series(0.,index=f.index)).fillna(0).replace(0,1)
            if (ratios<=0).any() or not np.isfinite(ratios).all():raise ValueError('Invalid corporate-action ratios')
            # A split effective today is already reflected in today's quote.
            future=ratios.iloc[::-1].cumprod().iloc[::-1]/ratios
            opens[s]=f['open']*future
            closes[s]=f['close']*future
            actions[s]=ratios.map(lambda x:float(Fraction(float(x)).limit_denominator(10000)))
            dividends[s]=f.get('dividends',pd.Series(0.,index=f.index)).fillna(0)*future
        self.open=pd.DataFrame(opens,index=panel.dates).to_numpy()
        self.close=pd.DataFrame(closes,index=panel.dates).to_numpy()
        self.marks=pd.DataFrame(self.close,index=panel.dates).ffill().fillna(0).to_numpy()
        self.actions=pd.DataFrame(actions,index=panel.dates).fillna(1).to_numpy()
        self.dividends=pd.DataFrame(dividends,index=panel.dates).fillna(0).to_numpy()


class Features:
    def __init__(self,panel):
        self.panel=panel
        f=Factory(panel)
        self.rank=sum(f.feature('momentum',n,21).rank(axis=1,pct=True) for n in (63,126,252))/3
        self.eligible=(f.available & f.age.ge(253) & f.liquid.ge(10_000_000) &
                       f.feature('momentum',252,21).gt(0) & f.feature('mean',200).gt(0))
        self.eligible.loc[:,list(panel.exclusions)]=False
        self.bull=f.market.gt(f.market.rolling(200).mean()).to_numpy()


@dataclass(frozen=True)
class LotExecution:
    windows: tuple = ('morning','close')
    extra_delay: int = 0
    phase: int = 0
    missed_fills: bool = False
    funding_buffer: float = .35
    prior_turnover_fraction: float = .01
    lot_size: int = 100
    halt_drawdown: float | None = None


def pick_targets(scores,eligible,previous,reference_prices,nav,spec,lot_size,fee_rate):
    """Selection and integral quantities use only pre-auction observations."""
    budget=nav*(1-spec.reserve)/spec.top_n/(1+fee_rate)
    valid=eligible & np.isfinite(scores) & (reference_prices>0)
    if spec.affordability_filter:valid &= reference_prices*lot_size<=budget
    order=np.argsort(-np.where(valid,scores,-np.inf),kind='stable')
    order=order[valid[order]]
    kept=[j for j in order[:spec.top_n+spec.rank_buffer] if j in previous][:spec.top_n]
    selected=np.array((kept+[j for j in order if j not in kept])[:spec.top_n],dtype=int)
    desired=np.zeros(len(scores),dtype=float)
    if len(selected):desired[selected]=np.floor(budget/reference_prices[selected]/lot_size)*lot_size
    return selected,desired


def simulate_lots(data,features,spec,start,end,costs=FeeSchedule(),capital=30000.,execution=LotExecution(),details=False):
    if spec.top_n<1 or not 0<=spec.reserve<1 or spec.daily_exit<0:raise ValueError('Invalid recipe')
    # The bounded study intentionally supports only these shared signal definitions.
    if (spec.skip,spec.trend,spec.market_window,spec.min_turnover_thb)!=(21,200,200,10_000_000):raise ValueError('Unsupported feature definition')
    if not np.isfinite(capital) or capital<=0 or not isinstance(execution.lot_size,int) or execution.lot_size<=0:raise ValueError('Invalid capital/lot')
    if not np.isfinite(execution.funding_buffer) or execution.funding_buffer<0:raise ValueError('Invalid funding buffer')
    if not 0<execution.prior_turnover_fraction<=1:raise ValueError('Invalid capacity')
    if not 0<=execution.phase<spec.rebalance:raise ValueError('Invalid rebalance phase')
    if set(execution.windows)-{'morning','close'} or not execution.windows:raise ValueError('Afternoon auction observations unavailable')
    if len(set(execution.windows))!=len(execution.windows):raise ValueError('Duplicate windows')
    if not isinstance(execution.extra_delay,int) or execution.extra_delay<0:raise ValueError('Invalid delay')
    if execution.halt_drawdown is not None and not 0<execution.halt_drawdown<1:raise ValueError('Invalid halt')
    panel=data.panel;n=len(panel.symbols)
    idx=np.flatnonzero((panel.dates>=pd.Timestamp(start))&(panel.dates<=pd.Timestamp(end)))
    if len(idx)<2:raise ValueError('Insufficient dates')
    selected=np.array([],dtype=int);shares=np.zeros(n);cash=capital;peak=capital;halted=False
    minfee=costs.minimum_daily_commission_thb*(1+costs.vat);rate=costs.rate;slip=costs.slippage_bps/10000;lot=execution.lot_size
    ranks=features.rank.to_numpy();eligible=features.eligible.to_numpy();bear=~features.bull
    risk_exit=pd.Series(bear).rolling(spec.daily_exit).sum().eq(spec.daily_exit).to_numpy() if spec.daily_exit else np.zeros(len(bear),bool)
    equity=[];exposure=[];records=[];daily=[];count=0;turnover=0.;fees=0.;maxweight=0.;excluded_dividends=0.
    for i in idx:
        # Corporate-action-created fractional and odd-lot balances are not auction orders.
        shares*=data.actions[i]
        prior=data.marks[i-1]/data.actions[i] if i else np.zeros(n)
        nav=cash+shares@prior
        # Entitlements on ex-date belong to pre-auction holdings. Intentionally
        # not credited to cash/NAV, making all results price-only.
        excluded_dividends+=float(shares@data.dividends[i])
        if execution.halt_drawdown is not None and nav/peak-1<=-execution.halt_drawdown:halted=True
        j=i-1-execution.extra_delay
        event=j>=0 and (j%spec.rebalance==execution.phase or risk_exit[j])
        notional=0.;dayfees=0.
        if event or halted:
            if halted or not features.bull[j] or risk_exit[j]:
                desired=np.zeros(n);selected=np.array([],dtype=int)
            else:
                selected,desired=pick_targets(ranks[j],eligible[j],selected,prior,max(0.,nav-minfee),spec,lot,rate+slip)
            bounds=prior*(1+execution.funding_buffer)*(1+slip)
            prior_value=panel.value.iloc[i-1].fillna(0).to_numpy() if i else np.zeros(n)
            maxlots=np.floor(np.divide(prior_value*execution.prior_turnover_fraction,bounds,
                out=np.zeros(n),where=bounds>0)/lot)*lot
            for window in ('morning','close'):
                if window not in execution.windows:continue
                px=data.open[i] if window=='morning' else data.close[i]
                tradable=panel.tradable[i]&np.isfinite(px)&(px>0)&(prior>0)
                delta=desired-shares
                sell=np.where(tradable,np.floor(np.maximum(-delta,0)/lot)*lot,0.)
                buy=np.where(tradable,np.floor(np.maximum(delta,0)/lot)*lot,0.)
                sell=np.minimum(sell,maxlots);buy=np.minimum(buy,maxlots)
                # ATO buys reserve existing cash against an upper-price envelope.
                # Confirmed proceeds from this window cannot fund another order here.
                budget=max(0.,cash-minfee)
                priority=sorted(np.flatnonzero(buy>0),key=lambda k:(-ranks[j,k],panel.symbols[k]))
                for k in priority:
                    affordable=np.floor(budget/(bounds[k]*(1+rate))/lot)*lot
                    buy[k]=max(0.,min(buy[k],affordable));budget-=buy[k]*bounds[k]*(1+rate)
                buy=np.where(px*(1+slip)<=bounds,buy,0.)
                if execution.missed_fills:
                    for k in np.flatnonzero(sell+buy):
                        key=f'{panel.dates[i].date()}:{window}:{panel.symbols[k]}'
                        if int(hashlib.sha256(key.encode()).hexdigest()[:8],16)%3==0:buy[k]=sell[k]=0
                        else:
                            if buy[k]>=2*lot:buy[k]=np.floor(buy[k]/2/lot)*lot
                            if sell[k]>=2*lot:sell[k]=np.floor(sell[k]/2/lot)*lot
                actual=np.nan_to_num(px);bv=buy*actual*(1+slip);sv=sell*actual*(1-slip)
                cash+=sv.sum()*(1-rate)-bv.sum()*(1+rate);shares+=buy-sell
                amount=float(bv.sum()+sv.sum());paid=amount*rate;notional+=amount;dayfees+=paid
                active=(buy+sell)>0;count+=int(active.sum())
                if details:
                    for k in np.flatnonzero(active):
                        b=buy[k]>0
                        records.append({'date':str(panel.dates[i].date()),'window':window,'symbol':panel.symbols[k],
                            'side':'buy' if b else 'sell','shares':int(buy[k] if b else sell[k]),
                            'price_proxy':float(actual[k]*(1+slip if b else 1-slip)),
                            'notional_thb':float(bv[k] if b else sv[k]),'variable_fee_thb':float((bv[k] if b else sv[k])*rate)})
            topup=costs.daily_minimum_topup(notional,1.);cash-=topup;dayfees+=topup
        fees+=dayfees;turnover+=notional
        values=shares*data.marks[i];nav=cash+values.sum();peak=max(peak,nav)
        if cash<-.00001 or shares.min()<-.00001 or not np.isfinite(nav) or nav<=0:raise ArithmeticError('Invalid account state')
        eq=nav/capital;exp=values.sum()/nav;mw=values.max()/nav;maxweight=max(maxweight,mw)
        equity.append(eq);exposure.append(exp)
        daily.append({'date':panel.dates[i],'equity_thb':nav,'cash_thb':cash,'invested':exp,'positions':int((values>.01).sum()),
            'auction_salable_positions':int((shares>=lot).sum()),'fees_thb':dayfees,'traded_thb':notional,
            'odd_lot_value_thb':float((np.mod(shares,lot)*data.marks[i]).sum()),'max_stock_weight':mw})
    result,curve=summarize(panel.dates[idx],np.array(equity),count,turnover/capital,fees/capital,exposure,maxweight)
    result.update(halted=halted,mean_positions=float(np.mean([d['positions'] for d in daily])),
        excluded_gross_dividend_entitlements_thb=excluded_dividends,ending_odd_lot_value_thb=daily[-1]['odd_lot_value_thb'],
        ending_cash_thb=cash)
    return result,curve,pd.DataFrame(records),pd.DataFrame(daily).set_index('date')


def price_only_basket(data,start,end,costs=FeeSchedule(),capital=30000.):
    """Fractional equal initial sleeves; idealized price-only comparison, not live."""
    p=data.panel;n=len(p.symbols);cash=np.full(n,capital/n);shares=np.zeros(n);bought=np.zeros(n,bool)
    out=[];count=0;turn=0.;fees=0.;exp=[];maxweight=0.
    idx=np.flatnonzero((p.dates>=pd.Timestamp(start))&(p.dates<=pd.Timestamp(end)))
    slip=costs.slippage_bps/10000
    for i in idx:
        shares*=data.actions[i]
        prior=data.marks[i-1] if i else np.zeros(n)
        enter=p.tradable[i]&~bought&(prior>0)
        if enter.any():
            minimum=costs.minimum_daily_commission_thb*(1+costs.vat)
            budget=np.maximum(0.,cash[enter]-minimum/enter.sum())
            notional=budget/(1+costs.rate)
            shares[enter]=notional/(data.open[i,enter]*(1+slip))
            extra=costs.daily_minimum_topup(float(notional.sum()),1.)
            cash[enter]-=budget+extra/enter.sum();bought[enter]=True
            turn+=notional.sum();fees+=notional.sum()*costs.rate+extra;count+=int(enter.sum())
        values=shares*data.marks[i];nav=cash.sum()+values.sum()
        out.append(nav/capital);exp.append(values.sum()/nav);maxweight=max(maxweight,values.max()/nav)
    return summarize(p.dates[idx],np.array(out),count,turn/capital,fees/capital,exp,maxweight)
