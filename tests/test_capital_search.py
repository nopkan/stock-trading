import numpy as np
from research.capital_search import CapitalRecipe, rank_features, MODES
from research.small_capital import SmallSpec
from research.portfolio import Panel
from tests.test_small_capital import make_panel


def test_original_id_and_serialization_preserved():
    r = CapitalRecipe(SmallSpec(top_n=15, reserve=.05, affordability_filter=False))
    assert r.identity == 'e9a522bb24938501'
    for mode in MODES:
        r = CapitalRecipe(SmallSpec(top_n=5), mode)
        assert CapitalRecipe.from_parameters(r.parameters) == r
        assert CapitalRecipe.from_parameters(r.parameters).identity == r.identity


def test_all_new_rankings_are_prefix_invariant():
    rng = np.random.default_rng(25)
    p = make_panel(20*np.exp(np.cumsum(rng.normal(.0005,.012,550))))
    second = p.frames['A'].copy()
    for col in ['open','close','adj_open','adj_close','adj_high','adj_low']:
        second[col] = 30*np.exp(np.cumsum(rng.normal(.0004,.02,550)))
    p = Panel({'A':p.frames['A'],'B':second})
    full = rank_features(p)
    short = rank_features(Panel({s:f.iloc[:430] for s,f in p.frames.items()}))
    for mode in MODES:
        np.testing.assert_allclose(full[mode].rank.iloc[:430],short[mode].rank,equal_nan=True)
        np.testing.assert_array_equal(full[mode].eligible.iloc[:430],short[mode].eligible)
        np.testing.assert_array_equal(full[mode].bull[:430],short[mode].bull)


def test_frozen_100000_module_and_config_agree():
    import json
    from research.portfolio import ROOT
    from strategy.set100_high_proximity_100000 import RECIPE, CANDIDATE_ID, LIVE_READY
    config = json.loads((ROOT/'configs/set100_100000_strategy.json').read_text())
    assert RECIPE.identity == CANDIDATE_ID == config['candidate']
    assert RECIPE.parameters == config['parameters']
    assert config['capital_thb'] == 100000
    assert not LIVE_READY and not config['live_ready']
