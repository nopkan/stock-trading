"""Frozen THB100k 52-week-high candidate; research only, not live-ready.

Use backtest.capital_ranked; the fractional target-weight runner is unsuitable.
Three desired slots, 42-session rebalance, three-day market-regime exit.
Failed extended timing/contributor robustness: see the report final_decision.json.
"""
from research.small_capital import SmallSpec, LotExecution, simulate_lots
from research.capital_search import CapitalRecipe, rank_features

RECIPE = CapitalRecipe(SmallSpec(top_n=3, reserve=.05, rebalance=42,
                                daily_exit=3, rank_buffer=5), 'high_proximity')
CANDIDATE_ID = '60ee10de14d6268a'
LIVE_READY = False


def run(data, start, end, costs, capital=100000., execution=None):
    assert RECIPE.identity == CANDIDATE_ID
    features = rank_features(data.panel)[RECIPE.ranking]
    return simulate_lots(data, features, RECIPE.sizing, start, end, costs,
                         capital, execution or LotExecution(), details=True)
