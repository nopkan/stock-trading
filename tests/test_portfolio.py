from dataclasses import replace
import numpy as np
import pandas as pd
import pytest
from research.portfolio import Panel, FeeSchedule, simulate, benchmark
from research.candidates import Factory, Spec, RULES, initial_grid
from research.registry import Registry
import importlib
import json
from pathlib import Path


def make_panel(values, volume=None):
    f=pd.DataFrame({'adj_open':values,'adj_close':values,'adj_high':values,'adj_low':values,
                    'close':values,'volume':volume if volume is not None else np.full(len(values),1e6)},
                   index=pd.bdate_range('2020-01-01',periods=len(values)))
    return Panel({'A':f})


def test_cost_schedule_and_minimum():
    c=FeeSchedule()
    assert c.rate==pytest.approx(.0016799)
    c=replace(c,minimum_daily_commission_thb=50)
    assert c.daily_minimum_topup(.001,1e6)==pytest.approx((50-1.5)*1.07/1e6)
    assert c.daily_minimum_topup(0,1e6)==0


def test_portfolio_next_open_fee_and_no_borrowing():
    p=make_panel([100.,120.,150.,150.])
    targets=np.array([[1.],[np.nan],[0.],[np.nan]])
    c=FeeSchedule(commission_bps=0,exchange_bps=0,clearing_bps=0,regulatory_bps=0,slippage_bps=0)
    r,e,t=simulate(p,targets,'2020','2021',c,details=True)
    assert e.tolist()==pytest.approx([1,1,1.25,1.25])
    assert t.date.tolist()==['2020-01-02','2020-01-06']
    costly,_,_=simulate(p,targets,'2020','2021',FeeSchedule(minimum_daily_commission_thb=50))
    assert costly['total_return']<r['total_return']


def test_untradable_no_fill_and_overnight_gap_is_paid():
    p=make_panel([100.,100.,200.,300.],[100,0,100,100])
    targets=np.array([[1.],[1.],[np.nan],[np.nan]])
    c=FeeSchedule(0,0,0,0,0,0,0)
    _,e,t=simulate(p,targets,'2020','2021',c,details=True)
    assert e.tolist()==pytest.approx([1,1,1,1.5])
    assert len(t)==1 and t.iloc[0].adjusted_price==200


def test_benchmark_matches_closed_form():
    p=make_panel([100.,120.,150.])
    c=FeeSchedule()
    r,e=benchmark(p,'2020','2021',c)
    assert e.iloc[-1]==pytest.approx(150/(120*(1+.001)*(1+c.rate)))


@pytest.mark.parametrize('family',list(RULES))
def test_portfolio_recipe_is_causal(family):
    rng=np.random.default_rng(12)
    values=100*np.exp(np.cumsum(rng.normal(.001,.02,420)))
    panel=make_panel(values)
    full=Factory(panel).targets(Spec(family=family,min_turnover_thb=0))
    prefix=Panel({s:f.iloc[:350] for s,f in panel.frames.items()})
    short=Factory(prefix).targets(Spec(family=family,min_turnover_thb=0))
    np.testing.assert_allclose(full[:350],short,equal_nan=True)
    assert np.nanmax(np.nansum(full,axis=1))<=.99+1e-10
    assert np.nanmax(full)<=.099+1e-10


def test_deduplication_persists(tmp_path):
    r=Registry(tmp_path)
    r.put('context','id','stage',{'family':'test'},{'total_return':.1})
    assert Registry(tmp_path).get('context','id','stage')['total_return']==.1
    assert len({s.identity for s in initial_grid()})==len(initial_grid())


def test_invalid_targets():
    p=make_panel([100.,100.])
    with pytest.raises(ValueError):simulate(p,[[2],[2]],'2020','2021')


def test_exclusion_on_dense_panel():
    p=make_panel([100.,100.,100.])
    excluded=Panel(p.frames,{'A'})
    assert not excluded.tradable.any()


@pytest.mark.parametrize('active',json.loads((Path(__file__).resolve().parents[1]/'strategy/active.json').read_text()))
def test_saved_strategy_matches_frozen_recipe_and_prefix(active):
    rng=np.random.default_rng(122)
    p=make_panel(100*np.exp(np.cumsum(rng.normal(.001,.02,420))))
    module=importlib.import_module('strategy.'+active['module'])
    full=module.generate_targets(p)
    expected=Factory(p).targets(Spec(family=active['family'],**active['parameters']))
    np.testing.assert_allclose(full,expected,equal_nan=True)
    prefix=Panel({s:f.iloc[:350] for s,f in p.frames.items()})
    np.testing.assert_allclose(full[:350],module.generate_targets(prefix),equal_nan=True)
