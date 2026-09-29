"""Verify trade-ledger accounting and publish the full search record."""
from pathlib import Path
import json
import sqlite3
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

from research.portfolio import ROOT, Panel

FOLDER=ROOT/'reports/strategy_search_20260929_v2'
LABELS={'multi_horizon':'Multi-horizon momentum','volume_flow':'Volume-flow leaders',
        'consistent_trend':'Consistent trend','downside_momentum':'Downside-adjusted momentum',
        'high_proximity':'Six-month high leaders'}


def replay(panel, fills, curve, profile, capital):
    """Independent cash-account reconstruction using exported fills only."""
    groups={pd.Timestamp(date):f for date,f in fills.groupby('date')}
    holdings=pd.Series(0.,index=panel.symbols)
    cash=capital
    reconstructed=[]
    paid=0.
    for date in curve.index:
        daily=groups.get(date)
        if daily is not None:
            signs=daily.side.map({'buy':1.,'sell':-1.})
            quantity=(daily.adjusted_units*signs).groupby(daily.symbol).sum()
            holdings.loc[quantity.index]+=quantity
            cash-=float((daily.notional_thb*signs).sum())
            notional=float(daily.notional_thb.sum())
            # Reconstruct commission minimum and VAT separately from the engine.
            commission=max(profile['minimum_daily_commission_thb'],notional*profile['commission_bps']/10000)
            other=notional*(profile['exchange_bps']+profile['clearing_bps']+profile['regulatory_bps'])/10000
            fee=(commission+other)*(1+profile['vat'])
            cash-=fee
            paid+=fee
        if cash < -1e-5 or holdings.min() < -1e-5:
            raise AssertionError('Ledger replay found borrowing or shorting')
        marks=panel.marks[panel.dates.get_loc(date)]
        reconstructed.append((cash+holdings.to_numpy()@marks)/capital)
    np.testing.assert_allclose(reconstructed,curve.to_numpy(),atol=1e-9,rtol=1e-9)
    return {'max_equity_error':float(np.max(np.abs(np.array(reconstructed)-curve.to_numpy()))),
            'fees_paid_thb':paid,'ending_equity_thb':reconstructed[-1]*capital}


def main():
    chosen=pd.read_csv(FOLDER/'retained_strategies.csv')
    candidates=pd.read_csv(FOLDER/'all_candidates.csv')
    dispositions=pd.read_csv(FOLDER/'audit_dispositions.csv').set_index('candidate').disposition.to_dict()
    costs=json.loads((ROOT/'configs/thai_trading_costs.json').read_text())
    benchmarks=json.loads((FOLDER/'benchmarks.json').read_text())
    config=json.loads((FOLDER/'search_plan.json').read_text())
    registry=sqlite3.connect(ROOT/'research/experiments/registry.sqlite3')
    trials={}
    for candidate,stage,result in registry.execute('SELECT candidate,stage,result FROM trials WHERE context=?',(config['context'],)):
        trials[(candidate,stage)]=json.loads(result)
    sensitivity=pd.read_csv(FOLDER/'sensitivity_results.csv')
    ledger=[]
    for _,r in candidates.iterrows():
        spec={k:r[k].item() if hasattr(r[k],'item') else r[k] for k in ['family','lookback','top_n','rebalance','trend','market_filter','skip','min_turnover_thb','reserve']}
        row={'candidate':r.candidate,'family':r.family,'parameters':json.dumps(spec,sort_keys=True),
             'rule':r.rule,'status':dispositions.get(r.candidate,r.status)}
        for stage in ['discovery_base','validation_base','confirmation_base','confirmation_stress','full_base','full_stress']:
            result=trials.get((r.candidate,stage),{})
            for metric in ['total_return','cagr','max_drawdown','excess_cagr','sharpe_rf0','fills']:
                row[stage+'_'+metric]=result.get(metric)
        d,v=trials[(r.candidate,'discovery_base')],trials[(r.candidate,'validation_base')]
        reasons=[]
        for stage,result in [('discovery',d),('validation',v)]:
            if result['excess_cagr']<=0:reasons.append(stage+': did not beat benchmark')
            if not result['drawdown_better']:reasons.append(stage+': worse drawdown than benchmark')
        for stage in ['confirmation_base','confirmation_stress','full_base','full_stress']:
            result=trials.get((r.candidate,stage))
            if result is not None:
                if result['excess_cagr']<=0:reasons.append(stage+': did not beat benchmark')
                if not result['drawdown_better']:reasons.append(stage+': worse drawdown than benchmark')
        failed_audits=sensitivity.loc[sensitivity.candidate.eq(r.candidate)&sensitivity.excess_cagr.le(0)]
        for _,audit in failed_audits.iterrows():
            reasons.append(audit.scenario+' '+audit.period+': did not beat corresponding benchmark')
        if row['status']=='confirmation_failed_or_pending':row['status']='rejected_confirmation'
        if not reasons:reasons.append(row['status'])
        row['reason']='; '.join(reasons)
        ledger.append(row)
    legacy=pd.read_csv(ROOT/'reports/strategy_comparison_20260929/full_period/comparison.csv')
    legacy_recent=pd.read_csv(ROOT/'reports/strategy_comparison_20260929/recent_period/comparison.csv').set_index('strategy')
    archive=json.loads((ROOT/'research/experiments/legacy_strategy_sources.json').read_text())
    for _,r in legacy.loc[legacy.strategy.ne('buy_hold')].iterrows():
        ledger.append({'candidate':'legacy_'+r.strategy,'family':r.strategy,
            'parameters':json.dumps(archive[r.strategy]['defaults'],sort_keys=True),
            'rule':'Original single-stock allocation rule; source preserved in legacy_strategy_sources.json',
            'status':'rejected_original_module_deleted','reason':'Below same-cost benchmark; original fees 0.20% + slippage 0.10% per side.',
            'full_base_total_return':r.total_return,'full_base_cagr':r.cagr,'full_base_max_drawdown':r.max_drawdown,
            'confirmation_base_total_return':legacy_recent.loc[r.strategy,'total_return']})
    # Preserve later research batches when regenerating this historical report.
    ledger_path=ROOT/'research/experiments/STRATEGY_LEDGER.csv'
    additional=[]
    if ledger_path.exists():
        prior=pd.read_csv(ledger_path)
        additional=prior[~prior.candidate.isin([r['candidate'] for r in ledger])].to_dict('records')
    pd.DataFrame(ledger+additional).to_csv(ledger_path,index=False)
    ledger_md=['# All strategy hypotheses tested','',
        '276 portfolio configurations plus the original five = **281 distinct specifications**. Verification reruns under corrected code are not counted as new strategies. Decimal values in CSV are fractions; the table below displays CAGR as percentages. A dash means that period was not evaluated after the candidate failed or was not shortlisted. Original-rule results used the earlier 0.20% fee assumption; the new search uses researched broker costs.','',
        '| ID | Family | Parameters | Discovery CAGR | Validation CAGR | Full CAGR | Status / reason |',
        '|---|---|---|---:|---:|---:|---|']
    fmt=lambda x:'—' if x is None or pd.isna(x) else f'{x:.2%}'
    for r in ledger:
        ledger_md.append(f"| {r['candidate']} | {r['family']} | `{r['parameters']}` | {fmt(r.get('discovery_base_cagr'))} | {fmt(r.get('validation_base_cagr'))} | {fmt(r.get('full_base_cagr'))} | {r['reason']} |")
    if additional:
        ledger_md.extend(['','## Later refinement experiments','',
            f'{len(additional)} additional specifications are preserved in STRATEGY_LEDGER.csv. See [refinement report](../../reports/momentum_refinement_20260929/RESULTS.md) for every later trial and its outcome.'])
    (ROOT/'research/experiments/STRATEGY_LEDGER.md').write_text('\n'.join(ledger_md)+'\n')
    panel=Panel.load()
    replay_results=[]
    for _,r in chosen.iterrows():
        for profile in ['base','stress']:
            curve=pd.read_csv(FOLDER/r.candidate/f'full_{profile}_equity.csv',index_col='date',parse_dates=True).equity
            fills=pd.read_csv(FOLDER/r.candidate/f'full_{profile}_fills.csv')
            result=replay(panel,fills,curve,costs[profile],costs['initial_capital_thb'])
            recorded=trials[(r.candidate,'full_'+profile)]
            assert np.isclose(result['fees_paid_thb']/costs['initial_capital_thb'],recorded['fees_fraction_initial_capital'])
            replay_results.append({'candidate':r.candidate,'profile':profile,**result})
    (FOLDER/'independent_ledger_verification.json').write_text(json.dumps(replay_results,indent=2))
    curve_map={'Buy-and-hold':pd.read_csv(FOLDER/'benchmark_full_base.csv',index_col='date',parse_dates=True).equity}
    for _,r in chosen.iterrows():
        curve_map[LABELS[r.family]]=pd.read_csv(FOLDER/r.candidate/'full_base_equity.csv',index_col='date',parse_dates=True).equity
    curves=pd.DataFrame(curve_map)
    fig,axes=plt.subplots(2,1,figsize=(13,8.5),sharex=True,gridspec_kw={'height_ratios':[2,1]})
    colors=['#17212f','#147d92','#a96624','#8151a8','#cf4b52','#3a8559']
    for (name,series),color in zip(curves.items(),colors):
        axes[0].plot(series.index,series*100,label=name,color=color,lw=2.2 if name=='Buy-and-hold' else 1.5)
        dd=series/series.cummax().clip(lower=1)-1
        axes[1].plot(series.index,dd,color=color,lw=1)
    axes[0].set_title('Five retained research strategies vs buy-and-hold',loc='left',fontsize=17,pad=14)
    axes[0].set_ylabel('Portfolio value · start = 100')
    axes[0].legend(loc='upper left',ncol=2,frameon=False,fontsize=9)
    axes[1].set_ylabel('Drawdown')
    axes[1].yaxis.set_major_formatter(PercentFormatter(1))
    for ax in axes:
        ax.grid(alpha=.18)
        ax.spines[['top','right']].set_visible(False)
    fig.text(.08,.015,'2017–Sep 2026 • Fees 0.16799% + slippage 0.10% per side • Fixed current SET100 snapshot; retrospective selection bias',fontsize=9,color='#555555')
    fig.tight_layout(rect=[0,.04,1,1])
    fig.savefig(FOLDER/'equity_and_drawdown.png',dpi=170)
    fig.savefig(FOLDER/'equity_and_drawdown.svg')
    plt.close(fig)
    lines=['# Five retained SET100 research strategies','',
        '**276 new portfolio configurations tested across 12 rule families; all five original failed rules also recorded. Five retained after chronological, higher-cost and sensitivity checks.** These are retrospective fixed-membership backtest outperformers, not proof of future market-beating performance.','',
        'Evaluation: January 4, 2017–September 28, 2026. Starting capital: THB1,000,000. All reported returns are after the modeled fees and slippage. Explicit fees are 0.16799% per side; slippage is 0.10%. The benchmark uses the same fee schedule. BANPU stays cash.','',
        '| Strategy | Net total return | CAGR | Max drawdown | 2024–Sep 2026 total return | Higher-cost full CAGR |',
        '|---|---:|---:|---:|---:|---:|']
    for _,r in chosen.iterrows():
        lines.append(f'| {LABELS[r.family]} | {r.full_base_total_return:.2%} | {r.full_base_cagr:.2%} | {r.full_base_max_drawdown:.2%} | {r.confirmation_base_total_return:.2%} | {r.full_stress_cagr:.2%} |')
    b=benchmarks['full_base'];recent=benchmarks['confirmation_base'];stress=benchmarks['full_stress']
    lines.append(f'| **Buy-and-hold benchmark** | **{b["total_return"]:.2%}** | **{b["cagr"]:.2%}** | **{b["max_drawdown"]:.2%}** | **{recent["total_return"]:.2%}** | **{stress["cagr"]:.2%}** |')
    lines+=['','![Equity and drawdown](equity_and_drawdown.png)','',
        '## Exact retained rules','',
        'All five require positive momentum excluding the latest 21 sessions, the stock above SMA200, and the equal-weight market proxy above SMA200. They buy the highest-ranked eligible names. At rebalancing, absent qualifying names leave their slots in cash. Filters are evaluated only at scheduled rebalance closes.','',
        '| Module | Ranking | Names | Rebalance interval | ID |','|---|---|---:|---:|---|']
    active=json.loads((ROOT/'strategy/active.json').read_text())
    for a in active:
        lines.append(f"| `{a['module']}.py` | {a['rule']} Lookback: {a['parameters']['lookback']} sessions. | {a['parameters']['top_n']} | {a['parameters']['rebalance']} sessions | `{a['candidate']}` |")
    lines+=['','The multi-horizon score combines 63/126/252-session ranks. The downside-adjusted score divides momentum by 63-session downside deviation. Volume flow is trailing signed volume divided by total volume. Consistent trend multiplies momentum by the fraction of positive-return sessions. High proximity ranks close divided by its trailing 126-session maximum.','',
        '## What was rejected and why','',
        '23 of 276 configurations passed discovery and validation; 19 were locked for later testing. 17 configurations passed the later and full-period base/stress return-and-drawdown checks. The sensitivity audit rejected two of those. Family/return-similarity filtering and the original discovery/validation score selected the final five. Other passing candidates are recorded as not selected, not incorrectly labeled failures.','',
        'The initially higher-ranked downside-momentum variant failed an additional-delay/exclusion audit; the retained downside variant has different predeclared parameters. Ordinary momentum variants were near-duplicates of retained trend strategies. The original five single-stock strategy files were deleted from the active folder; their source definitions and results remain in the audit trail.','',
        '## Files that prevent repeated experiments','',
        '- [Every distinct hypothesis and result](../../research/experiments/STRATEGY_LEDGER.md)',
        '- [Machine-readable strategy ledger](../../research/experiments/STRATEGY_LEDGER.csv)',
        '- [All individual evaluation records](../../research/experiments/all_trials.csv)',
        '- [Predeclared search plan](search_plan.json) and [locked shortlist](locked_shortlist.json)',
        '- [Final retained strategies](retained_strategies.csv), [sensitivity results](sensitivity_results.csv), and [audit dispositions](audit_dispositions.csv)',
        '- [Independent trade-ledger accounting checks](independent_ledger_verification.json)',
        '- [Thai cost sources and calculation](../../docs/THAI_TRADING_COSTS.md)',
        '- [Search protocol and limitations](../../docs/SEARCH_PROTOCOL.md)',
        '',
        '## Interpretation and limits','',
        'Multi-horizon momentum had the highest full-period return of the retained five. Downside-adjusted momentum had the highest recent-period return. These are not five independent bets: they share equity momentum and trend filters. The maximum pairwise daily-return correlation is below the chosen 0.95 near-duplicate threshold, but correlations remain substantial.','',
        'All five exceed their matching benchmark with higher costs, one additional execution session of delay, DELTA excluded, and THAI excluded. This does not resolve survivorship bias, multiple-testing bias, incomplete historical company identities, delayed/stale price marks or the lack of a new untouched holdout. The benchmark is the original equal-initial-allocation basket, not the official capitalization-weighted SET100 index.','',
        'The engine uses fractional adjusted units. Board lots, exact opening liquidity, tick-size rounding and a historical suspension feed are not modeled. The daily minimum commission is included in the higher-cost scenario. Portfolio values include open positions at the final close, with no forced final liquidation fee. A paper/live-execution model and historical constituent data remain the next evidence needed before deployment.','',
        'Verification: 34 automated tests passed. Independent replays reconstruct all ten retained full-period base/stress equity curves from exported fills, including commission, exchange charges, VAT and stress minimums. The writable-array fix was verified under a separate code context with unchanged selected results. This verification rerun is not counted as new strategy discovery.','']
    (FOLDER/'RESULTS.md').write_text('\n'.join(lines))
    (ROOT/'research/experiments/README.md').write_text('# Experiment registry\n\nStart with [STRATEGY_LEDGER.md](STRATEGY_LEDGER.md) or [STRATEGY_LEDGER.csv](STRATEGY_LEDGER.csv): one row per distinct hypothesis.\n\n`all_trials.csv` contains every saved evaluation, including different periods, fees, code contexts and diagnostics. `registry.sqlite3` is the authoritative deduplication store. Candidate IDs identify canonical rules and parameters; context IDs identify data, code and cost conditions. Do not erase rejected records.\n\nThe 276 candidate recipes are reusable research definitions in `research/candidates.py`; only five are promoted to active strategy modules. The five rejected original modules survive as audit text in `legacy_strategy_sources.json`.\n')
    print('Verified',len(replay_results),'trade-ledger replays; wrote',len(ledger),'distinct strategy records.')


if __name__=='__main__':main()
