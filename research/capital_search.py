"""Rank variants for bounded THB100k research; shared whole-lot execution."""
from dataclasses import asdict, dataclass
import hashlib
import json
from types import SimpleNamespace
from research.candidates import Factory
from research.small_capital import SmallSpec, Features


MODES = ('multi_horizon', 'medium_long', 'risk_adjusted', 'high_proximity', 'trend_quality')


@dataclass(frozen=True)
class CapitalRecipe:
    sizing: SmallSpec
    ranking: str = 'multi_horizon'

    def __post_init__(self):
        if self.ranking not in MODES:
            raise ValueError('Unknown ranking')

    @property
    def parameters(self):
        if self.ranking == 'multi_horizon':
            return asdict(self.sizing)
        return {'family': 'capital_ranked_momentum', 'ranking': self.ranking,
                'sizing': asdict(self.sizing)}

    @property
    def identity(self):
        if self.ranking == 'multi_horizon':
            return self.sizing.identity
        return hashlib.sha256(json.dumps(self.parameters, sort_keys=True,
            separators=(',', ':')).encode()).hexdigest()[:16]

    @classmethod
    def from_parameters(cls, p):
        if p['family'] == 'capital_ranked_momentum':
            return cls(SmallSpec(**p['sizing']), p['ranking'])
        return cls(SmallSpec(**p))


def rank_features(panel):
    """Only completed trailing daily observations; shared eligibility/regime."""
    common = Features(panel)
    f = Factory(panel)
    scores = {
        'multi_horizon': common.rank,
        'medium_long': sum(f.feature('momentum', n, 21).rank(axis=1, pct=True)
                           for n in (126, 252)) / 2,
        'risk_adjusted': f.feature('momentum', 126, 21) / f.vol,
        'high_proximity': f.feature('high', 252),
        'trend_quality': f.feature('momentum', 126, 21) * f.feature('efficiency', 126),
    }
    return {mode: SimpleNamespace(rank=rank, eligible=common.eligible, bull=common.bull)
            for mode, rank in scores.items()}
