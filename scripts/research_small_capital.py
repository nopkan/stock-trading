"""Bounded THB30,000 study; writes all results and one frozen experimental pick."""
from dataclasses import asdict, replace
import json
import hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from research.portfolio import ROOT, Panel, FeeSchedule
from research.registry import Registry
from research.small_capital import SmallSpec, LotData, Features, LotExecution, simulate_lots, price_only_basket

OUT=ROOT/'reports/small_capital_30000_20260929'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    plan=json.loads((ROOT/'configs/small_capital_plan.json').read_text())
    costs=json.loads((ROOT/'configs/thai_trading_costs.json').read_text())
    original=Panel.load()
    index=pd.read_csv(ROOT/'data/indices/set100_tradingview_daily.csv',index_col='date',parse_dates=True).close
    calendar=index.loc[original.dates[0]:original.dates[-1]].index
    # Reindexing adds NaN observations, not fabricated tradable prices.
    frames={s:f.reindex(calendar) for s,f in original.frames.items()}
    complex_names={s for s,f in original.frames.items() if any(not np.isclose(x,round(x)) for x in f.stock_splits[f.stock_splits.ne(0)])}
    exclusions=set(plan['common_exclusions'])|original.exclusions
    common=Panel(frames,exclusions,original.source_hashes)
    panels={'base':common,'exclude_top3':Panel(frames,exclusions|{'DELTA','RCL','KCE'},original.source_hashes),
            'exclude_complex_actions':Panel(frames,exclusions|complex_names|{'SCB','GULF','STECON','TIDLOR'},original.source_hashes)}
    data={k:LotData(p) for k,p in panels.items()};features={k:Features(p) for k,p in panels.items()}
    recipes=[('original_15',SmallSpec(**plan['reference'],affordability_filter=False))]
    recipes += [(f'affordable_{n}_exit{e}',SmallSpec(top_n=n,daily_exit=e)) for n in plan['holdings_grid'] for e in plan['market_exit_grid']]
    hashes={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in ['configs/small_capital_plan.json','configs/thai_trading_costs.json',
        'research/small_capital.py','research/candidates.py','research/portfolio.py','scripts/research_small_capital.py','data/indices/set100_tradingview_daily.csv']}
    fp={'prices':original.source_hashes,'sources':hashes}
    context='small_capital_'+hashlib.sha256(json.dumps(fp,sort_keys=True).encode()).hexdigest()[:16]
    registry=Registry(ROOT/'research/experiments')
    manifest={'context':context,'plan':plan,'hashes':fp,'known_complex_actions':sorted(complex_names),
        'stock_missing_sessions':[str(d.date()) for d in calendar.difference(original.dates)],
        'data_class':'daily-price-and-action-derived approximation, not observed auction tape',
        'sources':['https://www.set.or.th/en/market/information/trading-procedure/trading-units',
            'https://www.set.or.th/en/market/information/trading-procedure/trading-hours',
            'https://www.set.or.th/en/market/information/trading-procedure/order-types',
            'https://github.com/ranaroussi/yfinance/issues/1749',
            'https://www.set.or.th/en/market/news-and-alert/newsdetails?id=2023046335&symbol=DELTA']}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
    rows=[];bench={}
    for name,spec in recipes:
        for scenario in plan['scenarios']:
            key=scenario if scenario in data else 'base';d=data[key];feat=features[key]
            fee=FeeSchedule(**costs['stress' if scenario=='higher_cost' else 'base'])
            if scenario=='minimum_fee':fee=replace(fee,minimum_daily_commission_thb=50)
            x=LotExecution(windows=('morning',) if scenario=='morning_only' else ('close',) if scenario=='close_only' else ('morning','close'),
                phase=10 if scenario=='phase_10' else 0,extra_delay=int(scenario=='delay_one'),missed_fills=scenario=='missed_fills')
            for period,start in [('full','2017-01-04'),('recent','2024-01-01')]:
                stage=scenario+'_'+period
                bk=(scenario,period)
                if bk not in bench:
                    b,bc=price_only_basket(d,start,'2026-09-28',fee,plan['capital_thb']);bench[bk]=b
                    if scenario=='base':bc.to_csv(OUT/f'benchmark_{period}.csv',index_label='date',header=['equity'])
                b=bench[bk]
                result=registry.get(context,spec.identity,stage)
                if result is None:
                    result,curve,fills,daily=simulate_lots(d,feat,spec,start,'2026-09-28',fee,plan['capital_thb'],x,details=scenario=='base')
                    result.update(scenario=scenario,period=period,benchmark_cagr=b['cagr'],benchmark_total_return=b['total_return'],
                        benchmark_drawdown=b['max_drawdown'],excess_cagr=result['cagr']-b['cagr'])
                    registry.put(context,spec.identity,stage,asdict(spec),result)
                    folder=OUT/spec.identity;folder.mkdir(exist_ok=True)
                    curve.to_csv(folder/f'{stage}_equity.csv',index_label='date',header=['equity'])
                    if scenario=='base':
                        fills.to_csv(folder/f'{stage}_fills.csv',index=False);daily.to_csv(folder/f'{stage}_daily.csv')
                rows.append({'name':name,'candidate':spec.identity,**result})
        print('Audited',name,spec.identity,flush=True)
    results=pd.DataFrame(rows);results.to_csv(OUT/'all_results.csv',index=False)
    scores=[]
    for name,spec in recipes:
        subset=results[results.candidate.eq(spec.identity)];full=subset[subset.period.eq('full')]
        failed=subset[(subset.excess_cagr<=0)|(subset.max_drawdown<-.25)]
        scores.append({'name':name,'candidate':spec.identity,'passes':bool(failed.empty),'min_full_cagr':float(full.cagr.min()),
            'worst_drawdown':float(subset.max_drawdown.min()),'failed_cases':failed[['scenario','period','excess_cagr','max_drawdown']].to_dict('records')})
    passed=[r for r in scores if r['passes']]
    chosen=sorted(passed or scores,key=lambda r:(r['min_full_cagr'],r['worst_drawdown']),reverse=True)[0]
    spec=next(r for name,r in recipes if r.identity==chosen['candidate'])
    selection={'name':chosen['name'],'candidate':spec.identity,'parameters':asdict(spec),'capital_thb':plan['capital_thb'],
        'research_gate_passed':bool(passed),'live_ready':False,'user_drawdown_limit':None,'status':'experimental_strategy_only',
        'scores':scores,'execution_windows':['morning_ATO','afternoon_ATO','closing_ATC'],
        'validated_price_proxy_windows':['daily_open','daily_close'],
        'blockers':['Historical effective membership/exited stock histories missing','Afternoon and actual auction execution data missing',
            'Historical lot/entitlement/corporate-action metadata unverified','Cash-dividend cash-flow and taxes not modeled',
            'Fresh forward paper performance not observed','Broker and user drawdown limit not set']}
    (OUT/'selection.json').write_text(json.dumps(selection,indent=2))
    ledger_path=ROOT/'research/experiments/STRATEGY_LEDGER.csv';ledger=pd.read_csv(ledger_path);add=[]
    for score in scores:
        s=next(s for n,s in recipes if s.identity==score['candidate'])
        if s.identity in set(ledger.candidate):continue
        r=results[(results.candidate==s.identity)&(results.scenario=='base')&(results.period=='full')].iloc[0]
        add.append({'candidate':s.identity,'family':s.family,'parameters':json.dumps(asdict(s),sort_keys=True),
            'rule':'Capital-aware affordability screening then buffered momentum; 100-share order lots; price-only daily proxy',
            'status':'selected_experimental_30000' if s.identity==spec.identity else 'rejected_30000_comparison',
            'reason':json.dumps(score),'batch':'small_capital_30000_20260929','report':str(OUT.relative_to(ROOT)),
            **{'full_base_'+k:r[k] for k in ['total_return','cagr','max_drawdown','excess_cagr','fills']}})
    if add:pd.concat([ledger,pd.DataFrame(add)],ignore_index=True).to_csv(ledger_path,index=False)
    registry.export()
    print(results[(results.scenario=='base')&(results.period=='full')][['name','total_return','cagr','max_drawdown','mean_positions','fees_fraction_initial_capital']].to_string(index=False))
    print('SELECTED',chosen['name'],'passed',bool(passed),'worst cagr',chosen['min_full_cagr'],'worst DD',chosen['worst_drawdown'])


if __name__=='__main__':main()
