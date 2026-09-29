"""Post-search sensitivity audit. All evaluations append to the same registry.

Diagnostic audits do not create a new independent holdout. Candidates remain
retrospective and selected from a fixed current-constituent universe.
"""
from dataclasses import asdict
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

from research.candidates import Spec, Factory
from research.portfolio import Panel, FeeSchedule, ROOT, simulate, benchmark
from research.registry import Registry
from research.search import PERIODS

FOLDER=ROOT/'reports/strategy_search_20260929_v2'


def main():
    global FOLDER
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder',type=Path,default=FOLDER)
    FOLDER=parser.parse_args().folder
    panel=Panel.load()
    configs=json.loads((ROOT/'configs/thai_trading_costs.json').read_text())
    fees=FeeSchedule(**configs['base'])
    registry=Registry(ROOT/'research/experiments')
    plan=json.loads((FOLDER/'search_plan.json').read_text())
    for file,digest in plan['data_and_code']['source'].items():
        if hashlib.sha256((ROOT/file).read_bytes()).hexdigest()!=digest:
            raise RuntimeError('Audit source differs from frozen search context: '+file)
    if panel.source_hashes!=plan['data_and_code']['prices']:
        raise RuntimeError('Audit prices differ from frozen search dataset')
    source_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    context=plan['context']+'_audit_'+source_hash[:10]
    candidates=pd.read_csv(FOLDER/'all_candidates.csv')
    qualified=candidates.loc[candidates.qualified].sort_values('selection_score',ascending=False)
    audit_plan={'context':context,'candidates':qualified.candidate.tolist(),
        'tests':['one_additional_session_execution_delay','exclude_DELTA','exclude_THAI'],
        'periods':['full','confirmation'],
        'retention':'Start with original qualification; require positive excess CAGR in all six sensitivity runs. Select at most one per family, in original discovery/validation score order, reject return correlations >=0.95 with already retained candidates. These are additional retrospective screens, not independent confirmation.',
        'correlation_threshold':.95}
    (FOLDER/'audit_plan.json').write_text(json.dumps(audit_plan,indent=2))
    reference={}
    base_factory=Factory(panel)
    scenario_panels={'delay':panel,'exclude_DELTA':Panel(panel.frames,panel.exclusions|{'DELTA'}),
                     'exclude_THAI':Panel(panel.frames,panel.exclusions|{'THAI'})}
    factories={k:Factory(p) for k,p in scenario_panels.items() if k!='delay'}
    rows=[]
    for _,candidate in qualified.iterrows():
        spec=Spec(**{k:candidate[k].item() if hasattr(candidate[k],'item') else candidate[k] for k in Spec.__dataclass_fields__})
        for scenario,p in scenario_panels.items():
            targets=base_factory.targets(spec) if scenario=='delay' else factories[scenario].targets(spec)
            if scenario=='delay':targets=np.vstack([np.full((1,targets.shape[1]),np.nan),targets[:-1]])
            for period in ['full','confirmation']:
                stage=scenario+'_'+period
                key=(scenario,period)
                if key not in reference:
                    reference[key]=benchmark(p,*PERIODS[period],fees,configs['initial_capital_thb'])[0]
                result=registry.get(context,spec.identity,stage)
                if result is None:
                    result,_,_=simulate(p,targets,*PERIODS[period],fees,configs['initial_capital_thb'])
                    result.update(excess_cagr=result['cagr']-reference[key]['cagr'],
                                  benchmark_cagr=reference[key]['cagr'],scenario=scenario,period=period)
                    registry.put(context,spec.identity,stage,asdict(spec),result)
                rows.append({'candidate':spec.identity,'family':spec.family,**result})
        print('Audited',spec.identity,spec.family,flush=True)
        registry.export()
    results=pd.DataFrame(rows)
    results.to_csv(FOLDER/'sensitivity_results.csv',index=False)
    passed=results.groupby('candidate').excess_cagr.min().gt(0)
    eligible=qualified.loc[qualified.candidate.map(passed).fillna(False)]
    curves=pd.DataFrame({row.candidate:pd.read_csv(FOLDER/row.candidate/'full_base_equity.csv',index_col='date').equity for _,row in eligible.iterrows()})
    correlations=curves.pct_change().corr()
    kept=[]
    dispositions=[]
    for _,r in qualified.iterrows():
        reason='retained'
        if not passed.get(r.candidate,False):reason='rejected_sensitivity'
        elif r.family in [x.family for x in kept]:reason='same_family_as_retained'
        elif len(kept)>=5:reason='qualified_not_in_top_five_discovery_validation_ranking'
        elif any(correlations.loc[r.candidate,x.candidate]>=.95 for x in kept):reason='near_duplicate_return_profile'
        else:kept.append(r)
        dispositions.append({'candidate':r.candidate,'family':r.family,'disposition':reason})
    pd.DataFrame(dispositions).to_csv(FOLDER/'audit_dispositions.csv',index=False)
    retained=pd.DataFrame(kept)
    retained.to_csv(FOLDER/'retained_strategies.csv',index=False)
    if kept:
        correlations.loc[retained.candidate,retained.candidate].to_csv(FOLDER/'retained_return_correlations.csv')
    registry.export()
    print('Retained after audits:',len(kept),flush=True)
    print(retained[['candidate','family','full_base_cagr','confirmation_base_cagr']].to_string(index=False) if kept else 'None',flush=True)


if __name__=='__main__':main()
