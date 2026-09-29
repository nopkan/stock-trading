"""Rank trailing proportion of positive sessions multiplied by momentum.
Retrospective research candidate f397049c64b94cab; see experiment registry.
"""
from research.candidates import Factory, Spec

FAMILY = 'consistent_trend'
DEFAULTS = {'lookback': 126, 'top_n': 20, 'rebalance': 21, 'trend': 200, 'market_filter': True, 'skip': 21, 'min_turnover_thb': 10000000, 'reserve': 0.01}


def generate_targets(panel, **parameters):
    settings = {**DEFAULTS, **parameters}
    return Factory(panel).targets(Spec(family=FAMILY, **settings))
