"""Experimental buffered momentum: higher historical return, incomplete robustness.

Candidate e9a522bb24938501. Passed normal/base/stress comparisons, but failed
strict drawdown dominance under delayed fills and THAI exclusion. Deliberately
not included in active.json. See reports/momentum_refinement_20260929/RESULTS.md.
"""
from dataclasses import asdict
from research.refinements import Refinement, RefinementFactory

SPEC_CLASS = Refinement
RESEARCH_DEPENDENCIES = ['research/refinements.py']
DEFAULTS = asdict(Refinement(top_n=15,rank_buffer=5,reserve=.05))


def generate_targets(panel, **parameters):
    return RefinementFactory(panel).targets(Refinement(**{**DEFAULTS,**parameters}))
