"""Frozen refinement search against the incumbent; no unseen holdout exists.

Run screen first; lock a shortlist from 2017-2023, then run confirm unchanged.
"""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import pandas as pd
from research.portfolio import ROOT, Panel, FeeSchedule, simulate, benchmark
from research.refinements import Refinement, RefinementFactory, refinement_grid
from research.registry import Registry

PERIODS={'discovery':('2017-01-01','2020-12-31'),
    'validation':('2021-01-01','2023-12-31'),
    'development':('2017-01-01','2023-12-31'),
    'recent':('2024-01-01','2026-09-28'),
    'full':('2017-01-01','2026-09-28')}
FOLDER=ROOT/'reports/momentum_refinement_20260929'
INCUMBENT='f4f96d173a82b60a'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=['screen','confirm'],required=True)
    args=parser.parse_args()
    FOLDER.mkdir(parents=True,exist_ok=True)
    panel=Panel.load()
    config=json.loads((ROOT/'configs/thai_trading_costs.json').read_text())
    costs={k:FeeSchedule(**config[k]) for k in ['base','stress']}
    hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
        ['research/portfolio.py','research/candidates.py','research/refinements.py',
         'research/refine_search.py','configs/thai_trading_costs.json','configs/data_exclusions.json']}
    source={'prices':panel.source_hashes,'code':hashes}
    context='refine_'+hashlib.sha256(json.dumps(source,sort_keys=True).encode()).hexdigest()[:16]
    registry=Registry(ROOT/'research/experiments')
    grid=refinement_grid()
    plan={'context':context,'created_at':datetime.now(timezone.utc).isoformat(),
        'source':source,'periods':PERIODS,'costs':config,'incumbent':INCUMBENT,
        'candidates':[{'group':g,'candidate':s.identity,'parameters':asdict(s)} for g,s in grid],
        'screen':'Higher CAGR and smaller maximum drawdown than incumbent in combined development (2017-2023); CAGR no more than 2 percentage points below incumbent in either discovery or validation. Rank by development CAGR improvement plus drawdown improvement; lock up to 12, at most 3 per experiment group.',
        'confirm':'Require higher CAGR and smaller maximum drawdown than incumbent over full history at BOTH base and stress costs. Recent CAGR may trail incumbent by at most 2 percentage points, with no worse recent drawdown, at BOTH cost profiles. Require positive recent CAGR excess vs buy-and-hold. Report exact comparisons, including any period of underperformance.',
        'audit':'Evaluate all shortlisted variants with full and recent +1 session execution delay, DELTA exclusion, THAI exclusion and +10-session rebalance phase. Primary comparator receives the identical perturbation. Audit passes if full CAGR stays higher and drawdown smaller than incumbent in every scenario; recent comparisons reported descriptively. Rank eligible candidates by frozen development score.',
        'retest_reason':'User-requested challenge against retained multi-horizon winner; incumbent repeated as comparator under identical data and costs.',
        'holdout':'All dates previously inspected. Retrospective refinement only; future dates after 2026-09-28 remain untouched. Fixed current SET100 snapshot, not official SET100 total-return index.'}
    path=FOLDER/'search_plan.json'
    if path.exists():
        if json.loads(path.read_text())['context']!=context:
            raise RuntimeError('Frozen code/data changed. Preserve this run and use a new folder.')
    else:
        path.write_text(json.dumps(plan,indent=2))
    factory=RefinementFactory(panel)
    incumbent_targets=factory.targets(Refinement())
    def run(spec,stage,targets=None,save=False,incumbent=False):
        candidate=INCUMBENT if incumbent else spec.identity
        old=registry.get(context,candidate,stage)
        if old is not None:
            return old
        period,profile=stage.rsplit('_',1)
        result,curve,fills=simulate(panel,targets if targets is not None else factory.targets(spec),
            *PERIODS[period],costs[profile],config['initial_capital_thb'],details=save)
        registry.put(context,candidate,stage,asdict(spec),result)
        if save:
            folder=FOLDER/candidate;folder.mkdir(exist_ok=True)
            curve.rename('equity').rename_axis('date').to_csv(folder/f'{stage}_equity.csv')
            fills.to_csv(folder/f'{stage}_fills.csv',index=False)
        return result
    baseline={}
    for period in PERIODS:
        for profile in ['base','stress']:
            stage=f'{period}_{profile}'
            baseline[stage]=run(Refinement(),stage,incumbent_targets,save=True,incumbent=True)
            if registry.get(context,'benchmark',stage) is None:
                r,e=benchmark(panel,*PERIODS[period],costs[profile],config['initial_capital_thb'])
                registry.put(context,'benchmark',stage,{'family':'buy_hold'},r)
                e.rename('equity').rename_axis('date').to_csv(FOLDER/f'benchmark_{stage}.csv')
    (FOLDER/'incumbent.json').write_text(json.dumps(baseline,indent=2))
    if args.stage=='screen':
        for i,(group,spec) in enumerate(grid,1):
            targets=factory.targets(spec)
            for period in ['discovery','validation','development']:
                run(spec,period+'_base',targets)
            if i%15==0 or i==len(grid):
                print(f'Screened {i}/{len(grid)} refinements',flush=True)
    rows=[]
    for group,spec in grid:
        results={p:registry.get(context,spec.identity,p+'_base') for p in ['discovery','validation','development']}
        if any(r is None for r in results.values()):
            raise RuntimeError('Screen incomplete; resume it first')
        d=results['development'];b=baseline['development_base']
        gain=d['cagr']-b['cagr'];dd=d['max_drawdown']-b['max_drawdown']
        passed=gain>0 and dd>0 and all(results[p]['cagr']>=baseline[p+'_base']['cagr']-.02 for p in ['discovery','validation'])
        row={'candidate':spec.identity,'group':group,'parameters':json.dumps(asdict(spec),sort_keys=True),
            'screen_pass':passed,'selection_score':gain+dd,'development_cagr_gain':gain,'development_drawdown_gain':dd}
        for period,r in results.items():
            row.update({period+'_'+k:v for k,v in r.items()})
        rows.append(row)
    screen=pd.DataFrame(rows)
    screen.to_csv(FOLDER/'screen_results.csv',index=False)
    lock=FOLDER/'locked_shortlist.json'
    if not lock.exists():
        best=screen[screen.screen_pass].sort_values('selection_score',ascending=False).groupby('group',sort=False).head(3).head(12)
        lock.write_text(json.dumps({'locked_at':datetime.now(timezone.utc).isoformat(),
            'context':context,'candidate_ids':best.candidate.tolist()},indent=2))
    ids=json.loads(lock.read_text())['candidate_ids']
    print('Screen passed:',int(screen.screen_pass.sum()),'Locked:',len(ids),flush=True)
    if args.stage=='confirm':
        for group,spec in grid:
            if spec.identity not in ids:continue
            targets=factory.targets(spec)
            for stage in ['recent_base','recent_stress','full_base','full_stress']:
                r=run(spec,stage,targets,save=True)
                print(spec.identity,stage,f'return {r["total_return"]:.2%}, drawdown {r["max_drawdown"]:.2%}',flush=True)
    for row in rows:
        candidate=row['candidate'];confirmed=True
        for stage in ['recent_base','recent_stress','full_base','full_stress']:
            r=registry.get(context,candidate,stage)
            if r is None:confirmed=False;continue
            row.update({stage+'_'+k:v for k,v in r.items()})
            b=baseline[stage]
            confirmed &= r['max_drawdown']>=b['max_drawdown'] and r['cagr']>b['cagr']-(.02 if stage.startswith('recent') else 0)
            if stage.startswith('recent'):
                confirmed &= r['cagr']>registry.get(context,'benchmark',stage)['cagr']
        row['confirmed']=bool(confirmed and row['screen_pass'])
        row['status']='confirmed_pending_audit' if row['confirmed'] else ('rejected_screen' if not row['screen_pass'] else ('not_shortlisted' if candidate not in ids else 'confirmation_failed_or_pending'))
    pd.DataFrame(rows).to_csv(FOLDER/'all_candidates.csv',index=False)
    registry.export()
    print(pd.DataFrame(rows).query('confirmed')[['candidate','group','full_base_total_return','full_base_max_drawdown']].to_string(index=False) if any(r['confirmed'] for r in rows) else 'No confirmed candidate yet',flush=True)


if __name__=='__main__':main()
