from dataclasses import replace
import numpy as np
import pandas as pd
import pytest
from research.portfolio import Panel
from research.candidates import Factory, Spec
from research.refinements import Refinement, RefinementFactory, refinement_grid


def panel():
    rng=np.random.default_rng(100)
    frames={}
    for j in range(25):
        c=100*np.exp(np.cumsum(rng.normal(.001,.012+.001*j,520)))
        frames[str(j)]=pd.DataFrame({'adj_open':c,'adj_close':c,'adj_high':c*1.01,
            'adj_low':c*.99,'close':c,'volume':1e6},index=pd.bdate_range('2015',periods=520))
    return Panel(frames,{'0'})


def test_default_reproduces_incumbent():
    p=panel()
    a=RefinementFactory(p).targets(Refinement())
    b=Factory(p).targets(Spec('multi_horizon',252,20,21,200,True))
    np.testing.assert_allclose(a,b,equal_nan=True)


@pytest.mark.parametrize('changes',[{'blend':'slow'},{'blend':'downside_blend'},
    {'blend':'flow_blend'},{'blend':'quality_blend'},{'skip':42},
    {'weighting':'inverse_vol'},{'weighting':'inverse_downside'},
    {'daily_exit':3},{'rank_buffer':10}])
def test_causal_weights_and_exclusion(changes):
    p=panel();spec=replace(Refinement(),**changes)
    full=RefinementFactory(p).targets(spec)
    short=Panel({s:f.iloc[:431] for s,f in p.frames.items()},p.exclusions)
    np.testing.assert_allclose(full[:431],RefinementFactory(short).targets(spec),equal_nan=True)
    assert np.nanmax(np.nansum(full,axis=1))<=.99+1e-12
    assert np.nanmax(full)<=.99/spec.top_n*1.5+1e-12
    assert np.nansum(full[:,0])==0
    assert np.nansum(full)>0


def test_daily_exit_waits_for_confirmation():
    p=panel();f=RefinementFactory(p)
    # Controlled trailing market state, isolating confirmation and next schedule.
    f.market=pd.Series(np.r_[np.arange(1.,401.),np.full(120,1.)],index=p.dates)
    t=f.targets(Refinement(daily_exit=3))
    assert np.isnan(t[401]).all() # two bearish closes: no early liquidation
    assert np.all(t[402]==0) # third close creates the target, engine executes later
    assert np.all(t[403]==0) # retry in case a suspended holding could not be sold


def test_grid_deduplicated():
    specs=[s for _,s in refinement_grid()]
    assert len(specs)==223
    assert len({s.identity for s in specs})==223
    assert Refinement() not in specs
    assert replace(Refinement(),top_n=10) not in specs


def test_experimental_saved_module_matches_registered_candidate():
    from strategy import experimental_buffered_momentum as m
    p=panel()
    assert m.SPEC_CLASS(**m.DEFAULTS).identity=='e9a522bb24938501'
    np.testing.assert_allclose(m.generate_targets(p),
        RefinementFactory(p).targets(Refinement(top_n=15,rank_buffer=5,reserve=.05)),equal_nan=True)
    assert m.SPEC_CLASS(**{**m.DEFAULTS,'reserve':.10}).identity=='f4f5be7d82b85c48'


@pytest.mark.parametrize('tranches',[2,3])
def test_staggered_is_causal_and_averages_last_known_baskets(tranches):
    from research.staggered import StaggeredSpec,StaggeredFactory
    p=panel();spec=StaggeredSpec(tranches=tranches)
    full=StaggeredFactory(p).targets(spec)
    prefix=Panel({s:f.iloc[:431] for s,f in p.frames.items()},p.exclusions)
    np.testing.assert_allclose(full[:431],StaggeredFactory(prefix).targets(spec),equal_nan=True)
    base=Refinement(top_n=15,rank_buffer=5,reserve=.10)
    f=RefinementFactory(p)
    baskets=[f.targets(base,int(k*21/tranches)) for k in range(tranches)]
    previous=[np.zeros(len(p.symbols)) for _ in baskets]
    for i in range(len(full)):
        updated=False
        for k,t in enumerate(baskets):
            if np.isfinite(t[i]).all():previous[k]=t[i];updated=True
        if updated:np.testing.assert_allclose(full[i],np.mean(previous,axis=0))
        else:assert np.isnan(full[i]).all()
    assert np.nanmax(np.nansum(full,axis=1))<=.9+1e-12
    assert np.nansum(full[:,0])==0
