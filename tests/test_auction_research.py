from dataclasses import replace
import numpy as np
import pandas as pd
import pytest
from research.auction_research import AuctionRecipe, ProxyExecution, simulate_proxy, targets
from research.portfolio import Panel, FeeSchedule


def simple_panel(a, b=None, opens=None):
    frames={}
    for name,values in [('A',a),('B',b)]:
        if values is None:continue
        c=np.asarray(values,dtype=float)
        frames[name]=pd.DataFrame({'adj_open':c if opens is None else opens,'adj_close':c,
            'adj_high':c,'adj_low':c,'close':c,'volume':1e8},index=pd.bdate_range('2020-01-01',periods=len(c)))
    return Panel(frames)


FREE=FeeSchedule(commission_bps=0,exchange_bps=0,clearing_bps=0,regulatory_bps=0,vat=0,slippage_bps=0)


def test_reference_identity_is_not_a_new_recipe_because_of_float_serialization():
    assert AuctionRecipe(reserve=.05,market_exit_closes=0).identity=='e9a522bb24938501'
    assert AuctionRecipe(reserve=.05,market_exit_closes=0,min_turnover_thb=10000000).identity=='e9a522bb24938501'


def test_cannot_spend_same_auction_sale_proceeds():
    p=simple_panel([10]*6,[10]*6)
    t=np.full((6,2),np.nan);t[0]=[1,0];t[2]=[0,1]
    _,_,fills=simulate_proxy(p,t,p.dates[1],p.dates[-1],FREE,1000,ProxyExecution(windows=('morning',),funding_price_buffer=0),True)
    switched=fills[fills.date.eq(str(p.dates[3].date()))]
    assert set(switched.side)=={'sell'}
    _,_,fills=simulate_proxy(p,t,p.dates[1],p.dates[-1],FREE,1000,ProxyExecution(funding_price_buffer=0),True)
    switched=fills[fills.date.eq(str(p.dates[3].date()))]
    assert set(switched[switched.window.eq('morning')].side)=={'sell'}
    assert set(switched[switched.window.eq('close')].side)=={'buy'}


def test_quantity_determined_before_unknown_auction_price():
    t=np.full((4,1),np.nan);t[0]=.5
    p=simple_panel([10]*4)
    q=simple_panel([10]*4,opens=[10,12,10,10])
    x=ProxyExecution(windows=('morning',),funding_price_buffer=.35)
    f=simulate_proxy(p,t,p.dates[1],p.dates[-1],FREE,1000,x,True)[2]
    g=simulate_proxy(q,t,q.dates[1],q.dates[-1],FREE,1000,x,True)[2]
    assert f.adjusted_units.iloc[0]==g.adjusted_units.iloc[0]==50
    assert f.adjusted_price.iloc[0]!=g.adjusted_price.iloc[0]


def test_partial_residual_retries_but_daily_commission_minimum_charged_once():
    p=simple_panel([10]*4);t=np.full((4,1),np.nan);t[0]=.5
    fee=replace(FREE,minimum_daily_commission_thb=20)
    result,curve,fills=simulate_proxy(p,t,p.dates[1],p.dates[-1],fee,1000,ProxyExecution(fill_fraction=.5),True)
    assert len(fills)==2
    assert np.isclose(result['fees_fraction_initial_capital'],.02)
    assert np.isclose(curve.iloc[-1],.98)
    assert fills.adjusted_units.sum()<49


def test_halt_latches_and_exit_occurs_only_after_observed_loss():
    p=simple_panel([10,10,7,6,6,6]);t=np.full((6,1),np.nan);t[0]=1;t[3]=1
    r,_,fills=simulate_proxy(p,t,p.dates[1],p.dates[-1],FREE,1000,
        ProxyExecution(funding_price_buffer=0,portfolio_halt=.2),True)
    assert r['halted']
    assert fills[fills.side.eq('sell')].date.iloc[0]==str(p.dates[3].date())
    assert not ((fills.side=='buy')&(fills.date>=str(p.dates[3].date()))).any()
    assert r['max_drawdown']<-.2  # A threshold cannot prevent the opening gap.


@pytest.mark.parametrize('bad',[ProxyExecution(windows=('afternoon',)),ProxyExecution(fill_fraction=0),ProxyExecution(prior_turnover_fraction=-1)])
def test_rejects_unsupported_or_invalid_execution(bad):
    p=simple_panel([10]*4);t=np.full((4,1),np.nan)
    with pytest.raises(ValueError):simulate_proxy(p,t,p.dates[1],p.dates[-1],execution=bad)


@pytest.mark.parametrize('recipe',[AuctionRecipe(),AuctionRecipe(market_source='SET100_price'),AuctionRecipe(market_source='SET100_price',stock_exit_closes=3)])
def test_candidate_targets_are_prefix_invariant(recipe):
    rng=np.random.default_rng(812)
    p=simple_panel(10*np.exp(np.cumsum(rng.normal(.001,.01,500))),10*np.exp(np.cumsum(rng.normal(.001,.012,500))));index=p.close.mean(axis=1)
    full=targets(p,recipe,index)
    prefix=Panel({s:f.iloc[:420] for s,f in p.frames.items()})
    np.testing.assert_allclose(full[:420],targets(prefix,recipe,index.iloc[:420]),equal_nan=True)
