"""Run the declared, bounded auction-readiness experiment and preserve failures."""
from dataclasses import asdict, replace
from pathlib import Path
import argparse
import hashlib
import json
import numpy as np
import pandas as pd
from research.portfolio import ROOT, Panel, FeeSchedule, benchmark
from research.auction_research import AuctionRecipe, ProxyExecution, targets, simulate_proxy
from research.registry import Registry

OUT=ROOT/'reports/auction_readiness_20260929'


def main():
    global OUT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=OUT)
    parser.add_argument('--plan',type=Path,default=ROOT/'configs/auction_research_plan.json')
    args=parser.parse_args();OUT=args.output
    OUT.mkdir(parents=True,exist_ok=True)
    plan=json.loads(args.plan.read_text())
    costs=json.loads((ROOT/'configs/thai_trading_costs.json').read_text())
    original=Panel.load()
    index=pd.read_csv(ROOT/'data/indices/set100_tradingview_daily.csv',index_col='date',parse_dates=True).close
    frames={s:f.loc[f.index.intersection(index.index)] for s,f in original.frames.items()}
    p=Panel(frames,set(plan['common_exclusions'])|original.exclusions,original.source_hashes)
    hashes={file:hashlib.sha256((ROOT/file).read_bytes()).hexdigest() for file in [
        'research/auction_research.py','research/refinements.py','research/candidates.py','research/portfolio.py',
        'scripts/research_auction_candidate.py',str(args.plan.relative_to(ROOT)),'configs/thai_trading_costs.json',
        'data/indices/set100_tradingview_daily.csv']}
    fingerprint={'source':hashes,'prices':original.source_hashes}
    context='auction_proxy_'+hashlib.sha256(json.dumps(fingerprint,sort_keys=True).encode()).hexdigest()[:16]
    manifest={'context':context,'reason':plan['reason'],'plan':plan,'hashes':fingerprint,
        'missing_stock_sessions':[str(d.date()) for d in index.loc[p.dates[0]:p.dates[-1]].index.difference(p.dates)],
        'benchmark':'Same-exclusion original equal-initial-sleeve buy-and-hold, with open-based sizing and immediate full fills. Benchmark is granted more favorable execution than the proxy strategy, intentionally a stricter return hurdle. Not a broker-executable auction benchmark.',
        'status':'daily_price_proxy_only_not_auction_validated'}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
    registry=Registry(ROOT/'research/experiments')
    recipes={r['name']:AuctionRecipe(**{k:v for k,v in r.items() if k!='name'}) for r in plan['candidate_recipes']}
    for name,r in recipes.items():print(name,r.identity,flush=True)
    rows=[]
    for name,recipe in recipes.items():
        for scenario in plan['predeclared_scenarios']:
            panel=p
            if scenario.startswith('exclude_'):
                panel=Panel(frames,p.exclusions|{scenario.split('_',1)[1]},original.source_hashes)
            fee=FeeSchedule(**costs['stress' if scenario=='higher_cost' else 'base'])
            phase=10 if scenario=='phase_10' else 0
            x=ProxyExecution(extra_delay=int(scenario=='extra_day_delay'),fill_fraction=.5 if scenario=='half_fills' else 1.,
                windows=('morning',) if scenario=='morning_only' else ('close',) if scenario=='close_only' else ('morning','close'))
            target=targets(panel,recipe,index,phase)
            for period,start in [('full','2017-01-04'),('recent','2024-01-01')]:
                stage=scenario+'_'+period
                saved=registry.get(context,recipe.identity,stage)
                if saved is None:
                    result,curve,fills=simulate_proxy(panel,target,start,'2026-09-28',fee,plan['capital_thb_provisional'],x,details=scenario=='base')
                    b,_=benchmark(panel,start,'2026-09-28',fee,plan['capital_thb_provisional'])
                    result.update(benchmark_cagr=b['cagr'],benchmark_total_return=b['total_return'],benchmark_drawdown=b['max_drawdown'],
                        excess_cagr=result['cagr']-b['cagr'],scenario=scenario,period=period)
                    registry.put(context,recipe.identity,stage,asdict(recipe),result)
                    if scenario in ['base','higher_cost']:
                        folder=OUT/recipe.identity;folder.mkdir(exist_ok=True)
                        curve.to_csv(folder/f'{stage}_equity.csv',index_label='date',header=['equity'])
                        if not fills.empty:fills.to_csv(folder/f'{stage}_fills.csv',index=False)
                else:result=saved
                rows.append({'name':name,'candidate':recipe.identity,**result})
        print('Audited',name,flush=True)
    results=pd.DataFrame(rows);results.to_csv(OUT/'all_results.csv',index=False)
    scores=[]
    for name,recipe in recipes.items():
        subset=results[results.name.eq(name)]
        full=subset[subset.period.eq('full')]
        passed=bool(subset.excess_cagr.gt(0).all() and subset.max_drawdown.ge(-.25).all())
        scores.append({'name':name,'candidate':recipe.identity,'passed_research_hurdle':passed,
            'min_full_cagr':full.cagr.min(),'worst_drawdown':subset.max_drawdown.min(),
            'failed_scenarios':subset.loc[subset.excess_cagr.le(0)|subset.max_drawdown.lt(-.25),['scenario','period','excess_cagr','max_drawdown']].to_dict('records')})
    eligible=[r for r in scores if plan.get('include_reference_for_selection',False) or r['name']!='reference_buffer5']
    passed=[r for r in eligible if r['passed_research_hurdle']]
    selected=sorted(passed or eligible,key=lambda r:(r['min_full_cagr'],r['worst_drawdown']),reverse=True)[0]
    chosen=recipes[selected['name']]
    selection={'candidate':chosen.identity,'name':selected['name'],'parameters':asdict(chosen),
               'research_gate_passed':bool(passed),'live_ready':False,'mode':'paper_only','scores':scores,
               'live_blockers':['Complete point-in-time membership and exiting/delisted histories unavailable',
                'Actual morning/afternoon/closing auction prices, volumes, indicative snapshots and eligibility unavailable',
                'Broker, capital and user risk preferences unconfirmed',
                'Historical real-share corporate actions, dividends and lot metadata not validated',
                'Fresh forward paper performance and broker fault/partial-fill reconciliation not observed']}
    (OUT/'selection.json').write_text(json.dumps(selection,indent=2))
    # Keep all new definitions and rejected results in the existing strategy ledger.
    ledger_path=ROOT/'research/experiments/STRATEGY_LEDGER.csv'
    ledger=pd.read_csv(ledger_path)
    additions=[]
    for score in scores:
        recipe=recipes[score['name']]
        if recipe.identity in set(ledger.candidate):continue
        subset=results[results.candidate.eq(recipe.identity)]
        row={'candidate':recipe.identity,'family':'auction_buffered_momentum','parameters':json.dumps(asdict(recipe),sort_keys=True),
            'rule':'Buffered multi-horizon momentum with predeclared risk-exit changes; see auction_readiness report',
            'status':'paper_candidate_not_live_ready' if recipe.identity==chosen.identity else 'not_selected_auction_audit',
            'reason':json.dumps(score['failed_scenarios']) or 'Bounded comparison', 'report':str(OUT.relative_to(ROOT)),
            'batch':'auction_readiness_20260929'}
        for stage,costscenario,period in [('full_base','base','full'),('full_stress','higher_cost','full'),('recent_base','base','recent')]:
            r=subset[subset.scenario.eq(costscenario)&subset.period.eq(period)].iloc[0]
            for metric in ['total_return','cagr','max_drawdown','excess_cagr','sharpe_rf0','fills']:
                row[stage+'_'+metric]=r[metric]
        additions.append(row)
    if additions:pd.concat([ledger,pd.DataFrame(additions)],ignore_index=True).to_csv(ledger_path,index=False)
    registry.export()
    print(results[results.scenario.eq('base')][['name','period','total_return','cagr','max_drawdown','excess_cagr']].to_string(index=False))
    print(json.dumps(selection,indent=2))


if __name__=='__main__':main()
