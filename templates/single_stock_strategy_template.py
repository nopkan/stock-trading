"""Copy to strategy/my_strategy.py, then run --strategy my_strategy.

Input: date-indexed adjusted open/high/low/close and provider volume.
Output: desired position AT THIS CLOSE (0 cash, 1 long). The engine delays
execution to the next observed valid open. Do not shift again here.
Use only trailing indicators; never shift(-1), bfill or centered windows.
"""
from strategy.indicators import sma

DEFAULTS = {"period": 50}


def generate_signals(prices, period=50):
    if period < 1:
        raise ValueError("period must be positive")
    return (prices.close > sma(prices.close, period)).astype(int)
