"""Adaptive second batch: lower exposure in three promising development recipes.

The first batch failed strict confirmation. This follow-up is explicitly
adaptive and retrospective, not an independent validation exercise.
"""
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json
import numpy as np
import pandas as pd
from research.portfolio import ROOT, Panel, FeeSchedule, simulate, benchmark
from research.refinements import Refinement, RefinementFactory
from research.refine_search import PERIODS, INCUMBENT
from research.registry import Registry

FOLDER=ROOT/'reports/momentum_reserve_20260929'


def grid():
    bases=[Refinement(blend='slow',top_n=15),
           Refinement(top_n=15,rank_buffer=5),Refinement(top_n=15,rank_buffer=10)]
    return [replace(s,reserve=cash) for s in bases for cash in (.05,.10,.15,.20)]


def main():
    FOLDER.mkdir(exist_ok=True)
    panel=Panel.load()
    config=json.loads((ROOT/'configs/thai_trading_costs.json').read_text())
    hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
        ['research/portfolio.py','research/candidates.py','research/refinements.py',
         'research/refine_search.py','research/refine_reserve.py',
         'configs/thai_trading_costs.json','configs/data_exclusions.json']}
    source={'prices':panel.source_hashes,'code':hashes}
    context='reserve_'+hashlib.sha256(json.dumps(source,sort_keys=True).encode()).hexdigest()[:16]
    reg=Registry(ROOT/'research/experiments')
    costs={k:FeeSchedule(**config[k]) for k in ['base','stress']}
    specs=grid()
    plan={'context':context,'created_at':datetime.now(timezone.utc).isoformat(),
        'source':source,'candidates':[asdict(s) for s in specs],'periods':PERIODS,
        'costs':config,'prior_batch':'reports/momentum_refinement_20260929',
        'reason':'Adaptive follow-up after 223 variants produced one shortlist candidate that failed stricter confirmation. Its small drawdown improvement vanished at stress costs. Test 5/10/15/20% cash reserves in the slow-blend top15 candidate and two buffer top15 candidates with promising development performance. All observed results remain disclosed.',
        'screen':'Higher CAGR and smaller maximum drawdown in 2017-2023 development; discovery and validation CAGR each within 2 percentage points of incumbent or better. Rank by development CAGR gain + drawdown improvement. Lock all passing variants BEFORE examining their recent/full results.',
        'confirm':'Same as batch1: full CAGR higher and drawdown smaller at base AND stress costs; recent CAGR within 2 percentage points of incumbent or better, recent drawdown no worse, recent CAGR above buy-and-hold, at both costs.',
        'audit':'All passing-screen variants plus first-batch shortlist: full and recent base costs, +1 execution session, exclude DELTA, exclude THAI, +10-session rebalance phase. Compare identically perturbed incumbent. Audit promotion requires higher full CAGR AND smaller full drawdown in ALL four scenarios; recent comparisons reported. Highest frozen development score among confirmed audit-pass variants is selected.',
        'holdout':'None remaining in existing data. All research retrospective; forward dates after 2026-09-28 are reserved. Current-constituent bias remains.'}
    path=FOLDER/'search_plan.json'
    if path.exists():
        if json.loads(path.read_text())['context']!=context:raise RuntimeError('Frozen source changed')
    else:path.write_text(json.dumps(plan,indent=2))
    factory=RefinementFactory(panel)
    def evaluate(spec,stage,p=panel,f=factory,scenario=None):
        candidate=INCUMBENT if spec==Refinement() else spec.identity
        old=reg.get(context,candidate,stage)
        if old is not None:return old
        period,profile=stage.split('_')[-2:]
        t=f.targets(spec,phase=10 if scenario=='phase10' else 0)
        if scenario=='delay':t=np.vstack([np.full((1,t.shape[1]),np.nan),t[:-1]])
        r,e,fills=simulate(p,t,*PERIODS[period],costs[profile],config['initial_capital_thb'],details=scenario is None)
        reg.put(context,candidate,stage,asdict(spec),r)
        if scenario is None:
            folder=FOLDER/candidate;folder.mkdir(exist_ok=True)
            e.rename('equity').rename_axis('date').to_csv(folder/f'{stage}_equity.csv')
            fills.to_csv(folder/f'{stage}_fills.csv',index=False)
        return r
    baseline={}
    for period in PERIODS:
        for profile in ['base','stress']:
            stage=period+'_'+profile
            baseline[stage]=evaluate(Refinement(),stage)
            if reg.get(context,'benchmark',stage) is None:
                r,e=benchmark(panel,*PERIODS[period],costs[profile],config['initial_capital_thb'])
                reg.put(context,'benchmark',stage,{'family':'buy_hold'},r)
                e.rename('equity').rename_axis('date').to_csv(FOLDER/f'benchmark_{stage}.csv')
    (FOLDER/'incumbent.json').write_text(json.dumps(baseline,indent=2))
    rows=[]
    for spec in specs:
        row={'candidate':spec.identity,'parameters':json.dumps(asdict(spec),sort_keys=True)}
        for period in ['discovery','validation','development']:
            r=evaluate(spec,period+'_base')
            row.update({period+'_base_'+k:v for k,v in r.items()})
        gain=row['development_base_cagr']-baseline['development_base']['cagr']
        dd=row['development_base_max_drawdown']-baseline['development_base']['max_drawdown']
        row['selection_score']=gain+dd
        row['screen_pass']=bool(gain>0 and dd>0 and all(row[p+'_base_cagr']>=baseline[p+'_base']['cagr']-.02 for p in ['discovery','validation']))
        rows.append(row)
    locked=[r['candidate'] for r in rows if r['screen_pass']]
    lockpath=FOLDER/'locked_shortlist.json'
    if lockpath.exists():
        if json.loads(lockpath.read_text())['candidate_ids']!=locked:raise RuntimeError('Shortlist changed')
    else:lockpath.write_text(json.dumps({'locked_at':datetime.now(timezone.utc).isoformat(),'candidate_ids':locked},indent=2))
    pd.DataFrame(rows).to_csv(FOLDER/'screen_results.csv',index=False)
    print('Cash-reserve batch screened; locked',len(locked),'of',len(specs),flush=True)
    for spec,row in zip(specs,rows):
        row['confirmed']=False
        if not row['screen_pass']:continue
        ok=True
        for stage in ['recent_base','recent_stress','full_base','full_stress']:
            r=evaluate(spec,stage);b=baseline[stage]
            row.update({stage+'_'+k:v for k,v in r.items()})
            ok &= r['max_drawdown']>b['max_drawdown'] and r['cagr']>b['cagr']-(.02 if stage.startswith('recent') else 0)
            if stage.startswith('recent'):ok &= r['cagr']>reg.get(context,'benchmark',stage)['cagr']
        row['confirmed']=bool(ok)
        print(spec.identity,'cash',spec.reserve,'confirmed',ok,
            f'return {row["full_base_total_return"]:.2%}, DD {row["full_base_max_drawdown"]:.2%}',flush=True)
    audit=[]
    audited=[s for s in specs if s.identity in locked]+[Refinement(blend='slow',top_n=15)]
    for scenario in ['delay','exclude_DELTA','exclude_THAI','phase10']:
        p=Panel(panel.frames,panel.exclusions|{scenario.removeprefix('exclude_')}) if scenario.startswith('exclude_') else panel
        f=RefinementFactory(p)
        for period in ['full','recent']:
            stage=scenario+'_'+period+'_base'
            reference=evaluate(Refinement(),stage,p,f,scenario)
            for s in audited:
                r=evaluate(s,stage,p,f,scenario)
                audit.append({'candidate':s.identity,'scenario':scenario,'period':period,**r,
                    'incumbent_cagr':reference['cagr'],'incumbent_max_drawdown':reference['max_drawdown'],
                    'incumbent_total_return':reference['total_return'],
                    'cagr_gain':r['cagr']-reference['cagr'],
                    'drawdown_gain':r['max_drawdown']-reference['max_drawdown']})
        print('Audited',scenario,flush=True)
    audit=pd.DataFrame(audit);audit.to_csv(FOLDER/'sensitivity_results.csv',index=False)
    passed=audit[audit.period.eq('full')].assign(passed=lambda d:(d.cagr_gain>0)&(d.drawdown_gain>0)).groupby('candidate').passed.all()
    for row in rows:
        row['audit_pass']=bool(passed.get(row['candidate'],False))
        row['status']=('qualified' if row['confirmed'] and row['audit_pass'] else
            'rejected_screen' if not row['screen_pass'] else
            'rejected_confirmation' if not row['confirmed'] else 'rejected_sensitivity')
    results=pd.DataFrame(rows).sort_values('selection_score',ascending=False)
    eligible=results[results.status.eq('qualified')]
    if len(eligible):results.loc[results.candidate.eq(eligible.iloc[0].candidate),'status']='selected'
    results.to_csv(FOLDER/'all_candidates.csv',index=False)
    results[results.status.eq('selected')].to_csv(FOLDER/'selected.csv',index=False)
    reg.export()
    print(results[['candidate','screen_pass','confirmed','audit_pass','status']].to_string(index=False),flush=True)


if __name__=='__main__':main()
