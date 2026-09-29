"""Causal indicators: every output depends only on this and earlier rows."""
import numpy as np
import pandas as pd


def sma(s, window):
    return s.rolling(window, min_periods=window).mean()


def ema(s, window):
    return s.ewm(span=window, adjust=False, min_periods=window).mean()


def rsi(s, window=14):
    """Wilder RSI, seeded with the first window's arithmetic average."""
    delta = s.diff().to_numpy()
    result = np.full(len(s), np.nan)
    if len(s) <= window:
        return pd.Series(result, index=s.index)
    gain = np.maximum(delta[1:window+1], 0).mean()
    loss = np.maximum(-delta[1:window+1], 0).mean()
    for i in range(window, len(s)):
        if i > window:
            gain = (gain * (window-1) + max(delta[i], 0)) / window
            loss = (loss * (window-1) + max(-delta[i], 0)) / window
        result[i] = 50 if gain == loss == 0 else (100 if loss == 0 else 100 - 100/(1+gain/loss))
    return pd.Series(result, index=s.index)


def positions(entries, exits, max_holding=None):
    """Close-of-session desired state. Exit wins; no reentry on the same close."""
    holding, age, result = False, 0, []
    for enter, leave in zip(entries.fillna(False), exits.fillna(False)):
        if holding:
            age += 1
            if leave or (max_holding is not None and age >= max_holding):
                holding, age = False, 0
        elif enter and not leave:
            holding, age = True, 0
        result.append(int(holding))
    return pd.Series(result, index=entries.index, dtype=int)
