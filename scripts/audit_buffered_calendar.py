"""User-requested diagnostic rerun of a frozen recipe; not a new candidate."""
import json
import pandas as pd
from research.portfolio import ROOT, Panel, FeeSchedule, simulate, benchmark
from research.refinements import RefinementFactory, Refinement


def main():
    out=ROOT/'reports/buffered_momentum_deep_dive_20260929'
    panel=Panel.load()
    index=pd.read_csv(ROOT/'data/indices/set100_tradingview_daily.csv',index_col='date',parse_dates=True)
    removed=panel.dates.difference(index.index)
    clean=Panel({s:f.loc[f.index.intersection(index.index)] for s,f in panel.frames.items()},panel.exclusions,panel.source_hashes)
    spec=Refinement(top_n=15,rank_buffer=5,reserve=.05)
    target=RefinementFactory(clean).targets(spec)
    result,curve,fills=simulate(clean,target,'2017-01-04','2026-09-28',FeeSchedule(),details=True)
    base,bc=benchmark(clean,'2017-01-04','2026-09-28',FeeSchedule())
    curve.to_csv(out/'calendar_audit_strategy_equity.csv',index_label='date',header=['equity'])
    fills.to_csv(out/'calendar_audit_strategy_fills.csv',index=False)
    bc.to_csv(out/'calendar_audit_buy_hold_equity.csv',index_label='date',header=['equity'])
    record={'candidate':spec.identity,'reason':'User-requested deep analysis: remove seven provider holiday placeholder rows; identical parameters and fee schedule, no optimization.', 'removed_dates':[str(d.date()) for d in removed], 'Strategy':result,'Buy_hold':base}
    (out/'calendar_audit.json').write_text(json.dumps(record,indent=2))
    print(json.dumps(record,indent=2))


if __name__=='__main__':main()
