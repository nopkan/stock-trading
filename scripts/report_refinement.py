"""Publish every refinement, preserve the previous ledger, verify exported fills."""
from dataclasses import asdict
import json,sqlite3,hashlib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
from research.portfolio import ROOT,Panel
from research.refine_search import INCUMBENT
from scripts.report_search import replay

FOLDERS=[ROOT/'reports'/p for p in ['momentum_refinement_20260929',
    'momentum_reserve_20260929','momentum_staggered_20260929']]
EXAMPLES={'e9a522bb24938501':'Buffered 15 / 5% cash',
          'f4f5be7d82b85c48':'Buffered 15 / 10% cash'}


def main():
    conn=sqlite3.connect(ROOT/'research/experiments/registry.sqlite3')
    p=Panel.load();allrows=[]
    for batch,folder in enumerate(FOLDERS,1):
        plan=json.loads((folder/'search_plan.json').read_text())
        assert p.source_hashes==plan['source']['prices']
        for path,digest in plan['source']['code'].items():
            assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest,path
        candidates=pd.read_csv(folder/'all_candidates.csv')
        reference=json.loads((folder/'incumbent.json').read_text())
        records={(c,s):json.loads(r) for c,s,r in conn.execute('select candidate,stage,result from trials where context=?',(plan['context'],))}
        audits=pd.read_csv((FOLDERS[1] if batch==1 else folder)/'sensitivity_results.csv')
        for _,candidate in candidates.iterrows():
            spec=json.loads(candidate.parameters)
            row={'candidate':candidate.candidate,'family':spec['family'],'parameters':candidate.parameters,
                'rule':'Rank-buffered or blended multi-horizon momentum' if batch<3 else 'Average staggered desired momentum baskets; netted execution',
                'batch':batch,'report':str(folder.relative_to(ROOT)),
                'status':candidate.status.replace('confirmation_failed_or_pending','rejected_confirmation'),
                'screen_pass':bool(candidate.screen_pass),'confirmed':bool(candidate.confirmed),
                'selection_score':candidate.selection_score}
            reasons=[]
            for period in ['discovery','validation','development','recent','full']:
                for profile in ['base','stress']:
                    stage=period+'_'+profile
                    r=records.get((candidate.candidate,('normal_' if batch==3 else '')+stage))
                    if r is None:continue
                    row.update({stage+'_'+k:v for k,v in r.items()})
                    b=reference[stage]
                    row[stage+'_incumbent_cagr_gain']=r['cagr']-b['cagr']
                    row[stage+'_incumbent_drawdown_gain']=r['max_drawdown']-b['max_drawdown']
                    if period=='development' and profile=='base':
                        if r['cagr']<=b['cagr']:reasons.append('development: CAGR not higher')
                        if r['max_drawdown']<=b['max_drawdown']:reasons.append('development: drawdown not smaller')
                    if period in ('discovery','validation') and profile=='base' and r['cagr']<b['cagr']-.02:
                        reasons.append(period+': CAGR trails incumbent by >2 percentage points')
                    if period in ('recent','full'):
                        if r['cagr']<=b['cagr']-(.02 if period=='recent' else 0):reasons.append(stage+': return requirement failed')
                        if r['max_drawdown']<b['max_drawdown']:reasons.append(stage+': drawdown requirement failed')
            for _,a in audits[(audits.candidate.eq(candidate.candidate))&audits.period.eq('full')].iterrows():
                if a.cagr_gain<=0:reasons.append(a.scenario+': CAGR not higher')
                if a.drawdown_gain<=0:reasons.append(a.scenario+': drawdown not smaller')
            row['reason']='; '.join(reasons) or row['status']
            allrows.append(row)
    ledger=pd.DataFrame(allrows)
    assert len(ledger)==271 and ledger.candidate.nunique()==271
    ledger.to_csv(FOLDERS[0]/'ALL_REFINEMENTS.csv',index=False)
    path=ROOT/'research/experiments/STRATEGY_LEDGER.csv'
    old=pd.read_csv(path);old=old[~old.candidate.isin(ledger.candidate)]
    combined=pd.concat([old,ledger],ignore_index=True)
    assert len(combined)==552 and combined.candidate.nunique()==552
    combined.to_csv(path,index=False)
    fmt=lambda x:'—' if pd.isna(x) else f'{x:.2%}'
    md=['# Every momentum refinement','',
        '271 new specifications in three frozen batches: 223 broad variants, 12 adaptive cash-reserve variants, 36 adaptive staggered-rebalance variants. All prices had previously been inspected. These are not 271 independent tests or an untouched holdout. Rejected trials and partial evaluations are preserved. Blank cells mean no evaluation after failing the earlier screen.','',
        '| ID | Batch | Parameters | Development CAGR | Full return | Full max drawdown | Status / reason |',
        '|---|---:|---|---:|---:|---:|---|']
    for _,r in ledger.iterrows():
        md.append(f'| {r.candidate} | {r.batch} | `{r.parameters}` | {fmt(r.development_base_cagr)} | {fmt(r.full_base_total_return)} | {fmt(r.full_base_max_drawdown)} | {r.status}: {r.reason} |')
    (ROOT/'research/experiments/REFINEMENT_LEDGER.md').write_text('\n'.join(md)+'\n')
    index=ROOT/'research/experiments/STRATEGY_LEDGER.md'
    text=index.read_text().split('\n## Later refinement experiments')[0]
    text+='\n\n## Later refinement experiments\n\n271 new variants bring the permanent CSV ledger to **552 distinct specifications**. See [every refinement](REFINEMENT_LEDGER.md) and [comparison report](../../reports/momentum_refinement_20260929/RESULTS.md). None passed every strict robustness requirement; the original active five remain unchanged.\n'
    index.write_text(text)
    folder=FOLDERS[1];config=json.loads((ROOT/'configs/thai_trading_costs.json').read_text())
    verification=[]
    for cid in [INCUMBENT,*EXAMPLES]:
        for period in ['full','recent']:
            for profile in ['base','stress']:
                e=pd.read_csv(folder/cid/f'{period}_{profile}_equity.csv',index_col='date',parse_dates=True).equity
                fills=pd.read_csv(folder/cid/f'{period}_{profile}_fills.csv')
                r=replay(p,fills,e,config[profile],config['initial_capital_thb'])
                verification.append({'candidate':cid,'period':period,'profile':profile,**r})
    for cid,dirname in zip(EXAMPLES,['reproduction_buffer5','reproduction_buffer10']):
        original=pd.read_csv(folder/cid/'full_base_equity.csv',index_col='date').equity
        reproduced=pd.read_csv(folder/dirname/'equity.csv',index_col='date').experimental_buffered_momentum
        np.testing.assert_allclose(original,reproduced,rtol=1e-12,atol=1e-12)
    (FOLDERS[0]/'independent_ledger_verification.json').write_text(json.dumps(verification,indent=2))
    baseline=json.loads((folder/'incumbent.json').read_text())
    plan=json.loads((folder/'search_plan.json').read_text())
    curves={'Buy-and-hold basket':pd.read_csv(folder/'benchmark_full_base.csv',index_col='date',parse_dates=True).equity,
        'Original multi-horizon':pd.read_csv(folder/INCUMBENT/'full_base_equity.csv',index_col='date',parse_dates=True).equity}
    metrics=[]
    for label,cid in [('Buy-and-hold basket','benchmark'),('Original multi-horizon',INCUMBENT),*((label,cid) for cid,label in EXAMPLES.items())]:
        for period in ['full','recent']:
            for profile in ['base','stress']:
                r=json.loads(conn.execute('select result from trials where context=? and candidate=? and stage=?',
                    (plan['context'],cid,period+'_'+profile)).fetchone()[0])
                metrics.append({'strategy':label,'candidate':cid,'period':period,'cost_profile':profile,**r})
        if cid in EXAMPLES:curves[label]=pd.read_csv(folder/cid/'full_base_equity.csv',index_col='date',parse_dates=True).equity
    metrics=pd.DataFrame(metrics);metrics.to_csv(FOLDERS[0]/'comparison.csv',index=False)
    annual=[]
    for label,e in curves.items():
        prior=1.
        for year,g in e.groupby(e.index.year):
            annual.append({'strategy':label,'year':year,'return':g.iloc[-1]/prior-1})
            prior=g.iloc[-1]
    pd.DataFrame(annual).to_csv(FOLDERS[0]/'annual_returns.csv',index=False)
    fig,axes=plt.subplots(2,1,figsize=(12,8),sharex=True,gridspec_kw={'height_ratios':[2,1]})
    for (label,e),color in zip(curves.items(),['#91969b','#253851','#147d92','#c78333']):
        axes[0].plot(e.index,e,label=label,color=color,lw=1.8)
        axes[1].plot(e.index,e/e.cummax().clip(lower=1)-1,color=color,lw=1.2)
    axes[0].set_title('Momentum refinements: better fitted results, incomplete robustness',loc='left',fontsize=14)
    axes[0].set_ylabel('Portfolio value / starting capital');axes[0].legend(frameon=False,fontsize=9)
    axes[1].set_ylabel('Drawdown');axes[1].yaxis.set_major_formatter(PercentFormatter(1))
    for ax in axes:ax.grid(alpha=.2);ax.spines[['top','right']].set_visible(False)
    fig.text(.07,.017,'2017–Sep 2026 • Net of fees and slippage • Current SET100 snapshot • Retrospective, not a forward validation',fontsize=9)
    fig.tight_layout(rect=[0,.04,1,1]);fig.savefig(FOLDERS[0]/'comparison.png',dpi=170);plt.close(fig)
    report=['# Multi-horizon momentum challenge','',
        '**Historical improvement found; no refinement passed every robustness requirement.** The 15-stock buffered variant with 5% target cash returned 304.77% versus 262.29% for the original, while maximum drawdown fell from 14.79% to 14.50%. The 10% cash version traded some return for a larger drawdown reduction. Both failed strict dominance when delaying fills or excluding THAI. They are experimental alternatives, not replacements proven superior.','',
        '## Results after trading costs','',
        'Evaluation: January 2017–September 28, 2026; THB1 million initial capital. Net compounded returns, including unrealized ending holdings; no hypothetical final-sale charge. Benchmark is equal-initial-allocation buy-and-hold of the fixed current 100-name snapshot, BANPU excluded/cash—not the official SET100 index.','',
        '| Strategy | Total return | CAGR | Max drawdown | THB1m becomes | Average invested |',
        '|---|---:|---:|---:|---:|---:|']
    for _,r in metrics.query("period=='full' and cost_profile=='base'").iterrows():
        report.append(f'| {r.strategy} | {r.total_return:.2%} | {r.cagr:.2%} | {r.max_drawdown:.2%} | {1e6*(1+r.total_return):,.0f} | {r.mean_exposure:.2%} |')
    report+=['','The 5% and 10% reserves are target minimums at scheduled rebalances. Actual cash is often higher because the market filter switches off or fewer stocks qualify; weights drift between rebalances.','',
        '## The rule','',
        '1. Rank the mean cross-sectional percentile of adjusted-price returns over 63, 126 and 252 sessions, skipping the latest 21 sessions.',
        '2. Require positive 252-session skipped-month momentum, price above its 200-session average, 253 observed bars, positive current volume and 20-session median turnover of at least THB10m.',
        '3. Use the same equal-weight market proxy and 200-session market trend filter as the original; its universe has the same current-membership bias.',
        '4. At each 21-session rebalance, retain previously targeted names still ranked within the top 20 eligible stocks. Fill vacancies from the ranking until holding at most 15 names. The rank buffer aims to reduce unnecessary replacement. It tracks desired membership; actual fills can be delayed or skipped.',
        '5. Target 95%/15 = 6.333% per selected stock, leaving at least 5% target cash. The cautious variant uses 90%/15 = 6%. Unused slots stay cash. Signals use the close; orders execute at the following calendar-session open if actually tradable, otherwise they are skipped until the next scheduled target.',
        '', 'The monthly wording is approximate: schedules are anchored every 21 union-panel sessions, not calendar month-end. No shorting or leverage. No stop-loss or intraday execution is assumed.','',
        '## Recent and expensive-execution checks','',
        '| Strategy | 2024–Sep2026 return | Recent max drawdown | Full stress return | Full stress max drawdown |',
        '|---|---:|---:|---:|---:|']
    for label in metrics.strategy.unique():
        recent=metrics.query("strategy==@label and period=='recent' and cost_profile=='base'").iloc[0]
        stress=metrics.query("strategy==@label and period=='full' and cost_profile=='stress'").iloc[0]
        report.append(f'| {label} | {recent.total_return:.2%} | {recent.max_drawdown:.2%} | {stress.total_return:.2%} | {stress.max_drawdown:.2%} |')
    report+=['','Base costs: commission 0.15% + exchange/clearing/regulatory fees 0.007%, plus VAT7% on those fees = **0.16799% per side**, and modeled slippage **0.10% per side**. Stress: 0.27499% fees, 0.20% slippage, THB50 daily minimum commission before VAT. Cash earns zero. These are representative published rates, not a measured broker average. [Kasikorn fee schedule](https://www.kasikornsecurities.com/en/startinvesting/fee/thai-stocks); [DBS fee schedule](https://login.settrade.com/brokerpage/004/web/Commission-General.html). Both rechecked September29,2026. Present-day rates are held constant across historical dates.','',
        '## Where the advantage fails','',
        'Same-cost comparison after perturbing BOTH strategies. All numbers below use the full period. Buffered variants remain higher-return in all four scenarios, but their drawdowns are worse under delayed execution and THAI exclusion. The gate demanded both improvements in every scenario, so neither qualifies for promotion.','',
        '| Scenario | Original return / DD | Buffered 5% return / DD | Buffered 10% return / DD |',
        '|---|---:|---:|---:|']
    audits=pd.read_csv(folder/'sensitivity_results.csv')
    for scenario,label in [('delay','One additional execution session'),('exclude_DELTA','Exclude DELTA'),('exclude_THAI','Exclude THAI'),('phase10','Shift rebalance schedule +10 sessions')]:
        a=audits[(audits.scenario.eq(scenario))&audits.period.eq('full')].set_index('candidate')
        x=a.loc[list(EXAMPLES)[0]];y=a.loc[list(EXAMPLES)[1]]
        report.append(f'| {label} | {x.incumbent_total_return:.2%} / {x.incumbent_max_drawdown:.2%} | {x.total_return:.2%} / {x.max_drawdown:.2%} | {y.total_return:.2%} / {y.max_drawdown:.2%} |')
    report+=['','The 5% prototype is highlighted after examining full-period results because it has the highest return among the five variants passing the normal and stress comparisons. The 10% version illustrates a lower-exposure tradeoff. This is descriptive post-selection; neither is the predeclared robust winner.','',
        '## Search history and reproducibility','',
        '- Batch1: 223 new variants; one passed the 2017–2023 screen. It failed later strict comparison (higher stress drawdown, slightly worse recent base drawdown).',
        '- Batch2: 12 adaptive cash-reserve variants; five passed the screen and normal/stress comparisons. All failed at least one robustness requirement.',
        '- Batch3: 36 adaptive staggered-rebalance variants; two passed the screen, both failed full-period return requirements. No further tuning after this batch.',
        '- **271 new specifications, 552 total including the earlier281.** The SQLite registry contains additional comparator, period, cost and verification evaluations; those are not new strategies.',
        '- Shortlists were written before examining their recent/full results within each batch. All dates were previously seen, and later batches were informed by earlier outcomes. No claim of an untouched holdout or statistical significance is justified.',
        '- The original five active strategies remain in `strategy/active.json`. The optional experimental module can reproduce either buffered variant; rejected standalone modules were not added.',
        '', '[Every new trial and reason](../../research/experiments/REFINEMENT_LEDGER.md) · [Combined numeric ledger](../../research/experiments/STRATEGY_LEDGER.csv) · [Comparison metrics](comparison.csv) · [Yearly returns](annual_returns.csv) · [Sensitivity details](../momentum_reserve_20260929/sensitivity_results.csv)','',
        '```bash',
        '.venv/bin/python -m backtest.run --strategy experimental_buffered_momentum --accept-snapshot-bias --output reports/buffered_new_run',
        '.venv/bin/python -m backtest.run --strategy experimental_buffered_momentum --params \'{"reserve":0.10}\' --accept-snapshot-bias --output reports/buffered10_new_run',
        '.venv/bin/python -m backtest.run --strategy experimental_buffered_momentum --cost-profile stress --accept-snapshot-bias --output reports/buffered_stress_new_run',
        '```','',
        'Verification: saved-module CLI reproductions match the search equity curves within 1e-12. Independent cash-and-position replay of 12 exported ledgers (three portfolios × full/recent × base/stress) reproduces ending and daily equity within 1e-9. Causality, exclusion, sizing, delayed execution, fees and canonical identity are covered by the project tests.','',
        '## Limits on the conclusion','',
        'Repeated selection can fit noise. Current SET100 membership introduces survivorship bias; historical membership intervals and delisted price histories are not yet implemented. Provider adjusted OHLC uses fractional units, approximate liquidity and stale marks through data gaps, with incomplete corporate-action and suspension reconciliation. BANPU remains quarantined. No board lots, tick grids, price-limit queues or market-impact capacity model. Dividends are reflected only through adjusted prices and are not separately credited. The snapshot buy-and-hold basket is not the official index.','',
        '**Conclusion:** the requested higher-return/lower-drawdown pair exists in the fitted backtest, but a reliable improvement over multi-horizon momentum has not been established. Freeze these definitions before future paper evaluation; dates after September28,2026 are reserved.','',
        '![Equity and drawdown](comparison.png)']
    (FOLDERS[0]/'RESULTS.md').write_text('\n'.join(report)+'\n')
    print('Published 271 new trials; combined ledger 552; independently replayed',len(verification),'ledgers')
    print('Maximum replay error:',max(r['max_equity_error'] for r in verification))


if __name__=='__main__':main()
