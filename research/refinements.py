"""Predeclared refinements of the retained multi-horizon momentum portfolio.

All decisions use information through the signal close. Execution remains in
the unchanged common engine. These experiments reuse previously seen history.
"""
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import numpy as np
from research.candidates import Factory


@dataclass(frozen=True)
class Refinement:
    family: str = 'multi_horizon_refined'
    blend: str = 'equal'
    top_n: int = 20
    rebalance: int = 21
    trend: int = 200
    market_window: int = 200
    skip: int = 21
    weighting: str = 'equal'
    daily_exit: int = 0
    rank_buffer: int = 0
    min_turnover_thb: float = 10_000_000
    reserve: float = .01

    @property
    def identity(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True,
            separators=(',', ':')).encode()).hexdigest()[:16]


BLENDS = {'equal': (1, 1, 1), 'medium_long': (0, 1, 1),
          'slow': (2, 3, 5), 'fast': (5, 3, 2), 'medium': (1, 2, 1)}


class RefinementFactory(Factory):
    def targets(self, spec, phase=0):
        if spec.family != 'multi_horizon_refined' or spec.top_n < 10 or spec.rebalance < 1:
            raise ValueError('Invalid refinement specification')
        if not 0 <= spec.skip < 63 or not 0 <= phase < spec.rebalance:
            raise ValueError('Invalid lag or schedule phase')
        if spec.weighting not in ('equal', 'inverse_vol', 'inverse_downside'):
            raise ValueError('Unknown weighting')
        if spec.daily_exit < 0 or spec.rank_buffer < 0 or not 0 <= spec.reserve < 1:
            raise ValueError('Invalid risk parameters')
        key = ('refined_score', spec.blend, spec.skip)
        if key not in self.cache:
            ranks = [self.feature('momentum', w, spec.skip).rank(axis=1, pct=True)
                     for w in (63, 126, 252)]
            base = sum(ranks)/3
            if spec.blend in BLENDS:
                weights = BLENDS[spec.blend]
                score = sum(w*r for w, r in zip(weights, ranks))/sum(weights)
            elif spec.blend == 'downside_blend':
                score = .75*base + .25*(self.feature('momentum',252,spec.skip)/self.downside).rank(axis=1,pct=True)
            elif spec.blend == 'flow_blend':
                score = .75*base + .25*self.feature('flow',126).rank(axis=1,pct=True)
            elif spec.blend == 'quality_blend':
                score = .75*base + .25*self.feature('efficiency',126).rank(axis=1,pct=True)
            else:
                raise ValueError('Unknown blend')
            self.cache[key] = score
        bull = self.market.gt(self.market.rolling(spec.market_window).mean())
        eligible = (self.available & self.age.ge(253) &
                    self.liquid.ge(spec.min_turnover_thb) &
                    self.feature('momentum',252,spec.skip).gt(0) &
                    self.feature('mean',spec.trend).gt(0))
        for s in self.panel.exclusions:
            eligible.loc[:,s] = False
        scores = self.cache[key].where(eligible).to_numpy()
        risk = (self.vol if spec.weighting == 'inverse_vol' else self.downside).to_numpy()
        result = np.full(scores.shape, np.nan)
        exits = ((~bull).rolling(spec.daily_exit).sum().eq(spec.daily_exit).to_numpy()
                 if spec.daily_exit else np.zeros(len(scores),dtype=bool))
        selected = np.array([],dtype=int)
        for i in range(len(scores)):
            if spec.daily_exit and exits[i]:
                # Retry zero targets while risk-off in case a holding cannot trade.
                result[i] = 0.
                selected = np.array([],dtype=int)
                continue
            if i % spec.rebalance != phase:
                continue
            result[i] = 0.
            if not bull.iloc[i]:
                selected = np.array([],dtype=int)
                continue
            row = scores[i]
            order = np.argsort(-np.nan_to_num(row,nan=-np.inf),kind='stable')
            order = order[np.isfinite(row[order])]
            # Buffer retains desired members still inside N+buffer; no future fills used.
            retained = [j for j in order[:spec.top_n+spec.rank_buffer]
                        if j in selected][:spec.top_n] if spec.rank_buffer else []
            selected = np.array((retained+[j for j in order if j not in retained])[:spec.top_n],dtype=int)
            if not len(selected):
                continue
            if spec.weighting == 'equal':
                weights = np.ones(len(selected))
            else:
                weights = 1/risk[i,selected]
                weights /= weights.mean()
                # Do not redistribute the clipped excess: leave it in cash.
                weights = np.minimum(weights,1.5)
            result[i,selected] = weights*(1-spec.reserve)/spec.top_n
        return result


def refinement_grid():
    """223 unique new variants; exclude equivalent recipes already in the ledger."""
    result = {}
    base = Refinement()
    def add(group, **params):
        s = replace(base, **params)
        # These two exact recipes were already evaluated by the original search.
        if s == base or s == replace(base,top_n=10):
            return
        result.setdefault(s.identity,(group,s))
    for blend in [*BLENDS,'downside_blend','flow_blend','quality_blend']:
        for n in (10,15,20,25,30):
            for period in (10,21,42):
                add('score_and_breadth',blend=blend,top_n=n,rebalance=period)
    for market in (100,150,250):
        for trend in (100,150,200,250):
            for n in (15,20,25):
                add('trend_filter',market_window=market,trend=trend,top_n=n)
    for weighting in ('inverse_vol','inverse_downside'):
        for n in (15,20,25):
            for period in (10,21,42):
                add('risk_weights',weighting=weighting,top_n=n,rebalance=period)
    for market in (150,200,250):
        for days in (1,3,5):
            for n in (15,20,25):
                add('daily_risk_exit',market_window=market,daily_exit=days,top_n=n)
    for skip in (5,10,42):
        for n in (15,20,25):
            for blend in ('equal','slow'):
                add('skip_interval',skip=skip,top_n=n,blend=blend)
    for buffer in (5,10):
        for n in (15,20,25):
            add('rank_buffer',rank_buffer=buffer,top_n=n)
    return list(result.values())
