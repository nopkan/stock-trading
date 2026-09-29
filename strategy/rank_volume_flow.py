"""Rank mean signed-volume pressure, require positive trailing return.
Retrospective research candidate 8052992d1be308f6; see experiment registry.
"""
from research.candidates import Factory, Spec

FAMILY = 'volume_flow'
DEFAULTS = {'lookback': 252, 'top_n': 20, 'rebalance': 21, 'trend': 200, 'market_filter': True, 'skip': 21, 'min_turnover_thb': 10000000, 'reserve': 0.01}


def generate_targets(panel, **parameters):
    settings = {**DEFAULTS, **parameters}
    return Factory(panel).targets(Spec(family=FAMILY, **settings))
