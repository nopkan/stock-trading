"""Rank closeness to trailing high; require positive trailing return.
Retrospective research candidate 48544834d3c5f35b; see experiment registry.
"""
from research.candidates import Factory, Spec

FAMILY = 'high_proximity'
DEFAULTS = {'lookback': 126, 'top_n': 10, 'rebalance': 63, 'trend': 200, 'market_filter': True, 'skip': 21, 'min_turnover_thb': 10000000, 'reserve': 0.01}


def generate_targets(panel, **parameters):
    settings = {**DEFAULTS, **parameters}
    return Factory(panel).targets(Spec(family=FAMILY, **settings))
