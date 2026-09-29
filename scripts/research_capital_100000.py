"""Declared 152-recipe capital-context search, preserving all failures."""
from dataclasses import replace
import hashlib
import json
import numpy as np
import pandas as pd
from research.portfolio import ROOT, Panel, FeeSchedule
from research.registry import Registry
from research.small_capital import SmallSpec, LotData, LotExecution, simulate_lots, price_only_basket
from research.capital_search import CapitalRecipe, rank_features

OUT = ROOT / 'reports/capital_100000_20260929'


def load_panels():
    original = Panel.load()
    index = pd.read_csv(ROOT/'data/indices/set100_tradingview_daily.csv', index_col='date', parse_dates=True).close
    dates = index.loc[original.dates[0]:original.dates[-1]].index
    frames = {s: f.reindex(dates) for s, f in original.frames.items()}
    excluded = original.exclusions | {'THAI'}
    complex_names = {s for s, f in original.frames.items()
                     if any(not np.isclose(x, round(x)) for x in f.stock_splits[f.stock_splits.ne(0)])}
    panels = {'base': Panel(frames, excluded, original.source_hashes),
              'exclude_top3': Panel(frames, excluded | {'DELTA', 'RCL', 'KCE'}, original.source_hashes),
              'exclude_complex_actions': Panel(frames, excluded | complex_names | {'SCB','GULF','STECON','TIDLOR'}, original.source_hashes)}
    return panels, index


def main():
    OUT.mkdir(exist_ok=True, parents=True)
    plan = json.loads((ROOT/'configs/capital_100000_plan.json').read_text())
    costs = json.loads((ROOT/'configs/thai_trading_costs.json').read_text())
    ledger_path = ROOT/'research/experiments/STRATEGY_LEDGER.csv'
    ledger = pd.read_csv(ledger_path)
    registry = Registry(ROOT/'research/experiments')
    panels, index = load_panels()
    data = {k: LotData(p) for k, p in panels.items()}
    features = {k: rank_features(p) for k, p in panels.items()}
    recipes = [CapitalRecipe(SmallSpec(top_n=n, rebalance=r, daily_exit=e,
                 reserve=plan['reserve'], rank_buffer=plan['rank_buffer']), mode)
               for mode in plan['rankings'] for n in plan['holdings']
               for r in plan['rebalance_sessions'] for e in plan['daily_market_exit']]
    recipes += [CapitalRecipe(SmallSpec(top_n=15, reserve=.05, affordability_filter=False)),
                CapitalRecipe(SmallSpec(top_n=15, reserve=.10))]
    by_id = {r.identity: r for r in recipes}
    assert len(by_id) == 152
    files = ['configs/capital_100000_plan.json','configs/thai_trading_costs.json',
             'research/capital_search.py','research/small_capital.py','research/candidates.py',
             'research/portfolio.py','scripts/research_capital_100000.py','data/indices/set100_tradingview_daily.csv']
    hashes = {f: hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}
    context = 'capital100k_' + hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()[:16]
    manifest = {'context': context, 'plan': plan, 'code_hashes': hashes,
                'price_hashes': panels['base'].source_hashes,
                'existing_recipe_ids': sorted(set(by_id) & set(ledger.candidate)),
                'recipes': {k: r.parameters for k, r in by_id.items()}}
    existing = OUT/'manifest.json'
    if existing.exists() and json.loads(existing.read_text())['context'] != context:
        raise ValueError('Changed run definition: preserve this report; use a new directory')
    existing.write_text(json.dumps(manifest, indent=2))
    rows = []; benchmarks = {}

    def evaluate(recipe, scenario, period):
        key = scenario if scenario in data else 'base'
        fee = FeeSchedule(**costs['stress' if scenario == 'higher_cost' else 'base'])
        if scenario == 'minimum_fee': fee = replace(fee, minimum_daily_commission_thb=50)
        x = LotExecution(windows=('morning',) if scenario == 'morning_only' else
                         ('close',) if scenario == 'close_only' else ('morning','close'),
                         extra_delay=int(scenario == 'delay_one'),
                         phase=recipe.sizing.rebalance//2 if scenario == 'phase_half' else 0,
                         missed_fills=scenario == 'missed_fills')
        start = plan['full_start'] if period == 'full' else plan['recent_start']
        bk = (scenario, period)
        if bk not in benchmarks:
            b, bc = price_only_basket(data[key], start, plan['end'], fee, plan['capital_thb'])
            benchmarks[bk] = b
            if scenario == 'base': bc.to_csv(OUT/f'benchmark_{period}.csv', index_label='date', header=['equity'])
        b = benchmarks[bk]; stage = scenario+'_'+period
        result = registry.get(context, recipe.identity, stage)
        if result is None:
            result, curve, fills, daily = simulate_lots(data[key], features[key][recipe.ranking], recipe.sizing,
                start, plan['end'], fee, plan['capital_thb'], x, details=scenario == 'base')
            result.update(scenario=scenario, period=period, benchmark_cagr=b['cagr'],
                benchmark_total_return=b['total_return'], benchmark_drawdown=b['max_drawdown'],
                excess_cagr=result['cagr']-b['cagr'])
            folder = OUT/recipe.identity; folder.mkdir(exist_ok=True)
            curve.to_csv(folder/f'{stage}_equity.csv', index_label='date', header=['equity'])
            if scenario == 'base':
                fills.to_csv(folder/f'{stage}_fills.csv', index=False)
                daily.to_csv(folder/f'{stage}_daily.csv')
            registry.put(context, recipe.identity, stage, recipe.parameters, result)
        rows.append({'candidate': recipe.identity, 'ranking': recipe.ranking,
                     'top_n': recipe.sizing.top_n, 'rebalance': recipe.sizing.rebalance,
                     'daily_exit': recipe.sizing.daily_exit, **result})

    for count, recipe in enumerate(recipes, 1):
        for period in ('full','recent'): evaluate(recipe, 'base', period)
        if count % 10 == 0 or count == len(recipes):
            pd.DataFrame(rows).to_csv(OUT/'all_results.csv', index=False)
            print(f'Base recipes {count}/{len(recipes)}', flush=True)
    base = pd.DataFrame(rows)
    full = base[base.period.eq('full')].set_index('candidate')
    gate = base.assign(pass_case=(base.excess_cagr > 0) & (base.max_drawdown >= plan['screen_drawdown']))
    passes = gate.groupby('candidate').pass_case.all()
    short = []
    for mode in plan['rankings']:
        group = full[full.ranking.eq(mode)]
        eligible = group.loc[passes.reindex(group.index)]
        short.append((eligible if len(eligible) else group).total_return.idxmax())
    short += list(full.nlargest(2, 'total_return').index) + plan['reference_ids']
    short = list(dict.fromkeys(short))
    (OUT/'shortlist.json').write_text(json.dumps({'candidates': short, 'selection': plan['shortlist']}, indent=2))
    print('FROZEN SHORTLIST', short, flush=True)
    print(full.nlargest(8,'total_return')[['ranking','top_n','rebalance','daily_exit','total_return','max_drawdown']].to_string(), flush=True)
    for candidate in short:
        for scenario in plan['scenarios']:
            for period in ('full','recent'): evaluate(by_id[candidate], scenario, period)
        pd.DataFrame(rows).to_csv(OUT/'all_results.csv', index=False)
        print('Sensitivities complete', candidate, flush=True)
    results = pd.DataFrame(rows); scores = []
    for candidate in short:
        g = results[results.candidate.eq(candidate)]
        failed = g[(g.excess_cagr <= 0) | (g.max_drawdown < plan['screen_drawdown'])]
        scores.append({'candidate': candidate, 'passes': bool(failed.empty),
                       'worst_full_cagr': float(g[g.period.eq('full')].cagr.min()),
                       'worst_drawdown': float(g.max_drawdown.min()),
                       'failed_cases': failed[['scenario','period','excess_cagr','max_drawdown']].to_dict('records')})
    passed = [s for s in scores if s['passes']]
    chosen = max(passed or scores, key=lambda s: (s['worst_full_cagr'], s['worst_drawdown']))
    selection = {'candidate': chosen['candidate'], 'parameters': by_id[chosen['candidate']].parameters,
                 'capital_thb': plan['capital_thb'], 'research_gate_passed': bool(passed),
                 'live_ready': False, 'scores': scores,
                 'highest_base_return_candidate': full.total_return.idxmax(),
                 'target_total_return': plan['target_total_return']}
    (OUT/'selection.json').write_text(json.dumps(selection, indent=2))
    additions = []
    for recipe in recipes:
        if recipe.identity in set(ledger.candidate): continue
        r = full.loc[recipe.identity]
        additions.append({'candidate': recipe.identity, 'family': recipe.parameters['family'],
            'parameters': json.dumps(recipe.parameters, sort_keys=True),
            'rule': 'Whole-lot affordable ranking, shared SMA200 market/stock filter and positive skipped-year return',
            'status': 'selected_experimental_100000' if recipe.identity == chosen['candidate'] else 'not_selected_100000',
            'reason': json.dumps(next((s for s in scores if s['candidate'] == recipe.identity), {'reason':'Not shortlisted by declared screen'})),
            'batch':'capital_100000_20260929','report':str(OUT.relative_to(ROOT)),
            **{'full_base_'+k:r[k] for k in ['total_return','cagr','max_drawdown','excess_cagr','fills']}})
    if additions: pd.concat([ledger,pd.DataFrame(additions)], ignore_index=True).to_csv(ledger_path,index=False)
    registry.export()
    print('SELECTION', json.dumps(selection), flush=True)


if __name__ == '__main__': main()
