"""One locked THB30,000 research candidate. No broker orders or live readiness.

The affordability step depends on actual portfolio capital and cannot be
represented by the old engine's fractional target-weight array. Use
`python -m backtest.small_capital`, not the ordinary fractional engine.
"""
from research.small_capital import SmallSpec, simulate_lots

SPEC = SmallSpec(top_n=15, reserve=.10, daily_exit=0, affordability_filter=True)
CANDIDATE_ID = 'b142b3be5b992c7b'
ENGINE = 'small_capital_lots_price_only'
LIVE_READY = False


def run(data, features, start, end, costs, capital=30000., execution=None):
    from research.small_capital import LotExecution
    assert SPEC.identity == CANDIDATE_ID
    return simulate_lots(data, features, SPEC, start, end, costs, capital,
                         execution or LotExecution(), details=True)
