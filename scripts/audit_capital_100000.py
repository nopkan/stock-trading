"""Post-selection diagnostics; never reselect on these results."""
from dataclasses import asdict
import hashlib
import json
import numpy as np
import pandas as pd
from research.portfolio import ROOT, Panel, FeeSchedule
from research.registry import Registry
from research.capital_search import CapitalRecipe, rank_features
from research.small_capital import LotData, LotExecution, simulate_lots, price_only_basket
from scripts.research_capital_100000 import OUT, load_panels


def replay(candidate, data, fee, capital=100000.):
    p = data.panel
    folder = OUT/candidate
    curve = pd.read_csv(folder/'base_full_equity.csv',index_col='date',parse_dates=True).equity
    fills = pd.read_csv(folder/'base_full_fills.csv',parse_dates=['date'])
    daily = pd.read_csv(folder/'base_full_daily.csv',index_col='date',parse_dates=True)
    cash = capital; shares = np.zeros(len(p.symbols)); pnl = np.zeros(len(p.symbols))
    groups = dict(tuple(fills.groupby('date'))); errors = []; min_topups = 0.
    for date in curve.index:
        i = p.dates.get_loc(date); shares *= data.actions[i]; amount = 0.
        if date in groups:
            for window in ('morning','close'):
                g = groups[date]; trades = g[g.window.eq(window)]
                buys = trades[trades.side.eq('buy')]
                assert (buys.notional_thb+buys.variable_fee_thb).sum() <= cash+1e-6
                for r in trades.itertuples():
                    assert r.shares > 0 and r.shares % 100 == 0
                    assert np.isclose(r.shares*r.price_proxy,r.notional_thb)
                    j = p.symbols.index(r.symbol); sign = 1 if r.side == 'buy' else -1
                    shares[j] += sign*r.shares
                    flow = -sign*r.notional_thb-r.variable_fee_thb
                    cash += flow; pnl[j] += flow; amount += r.notional_thb
            topup = fee.daily_minimum_topup(amount,1.); cash -= topup; min_topups += topup
        assert cash >= -1e-6 and shares.min() >= -1e-6
        nav = cash+shares@data.marks[i]
        errors.append(abs(nav-capital*curve.loc[date]))
        np.testing.assert_allclose(nav,capital*curve.loc[date],atol=1e-6,rtol=1e-10)
        np.testing.assert_allclose(cash,daily.loc[date,'cash_thb'],atol=1e-6)
    values = shares*data.marks[p.dates.get_loc(curve.index[-1])]
    pnl += values
    np.testing.assert_allclose(pnl.sum()-min_topups,capital*(curve.iloc[-1]-1),atol=1e-6)
    attribution = pd.DataFrame({'symbol':p.symbols,'pnl_thb_after_variable_fees':pnl,
                                 'ending_shares':shares,'ending_value_thb':values}).sort_values('pnl_thb_after_variable_fees',ascending=False)
    attribution.to_csv(folder/'attribution.csv',index=False)
    return {'candidate':candidate,'fills_checked':len(fills),'whole_lot_orders':True,
            'no_same_window_sale_funding':True,'max_nav_error_thb':max(errors),
            'minimum_commission_topups_thb':min_topups}, attribution


def main():
    selection = json.loads((OUT/'selection.json').read_text())
    manifest = json.loads((OUT/'manifest.json').read_text())
    recipe = CapitalRecipe.from_parameters(selection['parameters'])
    panels,index = load_panels(); data = LotData(panels['base'])
    fee = FeeSchedule(**json.loads((ROOT/'configs/thai_trading_costs.json').read_text())['base'])
    checks = []; attr = None
    for candidate in dict.fromkeys([recipe.identity,selection['highest_base_return_candidate']]):
        check, a = replay(candidate,data,fee); checks.append(check)
        if candidate == recipe.identity: attr = a
    verification = {'ledger_replays':checks,'cash_dividends_credited':False,'initial_capital_thb':100000}
    reproduced = pd.read_csv(OUT/'reproduction/equity.csv',index_col='date',parse_dates=True).strategy
    saved = pd.read_csv(OUT/recipe.identity/'base_full_equity.csv',index_col='date',parse_dates=True).equity
    np.testing.assert_allclose(reproduced,saved,atol=1e-12,rtol=1e-12)
    verification['independent_cli_reproduction_matches'] = True
    (OUT/'verification.json').write_text(json.dumps(verification,indent=2))
    top = attr.head(3).symbol.tolist()
    plan = {'purpose':'Additional diagnostics after frozen selection, no reselection',
            'candidate':recipe.identity,'rebalance_phases':list(range(recipe.sizing.rebalance)),
            'exclude_actual_profit_leaders':top,
            'cold_start_blocks':[['2017-01-04','2019-12-31'],['2020-01-01','2023-12-31'],['2024-01-01','2026-09-28']],
            'all_history_previously_seen':True}
    (OUT/'post_selection_audit_plan.json').write_text(json.dumps(plan,indent=2))
    registry = Registry(ROOT/'research/experiments')
    audit_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    context = manifest['context']+'_audit_'+audit_hash[:12]
    features = rank_features(panels['base'])[recipe.ranking]
    rows = []

    def evaluate(label, d, f, start, end, execution):
        cached = registry.get(context,recipe.identity,label)
        if cached is not None: return cached
        result,curve,_,_ = simulate_lots(d,f,recipe.sizing,start,end,fee,100000,execution)
        b,_ = price_only_basket(d,start,end,fee,100000)
        result.update(label=label,start=start,end=end,benchmark_cagr=b['cagr'],
                      benchmark_total_return=b['total_return'],excess_cagr=result['cagr']-b['cagr'])
        registry.put(context,recipe.identity,label,{'recipe':recipe.parameters,'execution':asdict(execution),
                     'exclusions':sorted(d.panel.exclusions)},result)
        curve.to_csv(OUT/recipe.identity/f'audit_{label}_equity.csv',index_label='date',header=['equity'])
        return result

    base_results = pd.read_csv(OUT/'all_results.csv')
    for phase in range(recipe.sizing.rebalance):
        if phase in (0, recipe.sizing.rebalance//2):
            scenario = 'base' if phase == 0 else 'phase_half'
            result = base_results[(base_results.candidate==recipe.identity)&(base_results.scenario==scenario)&(base_results.period=='full')].iloc[0].to_dict()
            result.update(label=f'phase_{phase}',reused_existing_evaluation=True)
        else:
            result = evaluate(f'phase_{phase}',data,features,'2017-01-04','2026-09-28',LotExecution(phase=phase))
        rows.append({'phase':phase,**result})
        if phase%10 == 0: print('Phase audit',phase,flush=True)
    phases = pd.DataFrame(rows); phases.to_csv(OUT/'rebalance_phase_audit.csv',index=False)
    p = panels['base']; ex = Panel(p.frames,p.exclusions|set(top),p.source_hashes)
    d = LotData(ex); f = rank_features(ex)[recipe.ranking]
    extra = [evaluate('exclude_actual_leaders_full',d,f,'2017-01-04','2026-09-28',LotExecution()),
             evaluate('exclude_actual_leaders_recent',d,f,'2024-01-01','2026-09-28',LotExecution())]
    for start,end in plan['cold_start_blocks']:
        extra.append(evaluate('block_'+start[:4],data,features,start,end,LotExecution()))
    pd.DataFrame(extra).to_csv(OUT/'additional_diagnostics.csv',index=False)
    diagnostic = {'candidate':recipe.identity,'top_profit_names':top,
                  'top3_fraction_of_net_profit':float(attr.head(3).pnl_thb_after_variable_fees.sum()/(100000*(saved.iloc[-1]-1))),
                  'phase_min_return':float(phases.total_return.min()),'phase_median_return':float(phases.total_return.median()),
                  'phase_max_return':float(phases.total_return.max()),'phase_worst_drawdown':float(phases.max_drawdown.min()),
                  'phases_reaching_304_77':int(phases.total_return.ge(3.0477).sum()),'phase_count':len(phases),
                  'all_phase_drawdown_screen_passed':bool(phases.max_drawdown.ge(-.25).all()),
                  'audit_code_sha256':audit_hash,'registry_context':context,
                  'additional_diagnostics':extra,'live_ready':False}
    (OUT/'audit_summary.json').write_text(json.dumps(diagnostic,indent=2))
    registry.export()
    print(json.dumps(diagnostic,indent=2),flush=True)


from pathlib import Path
if __name__ == '__main__': main()
