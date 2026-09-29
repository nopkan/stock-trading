"""Rank mean percentile of skipped-month 3-, 6-, 12-month returns.
Retrospective research candidate f4f96d173a82b60a; see experiment registry.
"""
from research.candidates import Factory, Spec

FAMILY = 'multi_horizon'
DEFAULTS = {'lookback': 252, 'top_n': 20, 'rebalance': 21, 'trend': 200, 'market_filter': True, 'skip': 21, 'min_turnover_thb': 10000000, 'reserve': 0.01}


def generate_targets(panel, **parameters):
    settings = {**DEFAULTS, **parameters}
    return Factory(panel).targets(Spec(family=FAMILY, **settings))
