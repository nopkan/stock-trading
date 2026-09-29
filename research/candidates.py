"""Shared candidate recipes. Only promoted strategies get active .py modules.

Every score is based on trailing information. No stock-specific exceptions or
future constituent information beyond the disclosed fixed-snapshot universe.
"""
from dataclasses import dataclass, asdict
from functools import cached_property
import hashlib
import json
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Spec:
    family: str
    lookback: int = 126
    top_n: int = 10
    rebalance: int = 21
    trend: int = 0
    market_filter: bool = False
    skip: int = 21
    min_turnover_thb: float = 10_000_000
    reserve: float = .01

    @property
    def canonical(self):
        return json.dumps(asdict(self), sort_keys=True, separators=(',', ':'))

    @property
    def identity(self):
        return hashlib.sha256(self.canonical.encode()).hexdigest()[:16]


RULES = {
    'momentum': 'Rank trailing total return, skipping the latest month; select positive leaders.',
    'risk_adjusted_momentum': 'Rank trailing skipped-month return divided by 63-session realized volatility.',
    'multi_horizon': 'Rank mean percentile of skipped-month 3-, 6-, 12-month returns.',
    'high_proximity': 'Rank closeness to trailing high; require positive trailing return.',
    'trend_quality': 'Rank trailing return multiplied by directional efficiency (net move / sum absolute daily moves).',
    'volume_flow': 'Rank mean signed-volume pressure, require positive trailing return.',
    'low_volatility': 'Rank inverse 63-session volatility among positive-momentum stocks.',
    'ma_strength': 'Rank close / trailing moving average; require positive return.',
    'reversal_in_trend': 'Rank negative 21-session return within positive long-term momentum.',
    'downside_momentum': 'Rank skipped-month return / trailing downside deviation.',
    'consistent_trend': 'Rank trailing proportion of positive sessions multiplied by momentum.',
    'channel_position': 'Rank position within trailing high-low channel; require positive momentum.'
}


class Factory:
    def __init__(self, panel):
        self.panel = panel
        self.c = panel.close.ffill()  # Valuation/indicator state only; eligibility requires an actual current bar.
        self.ret = self.c.pct_change(fill_method=None)
        self.cache = {}
        self.available = panel.close.notna() & panel.volume.gt(0)
        self.age = panel.close.notna().cumsum()
        self.liquid = panel.value.rolling(20, min_periods=15).median()
        self.vol = self.ret.rolling(63, min_periods=63).std().clip(lower=.002)
        self.downside = self.ret.clip(upper=0).pow(2).rolling(63, min_periods=63).mean().pow(.5).clip(lower=.002)
        # Equal-weight daily market proxy, based only on returns available at each date.
        validret = self.ret.where(panel.close.notna())
        validret.loc[:,list(panel.exclusions)] = np.nan
        self.market = (1+validret.mean(axis=1).fillna(0)).cumprod()
        self.market_bull = self.market > self.market.rolling(200).mean()

    def feature(self, name, window, skip=0):
        key = (name, window, skip)
        if key not in self.cache:
            c = self.c
            if name == 'momentum':
                value = c.shift(skip)/c.shift(window)-1
            elif name == 'high':
                value = c/c.rolling(window).max()
            elif name == 'mean':
                value = c/c.rolling(window).mean()-1
            elif name == 'efficiency':
                value = (c-c.shift(window)).abs()/c.diff().abs().rolling(window).sum().replace(0,np.nan)
            elif name == 'flow':
                v = self.panel.volume.fillna(0)
                value = (np.sign(self.ret)*v).rolling(window).sum()/v.rolling(window).sum().replace(0,np.nan)
            elif name == 'positive':
                value = self.ret.gt(0).astype(float).rolling(window).mean()
            elif name == 'channel':
                low, high = self.panel.low.rolling(window).min(), self.panel.high.rolling(window).max()
                value = (c-low)/(high-low).replace(0,np.nan)
            else:
                raise ValueError(name)
            self.cache[key] = value
        return self.cache[key]

    def targets(self, spec):
        if spec.family not in RULES or spec.top_n < 10 or spec.rebalance < 1 or spec.lookback <= spec.skip:
            raise ValueError('Invalid candidate specification')
        mom = self.feature('momentum',spec.lookback,spec.skip)
        family = spec.family
        if family == 'momentum': score = mom
        elif family == 'risk_adjusted_momentum': score = mom/self.vol
        elif family == 'downside_momentum': score = mom/self.downside
        elif family == 'multi_horizon':
            score = sum(self.feature('momentum',w,spec.skip).rank(axis=1,pct=True) for w in [63,126,252])/3
        elif family == 'high_proximity': score = self.feature('high',spec.lookback)
        elif family == 'trend_quality': score = mom*self.feature('efficiency',spec.lookback)
        elif family == 'volume_flow': score = self.feature('flow',spec.lookback)
        elif family == 'low_volatility': score = -self.vol
        elif family == 'ma_strength': score = self.feature('mean',spec.lookback)
        elif family == 'reversal_in_trend': score = -self.feature('momentum',21,0)
        elif family == 'consistent_trend': score = mom*self.feature('positive',spec.lookback)
        elif family == 'channel_position': score = self.feature('channel',spec.lookback)
        eligible = self.available & self.age.ge(max(252,spec.lookback+1)) & self.liquid.ge(spec.min_turnover_thb) & mom.gt(0)
        if spec.trend:
            eligible &= self.feature('mean',spec.trend).gt(0)
        if spec.market_filter:
            eligible &= self.market_bull.to_numpy()[:,None]
        for s in self.panel.exclusions:
            eligible.loc[:,s] = False
        score = score.where(eligible).to_numpy()
        result = np.full(score.shape,np.nan)
        for i in range(0,len(score),spec.rebalance):
            row = score[i]
            order = np.argsort(-np.nan_to_num(row,nan=-np.inf),kind='stable')
            selected = order[np.isfinite(row[order])][:spec.top_n]
            result[i] = 0.
            result[i,selected] = (1-spec.reserve)/spec.top_n
        return result


def initial_grid():
    """Predeclared grid: 12 families, mostly 24 variants; no outcome-based additions."""
    result = []
    for family in RULES:
        windows = [126,252] if family != 'multi_horizon' else [252]
        for lookback in windows:
            for top_n in [10,20]:
                for rebalance in [21,63]:
                    for trend, market in [(0,False),(200,False),(200,True)]:
                        result.append(Spec(family,lookback,top_n,rebalance,trend,market))
    return result
