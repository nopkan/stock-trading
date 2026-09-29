import numpy as np
import pandas as pd
from research.portfolio import Panel, FeeSchedule
from research.small_capital import LotData, Features, SmallSpec, LotExecution, pick_targets, simulate_lots


def make_panel(close, splits=None):
    c=np.asarray(close,dtype=float)
    f=pd.DataFrame({'open':c,'close':c,'adj_open':c,'adj_close':c,'adj_high':c,'adj_low':c,
        'volume':1e8,'stock_splits':np.zeros(len(c)) if splits is None else splits,'dividends':np.zeros(len(c))},
        index=pd.bdate_range('2020-01-01',periods=len(c)))
    return Panel({'A':f})


def test_reverse_split_adjustment_uses_only_subsequent_actions():
    p=make_panel([10,11,12,13],[0,0,10,0]);d=LotData(p)
    np.testing.assert_allclose(d.close[:,0],[100,110,12,13])
    np.testing.assert_allclose(d.actions[:,0],[1,1,10,1])


def test_affordability_filter_does_not_buy_expensive_top_ranked_name():
    spec=SmallSpec(top_n=5)
    selected,desired=pick_targets(np.array([1.,.9,.8]),np.ones(3,bool),[],np.array([100.,20.,30.]),30000,spec,100,.002)
    assert list(selected)==[1,2]
    assert desired[0]==0 and (desired%100==0).all()
    assert (desired*np.array([100,20,30])).sum()<=30000*.9


def test_reference_does_not_silently_replace_unaffordable_stocks():
    spec=SmallSpec(top_n=1,affordability_filter=False)
    selected,desired=pick_targets(np.array([1.,.9]),np.ones(2,bool),[],np.array([1000.,20.]),30000,spec,100,.002)
    assert list(selected)==[0] and desired.sum()==0


def test_lot_orders_whole_cash_never_borrowed_and_minimum_once_daily():
    p=make_panel([20]*8);d=LotData(p);f=Features(p)
    f.rank[:]=1;f.eligible[:]=True;f.bull=np.ones(len(p.dates),bool)
    spec=SmallSpec(top_n=5,rebalance=2)
    fees=FeeSchedule(minimum_daily_commission_thb=50)
    r,c,fills,daily=simulate_lots(d,f,spec,p.dates[1],p.dates[-1],fees,30000,details=True)
    assert (fills.shares%100==0).all()
    assert daily.cash_thb.min()>=0
    assert np.isclose(daily.fees_thb[daily.traded_thb>0].iloc[0],53.5 + fills.iloc[0].notional_thb*.00007*1.07)


def test_actions_preserve_value_and_odd_lots_are_not_invented_auction_sales():
    p=make_panel([20]*8,[0,0,1.1,0,0,0,0,0]);d=LotData(p);f=Features(p)
    f.rank[:]=1;f.eligible[:]=True;f.bull=np.ones(len(p.dates),bool);f.bull[3:]=False
    spec=SmallSpec(top_n=5,rebalance=2)
    _,_,fills,daily=simulate_lots(d,f,spec,p.dates[1],p.dates[-1],capital=30000,details=True)
    assert (fills.shares%100==0).all()
    assert daily.odd_lot_value_thb.iloc[-1]>0
    assert daily.auction_salable_positions.iloc[-1]==0


def test_cash_dividends_not_double_counted_in_price_only_model():
    p=make_panel([20]*8);p.frames['A']['dividends']=1.
    d=LotData(p);f=Features(p);f.rank[:]=1;f.eligible[:]=True;f.bull=np.ones(len(p.dates),bool)
    fees=FeeSchedule(commission_bps=0,exchange_bps=0,clearing_bps=0,regulatory_bps=0,vat=0,slippage_bps=0)
    r,c,_,_=simulate_lots(d,f,SmallSpec(top_n=5),p.dates[1],p.dates[-1],fees,30000)
    assert r['total_return']==0
    assert r['excluded_gross_dividend_entitlements_thb']>0


def test_features_and_accounting_are_prefix_invariant():
    rng=np.random.default_rng(12)
    p=make_panel(10*np.exp(np.cumsum(rng.normal(.001,.012,550))))
    d=LotData(p);f=Features(p)
    prefix=Panel({s:v.iloc[:450] for s,v in p.frames.items()});short=Features(prefix)
    np.testing.assert_allclose(f.rank.iloc[:450],short.rank,equal_nan=True)
    np.testing.assert_array_equal(f.bull[:450],short.bull)
    spec=SmallSpec(top_n=5)
    a=simulate_lots(d,f,spec,p.dates[260],p.dates[-1])[1]
    b=simulate_lots(LotData(prefix),short,spec,p.dates[260],p.dates[449])[1]
    np.testing.assert_allclose(a.loc[b.index],b)


def test_locked_module_matches_selected_spec():
    from strategy.set100_small_capital import SPEC,CANDIDATE_ID,LIVE_READY
    assert SPEC.identity==CANDIDATE_ID=='b142b3be5b992c7b'
    assert SPEC.top_n==15 and SPEC.reserve==.10 and SPEC.affordability_filter
    assert not LIVE_READY
