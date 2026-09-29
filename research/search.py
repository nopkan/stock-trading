"""Predeclared chronological search; resume skips already recorded evaluations.

Discovery: 2017-2020. Validation: 2021-2023. Lock up to 2 distinct parameter
variants per family from discovery+validation before evaluating 2024-2026.
The latter is previously seen for legacy strategies, hence not a virgin holdout.
"""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

from research.candidates import Factory, Spec, RULES, initial_grid
from research.portfolio import Panel, FeeSchedule, ROOT, benchmark, simulate
from research.registry import Registry

PERIODS = {'discovery':('2017-01-01','2020-12-31'), 'validation':('2021-01-01','2023-12-31'),
           'confirmation':('2024-01-01','2026-09-28'), 'full':('2017-01-01','2026-09-28')}


def fingerprint(panel):
    source = {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
        [ROOT/'research/portfolio.py',ROOT/'research/candidates.py',ROOT/'research/search.py',
         ROOT/'configs/thai_trading_costs.json',ROOT/'configs/data_exclusions.json']}
    payload = {'prices':panel.source_hashes,'source':source,'periods':PERIODS}
    return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()[:16],payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder',type=Path,default=ROOT/'reports/strategy_search_20260929')
    parser.add_argument('--stage',choices=['screen','confirm','report'],default='screen')
    args=parser.parse_args()
    args.folder.mkdir(parents=True,exist_ok=True)
    panel=Panel.load()
    context,payload=fingerprint(panel)
    registry=Registry(ROOT/'research/experiments')
    config=json.loads((ROOT/'configs/thai_trading_costs.json').read_text())
    base,stress=FeeSchedule(**config['base']),FeeSchedule(**config['stress'])
    capital=config['initial_capital_thb']
    grid=initial_grid()
    plan_path=args.folder/'search_plan.json'
    plan={'context':context,'created_at':datetime.now(timezone.utc).isoformat(),
        'data_and_code':payload,'periods':PERIODS,'candidates':[asdict(s) for s in grid],
        'selection':'Require positive benchmark excess CAGR and no worse drawdown in discovery AND validation. Lock top two per family by minimum discovery/validation excess CAGR. Confirm unchanged. Select maximum one per family.',
        'qualification':'Beat benchmark full and confirmation at base AND stress costs; drawdown no worse than benchmark; same original discovery+validation pass. Five distinct rule families sought. All findings remain retrospective fixed-universe research.',
        'benchmark':'Original equal-initial-allocation buy-and-hold, same 100 names, BANPU cash.',
        'capital_thb':capital,'costs':config,'holdout_status':'2024-2026 previously examined for legacy defaults; not virgin holdout'}
    if plan_path.exists():
        saved=json.loads(plan_path.read_text())
        if saved['context'] != context:
            raise RuntimeError('Code/data/costs changed. Use a new --folder; preserve the original plan.')
    else:
        plan_path.write_text(json.dumps(plan,indent=2))
    baselines={}
    for period,(start,end) in PERIODS.items():
        for profile,cost in [('base',base),('stress',stress)]:
            key=f'{period}_{profile}'
            result=registry.get(context,'benchmark',key)
            if result is None:
                result,curve=benchmark(panel,start,end,cost,capital)
                registry.put(context,'benchmark',key,{'family':'buy_hold'},result)
                curve.rename('equity').rename_axis('date').to_csv(args.folder/f'benchmark_{key}.csv')
            baselines[key]=result
    (args.folder/'benchmarks.json').write_text(json.dumps(baselines,indent=2))
    factory=Factory(panel)

    def run(spec,stage,targets=None,save=False):
        old=registry.get(context,spec.identity,stage)
        if old is not None:
            return old
        period,profile=stage.rsplit('_',1)
        cost=base if profile=='base' else stress
        result,curve,trades=simulate(panel,factory.targets(spec) if targets is None else targets,
            *PERIODS[period],cost,capital,details=save)
        reference=baselines[stage]
        result.update(excess_cagr=result['cagr']-reference['cagr'],
                      excess_total_return=result['total_return']-reference['total_return'],
                      drawdown_better=result['max_drawdown']>=reference['max_drawdown'])
        registry.put(context,spec.identity,stage,asdict(spec),result)
        if save:
            folder=args.folder/spec.identity
            folder.mkdir(exist_ok=True)
            curve.rename('equity').rename_axis('date').to_csv(folder/f'{stage}_equity.csv')
            trades.to_csv(folder/f'{stage}_fills.csv',index=False)
        return result

    if args.stage=='screen':
        for number,spec in enumerate(grid,1):
            targets=None
            if registry.get(context,spec.identity,'discovery_base') is None or registry.get(context,spec.identity,'validation_base') is None:
                targets=factory.targets(spec)
            discovery=run(spec,'discovery_base',targets)
            validation=run(spec,'validation_base',targets)
            if number%12==0 or number==len(grid):
                print(f'Screened {number}/{len(grid)} | {spec.family}',flush=True)
                registry.export()
    screens=[]
    for spec in grid:
        d=registry.get(context,spec.identity,'discovery_base')
        v=registry.get(context,spec.identity,'validation_base')
        if d is None or v is None: continue
        passed=d['excess_cagr']>0 and v['excess_cagr']>0 and d['drawdown_better'] and v['drawdown_better']
        screens.append({'candidate':spec.identity,**asdict(spec),'discovery_excess_cagr':d['excess_cagr'],
            'validation_excess_cagr':v['excess_cagr'],'screen_pass':passed,
            'selection_score':min(d['excess_cagr'],v['excess_cagr'])})
    screen=pd.DataFrame(screens)
    if screen.empty:
        raise RuntimeError('Run --stage screen first')
    screen.to_csv(args.folder/'screen_results.csv',index=False)
    shortlist_path=args.folder/'locked_shortlist.json'
    if not shortlist_path.exists():
        if len(screen)!=len(grid):
            raise RuntimeError('Incomplete screen; resume before locking shortlist')
        locked=screen.loc[screen.screen_pass].sort_values('selection_score',ascending=False).groupby('family').head(2)
        shortlist_path.write_text(json.dumps({'locked_at':datetime.now(timezone.utc).isoformat(),'context':context,
            'candidate_ids':locked.candidate.tolist()},indent=2))
    locked_ids=json.loads(shortlist_path.read_text())['candidate_ids']
    print(f'Screen pass: {int(screen.screen_pass.sum())}/{len(screen)}; locked candidates: {len(locked_ids)}',flush=True)
    if args.stage=='confirm':
        for spec in [s for s in grid if s.identity in locked_ids]:
            targets=factory.targets(spec)
            for stage in ['confirmation_base','confirmation_stress','full_base','full_stress']:
                r=run(spec,stage,targets,save=True)
                print(f'{spec.family} {spec.identity} {stage} CAGR {r["cagr"]:.2%} excess {r["excess_cagr"]:.2%}',flush=True)
            registry.export()
    conclusions=[]
    for spec in grid:
        s=screen.loc[screen.candidate.eq(spec.identity)]
        if s.empty: continue
        row=s.iloc[0].to_dict()
        results={stage:registry.get(context,spec.identity,stage) for stage in ['confirmation_base','confirmation_stress','full_base','full_stress']}
        qualified=bool(row['screen_pass']) and all(r and r['excess_cagr']>0 and r['drawdown_better'] for r in results.values())
        for stage,r in results.items():
            if r:
                row.update({stage+'_'+k:r[k] for k in ['total_return','cagr','max_drawdown','excess_cagr','sharpe_rf0','fills','mean_exposure']})
        row['qualified']=qualified
        row['status']='qualified_research_candidate' if qualified else ('rejected_screen' if not row['screen_pass'] else ('not_shortlisted' if spec.identity not in locked_ids else 'confirmation_failed_or_pending'))
        row['rule']=RULES[spec.family]
        conclusions.append(row)
    conclusions=pd.DataFrame(conclusions)
    conclusions.to_csv(args.folder/'all_candidates.csv',index=False)
    q=conclusions.loc[conclusions.qualified]
    if not q.empty:
        q=q.sort_values('selection_score',ascending=False).groupby('family').head(1).head(5)
    q.to_csv(args.folder/'selected_five.csv',index=False)
    registry.export()
    print(f'Qualifying distinct families retained: {len(q)}',flush=True)
    print(q[['candidate','family']].to_string(index=False) if len(q) else 'None confirmed yet',flush=True)


if __name__=='__main__': main()
