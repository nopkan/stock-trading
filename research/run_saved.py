"""Reproduce retained strategies and benchmark with explicit Thai trading costs."""
import argparse
from dataclasses import asdict
import hashlib
import importlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from research.portfolio import Panel, FeeSchedule, ROOT, benchmark, simulate
from research.registry import Registry
from research.candidates import Spec


def load_panel(data_dir, symbols):
    frames,hashes={},{}
    for symbol in symbols:
        path=data_dir/f'{symbol}.csv'
        frame=pd.read_csv(path,parse_dates=['date']).set_index('date')
        columns=['adj_open','adj_close','adj_high','adj_low','close','volume']
        if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
            raise ValueError(f'{symbol}: dates must be unique and sorted')
        if not np.isfinite(frame[columns]).all().all() or (frame[columns[:-1]]<=0).any().any() or (frame.volume<0).any():
            raise ValueError(f'{symbol}: invalid market data')
        frames[symbol]=frame
        hashes[symbol]=hashlib.sha256(path.read_bytes()).hexdigest()
    exclusions=set(json.loads((ROOT/'configs/data_exclusions.json').read_text())) & set(symbols)
    return Panel(frames,exclusions,hashes)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--strategy',default='all',help='Active portfolio module name, custom generate_targets module, or all')
    p.add_argument('--params',default='{}')
    p.add_argument('--start',default='2017-01-01')
    p.add_argument('--end',default='2026-09-28')
    p.add_argument('--cost-profile',choices=['base','stress'],default='base')
    p.add_argument('--capital',type=float,default=1_000_000)
    p.add_argument('--symbols',nargs='+')
    p.add_argument('--universe',type=Path,default=ROOT/'data/universe/set100_snapshot.csv')
    p.add_argument('--data-dir',type=Path,default=ROOT/'data/prices')
    p.add_argument('--output',type=Path,default=ROOT/'reports/retained_latest')
    p.add_argument('--accept-snapshot-bias',action='store_true')
    a=p.parse_args()
    if not a.accept_snapshot_bias:p.error('Fixed current membership is biased; pass --accept-snapshot-bias for exploratory runs.')
    if pd.Timestamp(a.start)>=pd.Timestamp(a.end):p.error('start must precede end')
    if not np.isfinite(a.capital) or a.capital<=0:p.error('capital must be positive')
    parameters=json.loads(a.params)
    if not isinstance(parameters,dict) or (a.strategy=='all' and parameters):p.error('--params requires one strategy and a JSON object')
    active=json.loads((ROOT/'strategy/active.json').read_text())
    names=[s['module'] for s in active] if a.strategy=='all' else [a.strategy]
    if any(not name.isidentifier() or name.startswith('_') for name in names):p.error('Invalid strategy module')
    symbols=a.symbols or pd.read_csv(a.universe).symbol.tolist()
    if not symbols or len(set(symbols))!=len(symbols):p.error('Symbol list must be nonempty and unique')
    panel=load_panel(a.data_dir,symbols)
    config=json.loads((ROOT/'configs/thai_trading_costs.json').read_text())
    costs=FeeSchedule(**config[a.cost_profile])
    registry=Registry(ROOT/'research/experiments')
    code_hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['research/portfolio.py','research/candidates.py','research/run_saved.py']}
    modules={}
    for name in names:
        try:modules[name]=importlib.import_module('strategy.'+name)
        except ModuleNotFoundError:
            p.error(f'{name} is unavailable. Rejected originals are recorded in research/experiments/legacy_strategy_sources.json; see strategy/active.json.')
        for dependency in getattr(modules[name],'RESEARCH_DEPENDENCIES',[]):
            code_hashes[dependency]=hashlib.sha256((ROOT/dependency).read_bytes()).hexdigest()
    context='manual_'+hashlib.sha256(json.dumps({'prices':panel.source_hashes,'code':code_hashes,
        'costs':costs.__dict__,'capital':a.capital,'start':a.start,'end':a.end},sort_keys=True).encode()).hexdigest()[:16]
    a.output.mkdir(parents=True,exist_ok=True)
    if (a.output/'run.json').exists():p.error('Output already contains a run. Choose a new output directory to preserve experiments.')
    reference,curve=benchmark(panel,a.start,a.end,costs,a.capital)
    if registry.get(context,'benchmark','manual_run') is None:
        registry.put(context,'benchmark','manual_run',{'family':'buy_hold'},
                     {**reference,'report':str(a.output),'reason':'Explicit saved-strategy run or reproduction verification'})
    curves={'buy_hold':curve}
    comparison=[{'strategy':'buy_hold',**reference}]
    settings={}
    source_hashes={}
    for name in names:
        module=modules[name]
        if not hasattr(module,'generate_targets'):p.error(f'{name} is a single-stock module; use python -m backtest.single_stock')
        params={**module.DEFAULTS,**parameters}
        settings[name]=params
        source_hashes[name]=hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
        targets=module.generate_targets(panel,**params)
        result,curve,trades=simulate(panel,targets,a.start,a.end,costs,a.capital,details=True)
        result['excess_cagr']=result['cagr']-reference['cagr']
        result['excess_total_return']=result['total_return']-reference['total_return']
        if hasattr(module,'SPEC_CLASS'):
            spec=module.SPEC_CLASS(**params)
            candidate=spec.identity
            definition=asdict(spec)
        elif hasattr(module,'FAMILY'):
            spec=Spec(family=module.FAMILY,**params)
            candidate=spec.identity
            definition=json.loads(spec.canonical)
        else:
            definition={'module':name,'parameters':params,'source_sha256':source_hashes[name]}
            candidate=hashlib.sha256(json.dumps(definition,sort_keys=True).encode()).hexdigest()[:16]
        if registry.get(context,candidate,'manual_run') is None:
            registry.put(context,candidate,'manual_run',definition,
                         {**result,'report':str(a.output),'reason':'Explicit saved-strategy run or reproduction verification'})
        comparison.append({'strategy':name,**result})
        curves[name]=curve
        trades.to_csv(a.output/f'{name}_fills.csv',index=False)
        rows=np.flatnonzero(~np.isnan(targets).all(axis=1))
        weights=pd.DataFrame(targets[rows],index=panel.dates[rows],columns=panel.symbols)
        weights.loc[a.start:a.end].rename_axis('decision_date').to_csv(a.output/f'{name}_targets.csv')
    table=pd.DataFrame(comparison)
    table.to_csv(a.output/'comparison.csv',index=False)
    pd.DataFrame(curves).rename_axis('date').to_csv(a.output/'equity.csv')
    (a.output/'run.json').write_text(json.dumps({'created_at':datetime.now(timezone.utc).isoformat(),
        'start':a.start,'end':a.end,'symbols':symbols,'exclusions':sorted(panel.exclusions),
        'parameters':settings,'cost_profile':a.cost_profile,'costs':costs.__dict__,
        'fee_rate':costs.rate,'capital_thb':a.capital,'price_sha256':panel.source_hashes,
        'strategy_sha256':source_hashes,'portfolio_sha256':hashlib.sha256((ROOT/'research/portfolio.py').read_bytes()).hexdigest(),
        'research_source_sha256':code_hashes,
        'candidates_sha256':hashlib.sha256((ROOT/'research/candidates.py').read_bytes()).hexdigest(),
        'bias':'Retrospective current SET100 snapshot; not point-in-time membership or official SET100 index.',
        'execution':'Fractional adjusted units, previous close target, next observed session open; unavailable orders skipped until next rebalance.',
        'end_positions':'Marked to close, not liquidated; fees exclude hypothetical final exit.'},indent=2))
    print('EXPLORATORY RETROSPECTIVE RESULTS — fixed membership, fractional adjusted units')
    print(f'Fee per side {costs.rate:.5%}; slippage {costs.slippage_bps/100:.3f}%; excluded {sorted(panel.exclusions)}')
    print(table.to_string(index=False,float_format=lambda v:f'{v:.4f}'))
    print(a.output.resolve())
    registry.export()


if __name__=='__main__':main()
