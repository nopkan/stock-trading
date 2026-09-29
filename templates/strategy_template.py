"""Copy to strategy/my_strategy.py; run python -m backtest.run --strategy my_strategy.
Return close-of-session weights aligned to panel.dates and panel.symbols.
All-NaN row means no rebalance; other rows must be >=0 with sum <=1.
The engine delays execution once. Do not shift targets here.
"""
from research.candidates import Factory, Spec

DEFAULTS = {'lookback': 126, 'top_n': 20, 'rebalance': 21, 'trend': 200,
            'market_filter': True, 'skip': 21, 'min_turnover_thb': 10000000, 'reserve': .01}


def generate_targets(panel, **parameters):
    return Factory(panel).targets(Spec(family='momentum', **{**DEFAULTS, **parameters}))
