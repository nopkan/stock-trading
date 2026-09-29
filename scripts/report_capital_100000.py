"""Publish the THB100k search including the failed extended robustness audit."""
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
from research.portfolio import ROOT
from scripts.research_capital_100000 import OUT


def main():
    s = json.loads((OUT/'selection.json').read_text())
    audit = json.loads((OUT/'audit_summary.json').read_text())
    manifest = json.loads((OUT/'manifest.json').read_text())
    verification = json.loads((OUT/'verification.json').read_text())
    results = pd.read_csv(OUT/'all_results.csv')
    phase = pd.read_csv(OUT/'rebalance_phase_audit.csv')
    chosen = results[results.candidate.eq(s['candidate'])]
    base = chosen[(chosen.scenario=='base')&(chosen.period=='full')].iloc[0]
    full = results[(results.scenario=='base')&(results.period=='full')].sort_values('total_return',ascending=False)
    recent = results[(results.scenario=='base')&(results.period=='recent')].set_index('candidate')
    def curve(candidate):
        return pd.read_csv(OUT/candidate/'base_full_equity.csv',index_col='date',parse_dates=True).equity
    c = curve(s['candidate'])
    benchmark = pd.read_csv(OUT/'benchmark_full.csv',index_col='date',parse_dates=True).equity
    index = pd.read_csv(ROOT/'data/indices/set100_tradingview_daily.csv',index_col='date',parse_dates=True).close
    curves = pd.DataFrame({'Candidate':c,'Original_at_100k':curve('e9a522bb24938501'),
                          'Fractional_price_basket':benchmark,
                          'SET100_price':index.reindex(c.index)/index.loc[index.index<c.index[0]].iloc[-1]})
    rows=[];previous=pd.Series(1.,index=curves.columns)
    for year,g in curves.groupby(curves.index.year):
        rows.append({'year':year,**(g.iloc[-1]/previous-1).to_dict()});previous=g.iloc[-1]
    annual=pd.DataFrame(rows);annual.to_csv(OUT/'annual_returns.csv',index=False)
    rows=[];previous=pd.Series(1.,index=curves.columns)
    for month,g in curves.groupby(curves.index.to_period('M')):
        rows.append({'month':str(month),**(g.iloc[-1]/previous-1).to_dict()});previous=g.iloc[-1]
    pd.DataFrame(rows).to_csv(OUT/'monthly_returns.csv',index=False)
    fig,axes=plt.subplots(2,1,figsize=(12,7.5),sharex=True,gridspec_kw={'height_ratios':[2,1]})
    labels=['Selected run: timing-sensitive','Original recipe at THB100k','Fractional price-only basket','SET100 price index']
    colors=['#007D83','#8B5CF6','#A5743C','#637584']
    for col,label,color in zip(curves,labels,colors):
        v=curves[col]
        axes[0].plot(v.index,v*100000,label=label,color=color,lw=1.5)
        axes[1].plot(v.index,v/v.cummax().clip(lower=1)-1,color=color,lw=1.3)
    axes[0].set_title('THB100,000 search: favourable run, failed timing robustness',loc='left',fontsize=15)
    axes[0].set_ylabel('Account / normalized index (THB)');axes[0].legend(frameon=False,fontsize=9)
    axes[1].set_ylabel('Drawdown');axes[1].yaxis.set_major_formatter(PercentFormatter(1))
    for ax in axes: ax.grid(alpha=.2);ax.spines[['top','right']].set_visible(False)
    fig.text(.09,.012,'2017–28 Sep 2026 | Fees/slippage included, cash dividends excluded | Current-universe bias | Daily proxies, not certified auction fills',fontsize=8)
    fig.tight_layout(rect=[0,.04,1,1]);fig.savefig(OUT/'comparison.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(2,1,figsize=(11,6.5),sharex=True)
    axes[0].bar(phase.phase,phase.total_return,color=['#C95238' if i==0 else '#4A8792' for i in phase.phase])
    axes[0].axhline(3.0477,color='#B8342F',ls='--',label='Requested +304.77%')
    axes[0].axhline(phase.total_return.median(),color='#233E4D',ls=':',label='Median start offset')
    axes[0].set_title('Same strategy, all 42 rebalance start offsets',loc='left',fontsize=15)
    axes[0].set_ylabel('Total return');axes[0].legend(frameon=False,fontsize=9)
    axes[1].bar(phase.phase,phase.max_drawdown,color='#B65C4A');axes[1].axhline(-.25,color='#233E4D',ls='--')
    axes[1].set_ylabel('Max drawdown');axes[1].set_xlabel('Start offset in trading sessions; original run = 0')
    for ax in axes: ax.yaxis.set_major_formatter(PercentFormatter(1));ax.grid(axis='y',alpha=.2);ax.spines[['top','right']].set_visible(False)
    fig.tight_layout();fig.savefig(OUT/'phase_sensitivity.png',dpi=160);plt.close(fig)
    fmt=lambda v:f'{v:+.2%}'
    lines=['# THB100,000: search for approximately +304.77%','',
      '**Outcome: a historical target-beating candidate was found, but it failed the extended robustness audit. It is not approved for live funding.**',
      '',f"The frozen three-stock high-proximity candidate `{s['candidate']}` returned **{fmt(base.total_return)}** after modeled fees/slippage, turning THB100,000 into **THB{100000*(1+base.total_return):,.2f}** over January 4, 2017–September 28, 2026. CAGR was **{fmt(base.cagr)}**, maximum drawdown **{base.max_drawdown:.2%}**. These are fitted historical, price-only results, not a forecast.",
      '',f"Across all 42 rebalance offsets, total returns ranged from **{fmt(audit['phase_min_return'])} to {fmt(audit['phase_max_return'])}**, median **{fmt(audit['phase_median_return'])}**. Only **{audit['phases_reaching_304_77']} of 42** reached +304.77%; the worst drawdown was **{audit['phase_worst_drawdown']:.2%}**. The original offset happened to be the best. The return target is therefore not stable across scheduling choices.",
      '',f"The largest three profit contributors—{', '.join(audit['top_profit_names'])}—accounted for **{audit['top3_fraction_of_net_profit']:.1%}** of net profit. Removing those names and rerunning produced **{fmt(audit['additional_diagnostics'][0]['total_return'])}**, with **{audit['additional_diagnostics'][0]['max_drawdown']:.2%}** drawdown. This exclusion is a diagnostic, not a proposed stock blacklist.",
      '', '![All rebalance offsets](phase_sensitivity.png)', '',
      '## Exact frozen rules', '',
      '1. Rank eligible stocks by adjusted close divided by the maximum adjusted close over the trailing 252 sessions, including today’s completed close. Higher means nearer the one-year high. Exact ties follow the saved universe’s alphabetical order.',
      '2. Eligibility requires 253 observed closes, an actual positive-volume bar, 20-session median turnover of at least THB10m, positive 252-session momentum skipping the latest 21 sessions, and adjusted close above SMA200. BANPU and THAI stay excluded.',
      '3. Rebalance every 42 exchange-index sessions, anchored to the saved panel calendar starting '+str(index.loc[index.index>=pd.Timestamp('2016-01-01')].index[0].date())+'. This fixed anchor is part of the reported result.',
      '4. Target three affordable stocks at 95% / 3 = 31.67% each before purchase friction. Retain prior desired names still among the best eight eligible affordable names, then fill empty slots. Leave unaffordable/unfilled allocations in cash; do not borrow.',
      '5. Require the equal-weight market proxy above SMA200 at a scheduled rebalance. Also target cash after three consecutive completed sessions below that market average; execute at the next permitted observed window. Re-entry waits for a scheduled rebalance. This is a market-regime exit, not a guaranteed stop-loss or an individual-stock stop.',
      '6. Use whole 100-share orders, prior-close sizing, a 35% cash funding envelope, and a prior-turnover participation limit. Do not finance purchases from unconfirmed sales in the same auction. Retry valid residuals at the close using the already-decided quantities.',
      '',f"Three slots are not three continuously held stocks. Average exposure was **{base.mean_exposure:.1%}**; one position reached **{base.max_single_weight:.1%}** of account value between rebalances. There were **{int(base.fills)} fills** and **THB{100000*base.fees_fraction_initial_capital:,.2f}** in explicit fees. Slippage is embedded in fills. End values do not deduct hypothetical terminal liquidation costs.",
      '', '## Costs and execution assumptions', '',
      'Base modeled explicit charges: commission 0.15% + exchange/clearing/regulatory charges totaling 0.007%, plus 7% VAT = **0.16799% per side**. Add **0.10% slippage per side**. The separate minimum-fee case applies THB50 daily commission before VAT; higher-cost uses 0.25% commission, the same levies/VAT, 0.20% slippage and THB50 daily minimum. These are representative published schedules, not a broker quote or a historical market-wide average. [DBS fee schedule](https://login.settrade.com/brokerpage/004/web/Commission-General.html).',
      '', '100-share order lots are assumed conservatively throughout. SET has qualifying 50-share exceptions; their historical eligibility is not validated here. [SET trading units](https://www.set.or.th/en/market/information/trading-procedure/trading-units).',
      '', 'Three daily operating checks remain the intended design. Only daily morning-open and closing-price proxies were tested; afternoon auction execution is untested. Same-day closing prices never determine orders filled at that close. Actual auction queues, tick grids, broker cutoffs and historical cash-settlement permissions are not modeled. [SET trading hours](https://www.set.or.th/en/market/information/trading-procedure/trading-hours).',
      '', '## Frozen shortlist sensitivities for this candidate', '',
      '| Scenario | Full return | CAGR | Max DD | 2024–Sep2026 cold-start return |',
      '|---|---:|---:|---:|---:|']
    for scenario in chosen.scenario.drop_duplicates():
        f=chosen[(chosen.scenario==scenario)&(chosen.period=='full')].iloc[0]
        r=chosen[(chosen.scenario==scenario)&(chosen.period=='recent')].iloc[0]
        lines.append(f'| {scenario} | {fmt(f.total_return)} | {fmt(f.cagr)} | {f.max_drawdown:.2%} | {fmt(r.total_return)} |')
    lines += ['', 'The original predeclared shortlist screen passed: all 20 full/recent cases beat their matching fractional basket and stayed above −25% drawdown. **That preliminary pass is superseded by the failed all-offset and actual-contributor audits.** The −25% screen is a research criterion, not the user’s accepted loss limit. The original `selection.json` is retained to show the sequence; `final_decision.json` records the final status.',
      '', 'The `exclude_top3` scenario removes the earlier project’s leaders DELTA/RCL/KCE; the subsequent audit instead removes this candidate’s actual leaders RCL/JMART/STECON. They are different tests. Other sensitivity scenarios are individual changes, not simultaneous worst-case combinations.',
      '', '## Comparable baselines', '',
      '| Portfolio | Full return | Max drawdown |','|---|---:|---:|']
    for name,candidate in [('New candidate','60ee10de14d6268a'),('Original 15-stock recipe at THB100k','e9a522bb24938501'),('Previous affordable 15-stock recipe at THB100k','b142b3be5b992c7b')]:
        r=full[full.candidate.eq(candidate)].iloc[0];lines.append(f'| {name} | {fmt(r.total_return)} | {r.max_drawdown:.2%} |')
    ix=curves.SET100_price;ixdd=(ix/ix.cummax().clip(lower=1)-1).min()
    lines += [f'| Fractional price-only buy-and-hold basket | {fmt(base.benchmark_total_return)} | {base.benchmark_drawdown:.2%} |',
              f'| SET100 price index | {fmt(ix.iloc[-1]-1)} | {ixdd:.2%} |', '',
      'The fractional basket is an idealized benchmark, not a 100-stock portfolio executable at THB100k. SET100 price excludes dividends and index investment costs. Cash dividends are excluded from the new strategy and basket; they are neither reinvested nor credited to cash. The old +304.77% result used dividend-adjusted fractional units, different exclusions/calendar and THB1m capital. It is a numerical target here, not an apples-to-apples return comparison.',
      '', '![Base curves](comparison.png)', '', '## Annual returns of the favourable run', '',
      '| Year | New candidate | Original at THB100k | Fractional price basket | SET100 price |', '|---|---:|---:|---:|---:|']
    for r in annual.itertuples():
        lines.append(f'| {r.year}{" YTD" if r.year==2026 else ""} | {fmt(r.Candidate)} | {fmt(r.Original_at_100k)} | {fmt(r.Fractional_price_basket)} | {fmt(r.SET100_price)} |')
    lines += ['', '## Every tested recipe', '',
      'The plan was frozen before this batch: **150 parameter variants of five previously explored ranking ideas plus two references = 152 recipes**. Each received full/recent base evaluations. Eight shortlisted recipes then received nine additional scenarios × two periods: **448 search/sensitivity evaluations**. Existing definitions were retested because the user changed capital to THB100,000. These are not 150 independent economic discoveries.',
      '', 'The frozen candidate then received **45 further diagnostic runs**: 40 previously untested rebalance offsets, two actual-profit-leader exclusions, and three cold-start blocks. Two other offsets reused existing results; one cold-start block repeats the recent-period check. A separate CLI replay and two independent ledger reconstructions verify accounting. No additional recipe was selected using those diagnostics.',
      '', '| Candidate | Ranking | Slots | Rebalance | Market exit days | Full return | Max DD | Recent return | Status |',
      '|---|---|---:|---:|---:|---:|---:|---:|---|']
    shortlisted=set(json.loads((OUT/'shortlist.json').read_text())['candidates'])
    for r in full.itertuples():
        status='Failed extended audit' if r.candidate==s['candidate'] else ('Shortlisted, not final' if r.candidate in shortlisted else 'Not shortlisted')
        lines.append(f'| `{r.candidate}` | {r.ranking} | {r.top_n} | {r.rebalance} | {r.daily_exit} | {fmt(r.total_return)} | {r.max_drawdown:.2%} | {fmt(recent.loc[r.candidate,"total_return"])} | {status} |')
    lines += ['', 'The numerically highest return was **+643.99%** from the related three-stock strategy without the daily market exit; it failed even the initial timing/drawdown screen. It was not selected. Recipe IDs link to exact settings in `manifest.json`; all evaluations are retained in `all_results.csv` and the project SQLite registry. Rejections are never erased.',
      '', '## Data limits and decision', '',
      'All history through September 28, 2026 has already been inspected. Yearly blocks and recent-period results are retrospective diagnostics, not untouched holdouts. Current SET100 membership creates survivorship bias; former members and effective-date membership are missing. Split reversal uses provider action ratios, not certified historical exchange quotes; mergers, stock dividends and entitlement dates need reconciliation. The stress removing complex actions reduces this candidate to +201.63%. Additional capital does not repair these issues.',
      '', '**Final decision: preserve this strategy as an experimental candidate, reject it as evidence of dependable +304.77% performance or readiness for live money.** The experiment meets the numerical target in a favourable retrospective run, but not consistently under rebalance timing and contributor tests. Future performance requires genuinely new forward observations and improved historical data; continuing to search this same history cannot establish certainty.',
      '', '## Reproduce and inspect', '', '```bash',
      '.venv/bin/python -m backtest.capital_ranked --accept-snapshot-bias --output reports/my_100000_replay',
      '```', '',
      'Frozen module: `strategy/set100_high_proximity_100000.py`; configuration: `configs/set100_100000_strategy.json`. Neither contains live order routing. The previous THB30k strategy and reports remain available as historical work.', '',
      f"Independent ledger replay reconstructed the selected run’s **{verification['ledger_replays'][0]['fills_checked']} fills** with maximum NAV error **THB{verification['ledger_replays'][0]['max_nav_error_thb']:.9f}**. Every submitted quantity is a multiple of 100; cash remained nonnegative and purchases did not use same-window sale proceeds. The CLI reproduction matches every saved equity observation.", '',
      '- [All evaluations](all_results.csv), [exact recipes and hashes](manifest.json), [original shortlist decision](selection.json), [final decision](final_decision.json).',
      '- [Phase audit](rebalance_phase_audit.csv), [additional diagnostics](additional_diagnostics.csv), [audit summary](audit_summary.json), [accounting verification](verification.json).',
      '- [Annual returns](annual_returns.csv), [monthly returns](monthly_returns.csv), [candidate attribution](60ee10de14d6268a/attribution.csv).','']
    (OUT/'REPORT.md').write_text('\n'.join(lines))
    decision={'candidate':s['candidate'],'capital_thb':100000,'numerical_base_target_met':bool(base.total_return>=3.0477),
              'preliminary_shortlist_screen_passed':s['research_gate_passed'],
              'extended_robustness_passed':False,'live_ready':False,
              'status':'experimental_candidate_failed_extended_robustness',
              'reason':'Strong dependence on rebalance offset and three profit contributors; no untouched history or verified auction data.',
              'base_return':float(base.total_return),'base_drawdown':float(base.max_drawdown),
              'phase_median_return':audit['phase_median_return'],'phase_worst_drawdown':audit['phase_worst_drawdown']}
    (OUT/'final_decision.json').write_text(json.dumps(decision,indent=2))
    config_path=ROOT/'configs/set100_100000_strategy.json';config=json.loads(config_path.read_text())
    config.update(status=decision['status'],preliminary_research_gate_passed=config.pop('research_gate_passed',s['research_gate_passed']),extended_robustness_passed=False)
    config_path.write_text(json.dumps(config,indent=2))
    ledger_path=ROOT/'research/experiments/STRATEGY_LEDGER.csv';ledger=pd.read_csv(ledger_path)
    mask=ledger.candidate.eq(s['candidate']);ledger.loc[mask,'status']='rejected_extended_robustness_100000'
    ledger.loc[mask,'reason']=json.dumps(decision,sort_keys=True);ledger.to_csv(ledger_path,index=False)
    print(json.dumps(decision,indent=2))


if __name__ == '__main__': main()
