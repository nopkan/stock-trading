"""Benchmark for the same universe and execution/cost model."""
DEFAULTS = {}


def generate_signals(prices):
    import pandas as pd
    return pd.Series(1, index=prices.index, dtype=int)
