"""Causal auction-oriented daily-price PROXY research; not an auction backtest.

No afternoon price or auction liquidity is manufactured. Adjusted units remain
fractional research units. True share lots, auction queues and corporate-action
cash ledgers must be validated with a broker/exchange feed before live use.
"""
from dataclasses import dataclass, asdict
import hashlib
import json
import numpy as np
import pandas as pd
from research.portfolio import Panel, FeeSchedule, summarize
from research.refinements import Refinement, RefinementFactory


@dataclass(frozen=True)
class AuctionRecipe:
    top_n: int = 15
    rank_buffer: int = 5
    reserve: float = .10
    market_exit_closes: int = 3
    market_source: str = 'equal_weight'
    stock_exit_closes: int = 0
    rebalance: int = 21
    market_window: int = 200
    stock_window: int = 200
    skip: int = 21
    min_turnover_thb: float = 10_000_000.

    @property
    def identity(self):
        # Preserve existing canonical IDs where the recipe is exactly equivalent.
        if self.market_source=='equal_weight' and not self.stock_exit_closes:
            return self.refinement.identity
        return hashlib.sha256(json.dumps(asdict(self),sort_keys=True,separators=(',',':')).encode()).hexdigest()[:16]

    @property
    def refinement(self):
        turnover=(int(self.min_turnover_thb) if float(self.min_turnover_thb).is_integer()
                  else self.min_turnover_thb)
        return Refinement(top_n=self.top_n,rank_buffer=self.rank_buffer,reserve=self.reserve,
            daily_exit=self.market_exit_closes,rebalance=self.rebalance,market_window=self.market_window,
            trend=self.stock_window,skip=self.skip,min_turnover_thb=turnover)


def targets(panel, recipe, index_close, phase=0):
    factory=RefinementFactory(panel)
    if recipe.market_source=='SET100_price':
        market=index_close.reindex(panel.dates)
        if market.isna().any():raise ValueError('Missing observed SET100 index session')
        factory.market=market
    elif recipe.market_source!='equal_weight':raise ValueError('Unknown market source')
    output=factory.targets(recipe.refinement,phase)
    if recipe.stock_exit_closes:
        below=(factory.c < factory.c.rolling(recipe.stock_window).mean()) & factory.available
        exits=below.rolling(recipe.stock_exit_closes).sum().eq(recipe.stock_exit_closes).to_numpy()
        desired=np.zeros(len(panel.symbols))
        for i,row in enumerate(output):
            scheduled=np.isfinite(row).all()
            if scheduled:desired=row.copy()
            killed=(desired>0)&exits[i]
            if killed.any():
                desired[killed]=0
                output[i]=desired
    return output


@dataclass(frozen=True)
class ProxyExecution:
    windows: tuple = ('morning','close')
    fill_fraction: float = 1.
    extra_delay: int = 0
    funding_price_buffer: float = .35
    prior_turnover_fraction: float = .01
    portfolio_halt: float | None = None


def simulate_proxy(panel, desired_targets, start, end, costs=FeeSchedule(),
                   capital=1_000_000., execution=ProxyExecution(), details=False):
    """Prior-close sizing; independently funded simultaneous auction orders.

    Daily open/close are proxies, NOT guaranteed auction prices. A morning sale
    may fund the close only after confirmation; never another order in the same
    auction. Residuals retry at the next requested window that day then expire.
    A portfolio halt uses a completed close and latches, retrying liquidation at
    subsequent modeled windows. Threshold is not a guaranteed maximum loss.
    """
    if not np.isfinite(capital) or capital<=0:raise ValueError('Invalid capital')
    if not 0<execution.fill_fraction<=1 or not isinstance(execution.extra_delay,int) or execution.extra_delay<0:raise ValueError('Invalid execution settings')
    if not np.isfinite(execution.funding_price_buffer) or execution.funding_price_buffer<0:raise ValueError('Invalid funding buffer')
    if not np.isfinite(execution.prior_turnover_fraction) or not 0<execution.prior_turnover_fraction<=1:raise ValueError('Invalid capacity fraction')
    if not execution.windows or set(execution.windows)-{'morning','close'}:raise ValueError('Afternoon auction requires actual intraday data')
    if len(execution.windows)!=len(set(execution.windows)):raise ValueError('Duplicate windows')
    if execution.portfolio_halt is not None and not 0<execution.portfolio_halt<1:raise ValueError('Invalid halt')
    t=np.asarray(desired_targets,dtype=float)
    if t.shape!=panel.marks.shape:raise ValueError('Targets shape mismatch')
    active=~np.isnan(t).all(axis=1)
    if not np.isfinite(t[active]).all() or (t[active]<0).any() or (t[active].sum(axis=1)>1+1e-10).any():raise ValueError('Invalid target weights')
    units=np.zeros(len(panel.symbols));cash=capital;peak=capital;halted=False
    equity=[];exposure=[];records=[];count=0;fees=0.;turnover=0.;max_weight=0.
    idx=np.flatnonzero((panel.dates>=pd.Timestamp(start))&(panel.dates<=pd.Timestamp(end)))
    if len(idx)<2:raise ValueError('Insufficient evaluation history')
    slip=costs.slippage_bps/10000
    rate=costs.rate
    minimum=costs.minimum_daily_commission_thb*(1+costs.vat)
    for i in idx:
        signal_i=i-1-execution.extra_delay
        prior=panel.marks[i-1] if i else np.zeros_like(units)
        nav=cash+units@prior
        if execution.portfolio_halt is not None and nav/peak-1<=-execution.portfolio_halt:
            halted=True
        scheduled=signal_i>=0 and active[signal_i]
        day_notional=0.
        if scheduled or halted:
            weights=np.zeros_like(units) if halted else t[signal_i]
            # Quantities known before first auction; never resize from its result.
            locked=np.divide(weights*max(0.,nav-minimum)/(1+rate+slip),prior,
                             out=units.copy(),where=prior>0)
            known_bounds=prior*(1+execution.funding_price_buffer)*(1+slip)
            previous_turnover=panel.value.iloc[i-1].fillna(0).to_numpy() if i else np.zeros_like(units)
            for window in ('morning','close'):
                if window not in execution.windows:continue
                prices=panel.opens[i] if window=='morning' else panel.close.iloc[i].to_numpy()
                tradable=panel.tradable[i]&np.isfinite(prices)&(prices>0)&(prior>0)
                delta=np.where(tradable,locked-units,0.)
                # Both sides allocated before execution, using pre-auction cash.
                sell=np.maximum(-delta,0.)
                buy=np.maximum(delta,0.)
                capacity=np.divide(previous_turnover*execution.prior_turnover_fraction,known_bounds,
                                   out=np.zeros_like(units),where=known_bounds>0)
                sell=np.minimum(sell,capacity);buy=np.minimum(buy,capacity)
                budget=max(0.,cash-minimum)
                requested=float((buy*known_bounds).sum()*(1+rate))
                buy*=min(1.,budget/requested) if requested else 0.
                # If an observed price exceeds our prior funding envelope, this
                # simplified proxy cannot model that auction; record no buy fill.
                buy=np.where(prices*(1+slip)<=known_bounds,buy,0.)
                buy*=execution.fill_fraction;sell*=execution.fill_fraction
                actual=np.nan_to_num(prices)
                bv=buy*actual*(1+slip);sv=sell*actual*(1-slip)
                cash+=sv.sum()*(1-rate)-bv.sum()*(1+rate)
                units+=buy-sell
                notional=float(bv.sum()+sv.sum());paid=notional*rate
                day_notional+=notional;fees+=paid;turnover+=notional
                active_fills=(buy+sell)>1e-7;count+=int(active_fills.sum())
                if details:
                    for j in np.flatnonzero(active_fills):
                        isbuy=buy[j]>0
                        records.append({'date':str(panel.dates[i].date()),'window':window,'symbol':panel.symbols[j],
                            'side':'buy' if isbuy else 'sell','adjusted_units':float(buy[j] if isbuy else sell[j]),
                            'adjusted_price':float(actual[j]*(1+slip if isbuy else 1-slip)),
                            'notional_thb':float(bv[j] if isbuy else sv[j]),
                            'variable_fee_thb':float((bv[j] if isbuy else sv[j])*rate)})
            topup=costs.daily_minimum_topup(day_notional,1.)
            cash-=topup;fees+=topup
        if cash < -1e-6 or units.min() < -1e-6:raise ArithmeticError('Borrowing/shorting')
        values=units*panel.marks[i];nav=cash+values.sum();peak=max(peak,nav)
        if not np.isfinite(nav) or nav<=0:raise ArithmeticError('Invalid NAV')
        equity.append(nav/capital);exposure.append(values.sum()/nav);max_weight=max(max_weight,values.max()/nav)
    result,curve=summarize(panel.dates[idx],np.array(equity),count,turnover/capital,fees/capital,exposure,max_weight)
    result['halted']=halted
    return result,curve,pd.DataFrame(records)
