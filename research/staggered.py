"""Average several independently scheduled desired momentum baskets.

This is a single netted portfolio: whenever a basket updates, the whole account
rebalances to their average desired weights. It is not an average of backtest
returns, and all resulting trades pay the common engine's fees.
"""
from dataclasses import dataclass, asdict
import hashlib
import json
import numpy as np
from research.refinements import Refinement, RefinementFactory


@dataclass(frozen=True)
class StaggeredSpec:
    family: str = 'staggered_multi_horizon'
    top_n: int = 15
    rank_buffer: int = 5
    reserve: float = .10
    tranches: int = 3

    @property
    def identity(self):
        return hashlib.sha256(json.dumps(asdict(self),sort_keys=True,separators=(',', ':')).encode()).hexdigest()[:16]


class StaggeredFactory(RefinementFactory):
    def targets(self,spec,phase=0):
        if isinstance(spec,Refinement):
            return super().targets(spec,phase)
        if spec.family!='staggered_multi_horizon' or spec.tranches not in (2,3):
            raise ValueError('Invalid staggered specification')
        base=Refinement(top_n=spec.top_n,rank_buffer=spec.rank_buffer,reserve=spec.reserve)
        offsets=[(phase+int(k*21/spec.tranches))%21 for k in range(spec.tranches)]
        targets=[super(StaggeredFactory,self).targets(base,p) for p in offsets]
        combined=np.zeros_like(targets[0]);events=np.zeros(len(combined),dtype=bool)
        for t in targets:
            scheduled=~np.isnan(t).all(axis=1)
            events|=scheduled
            last=np.maximum.accumulate(np.where(scheduled,np.arange(len(t)),-1))
            valid=last>=0
            combined[valid]+=t[last[valid]]/spec.tranches
        combined[~events]=np.nan
        return combined


def grid():
    return [StaggeredSpec(top_n=n,rank_buffer=b,reserve=c,tranches=t)
            for n in (15,20) for b in (0,5,10) for c in (.01,.05,.10) for t in (2,3)]
