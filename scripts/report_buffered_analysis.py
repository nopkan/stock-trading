"""Readable report for the frozen buffered-momentum period analysis."""
import json
import pandas as pd
from scripts.analyze_buffered_momentum import OUT, NAMES


def main():
    s=json.loads((OUT/'summary.json').read_text())
    a=pd.read_csv(OUT/'annual_comparison.csv',dtype={'period':str})
    m=pd.read_csv(OUT/'monthly_comparison.csv')
    c=pd.read_csv(OUT/'annual_stock_contributions.csv')
    total=pd.read_csv(OUT/'stock_contributions.csv')
    audit=json.loads((OUT/'calendar_audit.json').read_text())
    f=lambda x:f'{x:+.2%}'
    lines=['# Buffered momentum: annual and monthly analysis','',
        '**Frozen strategy e9a522bb24938501 — 4 January 2017 to 28 September 2026.** No strategy parameters were changed or optimized for this report. September 2026 is a partial month; 2026 is year-to-date. Starting capital is THB1,000,000.','',
        'The strategy returned **+304.77% net**, versus **+99.67%** for our buy-and-hold basket and **+6.41%** for the SET100 **price** index. It beat the basket in 9 of 10 calendar periods and 69 of 117 months. It did not win consistently every month or avoid all losses.','',
        '**Benchmark distinction:** the basket holds equal initial allocations to the current SET100 snapshot, with later-listed names bought when available and BANPU left as cash. Its prices and the strategy prices are dividend-adjusted. The actual SET100 index changes membership and uses market-capitalization weights; the price index excludes dividends. Therefore excess return over SET100 price is descriptive, not a like-for-like total-return alpha measure. Full SET100 TRI history was not accessible from the public sources checked; it was not estimated.','',
        '| Portfolio | Total return | Annualized return | Maximum drawdown | Ending value, THB |',
        '|---|---:|---:|---:|---:|']
    for n,label in zip(NAMES,['Buffered momentum, net','Buy-and-hold basket, net','SET100 price index, no dividends/costs']):
        r=s[n]; lines.append(f"| {label} | {f(r['total_return'])} | {f(r['cagr'])} | {r['max_drawdown']:.2%} | {(1+r['total_return'])*1e6:,.0f} |")
    lines+=['','Index ending value is a normalized illustration, not an investable after-cost portfolio.','',
        '![Growth and drawdown](comparison.png)','',
        '## Annual comparisons','',
        'Returns compound from the previous calendar year’s closing value; the account is never reset in January. Gaps are percentage points (pp), not relative percentage changes.','',
        '| Year | Strategy, net | Basket, net | SET100 price | Gap vs basket, pp | Gap vs SET100 price, pp |',
        '|---|---:|---:|---:|---:|---:|']
    for _,r in a.iterrows():
        year=r.period+(' YTD' if r.period=='2026' else '')
        lines.append(f'| {year} | {f(r.Strategy_return)} | {f(r.Buy_hold_return)} | {f(r.SET100_price_return)} | {r.excess_buy_hold*100:+.2f} | {r.excess_SET100_price*100:+.2f} |')
    lines+=['','## Risk and costs by year','',
        'Within-year drawdown includes the prior December closing value as the starting anchor. This is different from the lifetime drawdown, whose peak may be in an earlier year. Exposure is the average fraction of portfolio value invested at each model close.','',
        '| Year | Strategy drawdown | Basket drawdown | Index drawdown | Mean invested | All-cash dates | Explicit fees, THB | Slippage, THB |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for _,r in a.iterrows():
        lines.append(f'| {r.period} | {r.Strategy_drawdown:.2%} | {r.Buy_hold_drawdown:.2%} | {r.SET100_price_drawdown:.2%} | {r.mean_exposure:.1%} | {int(r.cash_only_sessions)} | {r.fees_thb:,.0f} | {r.slippage_thb:,.0f} |')
    lines+=['','**Cost assumptions:** commission 0.15% plus exchange/clearing/regulatory charges of 0.007%, then 7% VAT: **0.16799% explicit fees per side**, plus **0.10% slippage per side**. These are representative published rates, held constant through history, not a measured average across Thai brokers. No minimum commission in the base case. Cash earns zero; taxes and terminal liquidation are not modeled.','',
        f"The strategy paid **THB{s['fees_thb']:,.0f} explicit fees** and **THB{s['slippage_thb']:,.0f} execution slippage** over 1,512 fills. Both are already reflected in the reported net returns; do not subtract them again. These cash totals are not the full compounded cost drag of a hypothetical fee-free strategy. The basket’s explicit fees were THB1,660 across 99 buys.",'',
        'Under the saved higher-cost case (0.27499% explicit fees plus 0.20% slippage per side and THB50 daily minimum commission before VAT), the same strategy returned **+262.47%**, with **−15.19% maximum drawdown**.','',
        '## What happened each year','']
    interpretations={
        '2017':'Almost fully invested. It only narrowly beat the basket and had a much larger within-year drawdown: the strategy was not safer in every year.',
        '2018':'The strategy lost money but lost substantially less than either benchmark. Reduced exposure helped, yet this year contains its deepest lifetime drawdown.',
        '2019':'It beat both benchmarks with moderate average exposure, although its within-year drawdown was worse than the basket’s.',
        '2020':'A major source of the advantage: strong selected-stock gains alongside long cash periods. The current-universe basket also rose while the actual price index fell, highlighting how different those benchmarks are.',
        '2021':'The strongest calendar year. It stayed approximately 95% invested and captured large gains among its selected momentum stocks.',
        '2022':'The weakest relative year versus the basket: near-zero net return, high exposure and substantial trading costs. Its drawdown also exceeded both benchmarks.',
        '2023':'A losing year, but losses were much smaller than the benchmarks. Cash periods reduced participation in the decline.',
        '2024':'A positive return despite low average exposure. Individual winners mattered; portfolio weights were allowed to drift between rebalances.',
        '2025':'It mostly avoided the benchmarks’ losses, holding cash for much of the year. It still ended slightly negative.',
        '2026':'A strong market rebound benefited both stock portfolios. The strategy’s advantage over the basket was only about one percentage point, much smaller than its gap versus the price index.'}
    for _,r in a.iterrows():
        stocks=c[c.year.eq(int(r.period))].sort_values('return_contribution',ascending=False)
        leaders=', '.join(f'{x.symbol} {x.return_contribution*100:+.2f} pp' for x in stocks.head(3).itertuples())
        loser=stocks.iloc[-1]
        lines.append(f"- **{r.period}{' YTD' if r.period=='2026' else ''}:** {interpretations[r.period]} Largest net contributions: {leaders}. Largest detractor: {loser.symbol} {loser.return_contribution*100:+.2f} pp.")
    lines+=['','Contributions are actual marked stock P&L, including each stock’s transaction costs, divided by the portfolio’s starting value for that year. They sum to the strategy’s annual return; they are not each stock’s standalone percentage return.','',
        '## Monthly consistency','',
        f"- **54 positive, 34 negative and 29 flat months** out of {s['months']}. Flat months reflect cash exposure in this zero-interest model.",
        '- Beat the basket in **69/117 months (59.0%)**; beat SET100 price in **74/117 months (63.2%)**.',
        f"- Best month: **{s['best_month']['period']} {f(s['best_month']['Strategy_return'])}**. Worst month: **{s['worst_month']['period']} {f(s['worst_month']['Strategy_return'])}**.",
        f"- In months when SET100 price fell, average monthly returns were strategy **{f(s['average_month_when_index_down']['Strategy'])}**, basket **{f(s['average_month_when_index_down']['Buy_hold'])}**, index **{f(s['average_month_when_index_down']['SET100_price'])}**.",
        f"- In months when SET100 price rose, averages were strategy **{f(s['average_month_when_index_up']['Strategy'])}**, basket **{f(s['average_month_when_index_up']['Buy_hold'])}**, index **{f(s['average_month_when_index_up']['SET100_price'])}**. Its defensive behavior can miss part of a rally.",
        f"- Worst/best rolling 12-month strategy returns at month-end: **{f(s['Strategy']['worst_rolling_12m'])} / {f(s['Strategy']['best_rolling_12m'])}**. The final endpoint is September 28, not a full September month-end.",'',
        'Monthly conditional averages above are simple averages, not compounded capture ratios.','',
        '![Every month, all three series](monthly_heatmap.png)','',
        '## Drawdown, recovery and concentration','',
        '- Deepest strategy drawdown: **−14.50%**, from the January 29, 2018 peak to October 24, 2018. It recovered on July 25, 2019: **542 calendar days** after the peak.',
        '- A shallower **−9.44%** drawdown starting February 21, 2023 did not recover until November 7, 2024: **625 days**. Lower drawdown does not mean a quick recovery.',
        '- The basket’s deepest drawdown was **−37.98%**; SET100 price fell **−45.02%** from its 2018 peak and had not regained that peak by September 28, 2026.',
        f"- Average invested exposure: **{s['mean_exposure']:.2%}**. Entirely in cash on **744/2,370 model dates (31.4%)**. The 5% reserve is a target at rebalancing, not a guarantee that only 5% stays in cash.",
        '- Equal target weights are about 6.33% per stock, but the largest observed stock weight reached **15.40%** between rebalances. Winners can become concentrated.',
        '- There is **no fixed stop-loss or daily trailing stop** in this recipe. Exits depend on the scheduled momentum/trend/market checks and next-session tradability. Maximum historical drawdown is not a guaranteed loss limit.','',
        '| Largest net P&L contributors | THB | Share of total net profit |','|---|---:|---:|']
    for r in total.head(10).itertuples():
        lines.append(f'| {r.symbol} | {r.net_pnl_thb:,.0f} | {r.net_pnl_thb/(s["Strategy"]["total_return"]*1e6):.1%} |')
    lines+=['','The top three contributed about 29% of net profit. This is accounting attribution, not an estimate of the result if those stocks had been excluded; replacement holdings would change the path.','',
        '## Calendar audit and limits','',
        'The stock provider includes seven zero-volume placeholder dates on official 2026 exchange holidays: May 1, May 4, June 1, June 3, July 28, July 29 and August 12. No frozen-strategy fills occurred on them. For daily comparison only, SET100’s prior observed close is carried on those dates and `index_observed=False` identifies them. All monthly and annual boundaries have actual index observations. No market prices were invented.','',
        f"A separate same-parameter replay removing those seven dates returned **{f(audit['Strategy']['total_return'])}** with **{audit['Strategy']['max_drawdown']:.2%} drawdown**, versus the frozen +304.77% / −14.50%. The basket was unchanged. The holiday counting issue has only a small effect in this particular replay; the primary tables preserve the exact result you asked about. This is a diagnostic rerun of the same candidate, not another optimized strategy.",'',
        'Two actual index sessions, January 13, 2017 and January 2, 2024, have no stock-panel observations. The frozen portfolio’s previous value is carried only for the comparison chart and flagged `portfolio_observed=False`; stock bars and trades were not invented. Index drawdown uses all actual index sessions. Monthly/yearly endpoints are unaffected, but the original strategy’s indicator and execution history remains subject to these missing observations. The seven-holiday replay does not repair these missing stock sessions.','',
        'The fixed current membership creates survivorship and selection bias. The actual index has historical constituent changes. BANPU is quarantined; some entity histories are short; THAI’s suspension/restructure history is a sensitivity concern. The engine uses fractional adjusted units and simplified fills, without board lots, tick-size restrictions, market impact or a complete tradability history. Stale marks can understate risk. Dividends are represented through adjusted prices, not a separate tax-aware cash ledger.','',
        'The strategy was selected after 552 recipes had been examined. No dates through September 28, 2026 are untouched. It failed the earlier strict requirement to improve both return and drawdown under every sensitivity scenario. These results describe a fitted historical candidate; they do not establish it as the best future strategy.','',
        '## Data, reproducibility and verification','',
        '- [SET100 series at TradingView](https://www.tradingview.com/symbols/SET-SET100/): 5,000 daily bars retrieved September 29, 2026. Today’s incomplete bar is excluded.',
        '- [Independent year-end checkpoints](https://www.ivglobal.co.th/uploads/research/260105.pdf): SET100 2024 close 1,959.79 and 2025 close 1,788.35. [Latest historical checkpoint](https://www.investing.com/indices/set-100-historical-data): September 28, 2026 close 2,317.78.',
        '- [SET100 methodology](https://www.set.or.th/en/market/index/set100/profile), [TRI explanation](https://www.set.or.th/en/market/index/tri/profile), [official holidays](https://www.set.or.th/en/about/event-calendar/holiday), [fee source](https://www.kasikornsecurities.com/en/startinvesting/fee/thai-stocks).',
        '- Daily cash/holdings replay agrees with the frozen equity curve within floating-point tolerance. Stock P&L sums to daily portfolio P&L. Compounded monthly returns reconcile to annual and full-period returns for all three series.',
        '- [Data hashes and source metadata](provenance.json), [annual CSV](annual_comparison.csv), [monthly CSV](monthly_comparison.csv), [daily comparison](daily_comparison.csv), [daily exposure/costs](daily_diagnostics.csv), [annual stock attribution](annual_stock_contributions.csv), [drawdown episodes](drawdown_episodes.csv), [calendar replay](calendar_audit.json).',
        '- Reproduce with `.venv/bin/python -m scripts.analyze_buffered_momentum`, then `scripts.audit_buffered_calendar` and `scripts.report_buffered_analysis` using the same module invocation. Frozen source files are unchanged.','',
        '## Every month','',
        '| Month | Strategy, net | Basket, net | SET100 price | Gap vs basket, pp | Gap vs index, pp |','|---|---:|---:|---:|---:|---:|']
    for r in m.itertuples():
        lines.append(f'| {r.period}{" partial" if r.period=="2026-09" else ""} | {f(r.Strategy_return)} | {f(r.Buy_hold_return)} | {f(r.SET100_price_return)} | {r.excess_buy_hold*100:+.2f} | {r.excess_SET100_price*100:+.2f} |')
    (OUT/'REPORT.md').write_text('\n'.join(lines)+'\n')
    print(OUT/'REPORT.md')


if __name__=='__main__':main()
