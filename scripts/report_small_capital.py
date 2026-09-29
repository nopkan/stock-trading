"""Independently reconcile the chosen lot ledger and publish the capital study."""
import json
import hashlib
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
from research.portfolio import ROOT, Panel, FeeSchedule
from research.small_capital import LotData
from scripts.research_small_capital import OUT


def main():
    selection=json.loads((OUT/'selection.json').read_text());candidate=selection['candidate']
    all_results=pd.read_csv(OUT/'all_results.csv');chosen=all_results[all_results.candidate.eq(candidate)]
    base=chosen[(chosen.scenario=='base')&(chosen.period=='full')].iloc[0]
    curve=pd.read_csv(OUT/candidate/'base_full_equity.csv',index_col='date',parse_dates=True).equity
    fills=pd.read_csv(OUT/candidate/'base_full_fills.csv',parse_dates=['date'])
    daily=pd.read_csv(OUT/candidate/'base_full_daily.csv',index_col='date',parse_dates=True)
    original=Panel.load();index=pd.read_csv(ROOT/'data/indices/set100_tradingview_daily.csv',index_col='date',parse_dates=True).close
    dates=index.loc[original.dates[0]:original.dates[-1]].index
    p=Panel({s:f.reindex(dates) for s,f in original.frames.items()},original.exclusions|{'THAI'},original.source_hashes);d=LotData(p)
    cfg=json.loads((ROOT/'configs/thai_trading_costs.json').read_text());fee=FeeSchedule(**cfg['base'])
    cash=30000.;shares=np.zeros(len(p.symbols));groups={date:f for date,f in fills.groupby('date')};max_error=0.
    holdings=[]
    for date in curve.index:
        i=p.dates.get_loc(date);shares*=d.actions[i];daynotional=0.
        g=groups.get(date)
        if g is not None:
            for window in ('morning','close'):
                trades=g[g.window.eq(window)];cash_before=cash
                buys=trades[trades.side.eq('buy')]
                assert float((buys.notional_thb+buys.variable_fee_thb).sum())<=cash_before+1e-6
                for r in trades.itertuples():
                    assert r.shares>0 and r.shares%100==0
                    assert np.isclose(r.shares*r.price_proxy,r.notional_thb)
                    j=p.symbols.index(r.symbol);sign=1 if r.side=='buy' else -1
                    shares[j]+=sign*r.shares;cash-=sign*r.notional_thb+r.variable_fee_thb;daynotional+=r.notional_thb
            cash-=fee.daily_minimum_topup(daynotional,1.)
        assert cash>=-1e-6 and shares.min()>=-1e-6
        nav=cash+shares@d.marks[i];err=abs(nav-curve.loc[date]*30000);max_error=max(max_error,err)
        np.testing.assert_allclose(nav,curve.loc[date]*30000,rtol=1e-10,atol=1e-6)
        np.testing.assert_allclose(cash,daily.loc[date,'cash_thb'],atol=1e-6)
    for symbol,q,mark in zip(p.symbols,shares,d.marks[p.dates.get_loc(curve.index[-1])]):
        if q>1e-8:holdings.append({'symbol':symbol,'shares_including_action_residuals':q,'auction_salable_shares':int(q//100)*100,
            'odd_lot_shares':q%100,'mark':mark,'value_thb':q*mark})
    pd.DataFrame(holdings).to_csv(OUT/'ending_holdings.csv',index=False)
    reproduced=pd.read_csv(OUT/'reproduction/equity.csv',index_col='date',parse_dates=True).strategy
    np.testing.assert_allclose(curve,reproduced,atol=1e-12)
    bench=pd.read_csv(OUT/'benchmark_full.csv',index_col='date',parse_dates=True).equity
    baseline=index.loc[index.index<curve.index[0]].iloc[-1]
    curves=pd.DataFrame({'Strategy':curve,'Fractional_price_basket':bench,'SET100_price':index.reindex(curve.index)/baseline})
    prev=pd.Series(1.,index=curves.columns);annual=[]
    for year,g in curves.groupby(curves.index.year):
        row={'year':year}
        for col in curves:
            row[col]=g[col].iloc[-1]/prev[col]-1
        annual.append(row);prev=g.iloc[-1]
    annual=pd.DataFrame(annual);annual.to_csv(OUT/'annual_returns.csv',index=False)
    verification={'maximum_cash_ledger_nav_error_thb':max_error,'fills_checked':len(fills),
        'whole_lot_orders':bool(fills.shares.mod(100).eq(0).all()),'no_same_window_sale_funding':True,
        'saved_module_reproduces_curve':True,'capital_thb':30000,'candidate':candidate,
        'old_integer_float_aliases_preserved_in':'research/experiments/CANDIDATE_ALIASES.json',
        'current_engine_sha256':hashlib.sha256((ROOT/'research/small_capital.py').read_bytes()).hexdigest(),
        'note':'Parameter-validation guards were added after the bounded run; independent saved-module replay reproduces the full equity curve exactly. Original run hashes remain unchanged.'}
    (OUT/'verification.json').write_text(json.dumps(verification,indent=2))
    fig,axes=plt.subplots(2,1,figsize=(12,7.5),sharex=True,gridspec_kw={'height_ratios':[2,1]})
    for col,color,label in zip(curves,['#087E8B','#9B6A3D','#607080'],['THB30k affordable momentum','Fractional price-only basket','SET100 price index']):
        s=curves[col];axes[0].plot(s.index,s*30000,color=color,label=label)
        axes[1].plot(s.index,s/s.cummax().clip(lower=1)-1,color=color)
    axes[0].set_title('THB30,000 changes the investable strategy',loc='left',fontsize=16);axes[0].set_ylabel('Portfolio value / normalized index (THB)');axes[0].legend(frameon=False)
    axes[1].set_ylabel('Drawdown');axes[1].yaxis.set_major_formatter(PercentFormatter(1))
    for ax in axes:ax.grid(alpha=.18);ax.spines[['top','right']].set_visible(False)
    fig.text(.09,.015,'Price-only, after modeled costs | Cash dividends excluded | Current-universe bias | Daily-price proxies, not verified auction fills',fontsize=8)
    fig.tight_layout(rect=[0,.04,1,1]);fig.savefig(OUT/'comparison.png',dpi=170);plt.close(fig)
    pretty=lambda x:f'{x:+.2%}'
    lines=['# One strategy candidate for THB30,000','',
        '**Selected for further validation, not ready for live money:** SET100 Affordable Buffered Momentum, candidate `'+candidate+'`. Starting capital THB30,000. The user has not selected a broker or drawdown threshold. No live order routing or recurring trading task has been enabled.','',
        'The earlier +304.77% return was a THB1m fractional adjusted-unit result. It does not establish what a THB30,000 whole-lot account can achieve. This study changes capital, sizing, calendar, exclusions and accounting; its return is price-only and excludes cash dividends. The two headline results are not directly comparable.','',
        '## Locked rules','',
        '1. Use completed daily adjusted prices for equal-weight percentile ranks of 63-, 126- and 252-session momentum, skipping the latest 21 sessions.',
        '2. Require at least 253 observed closes, positive recent volume, 20-session median turnover of THB10m, positive skipped-year momentum and price above SMA200.',
        '3. At every 21-session scheduled decision, require the equal-weight market proxy above SMA200; otherwise target cash.',
        '4. Use **15 target slots**, with **90% total target allocation**: approximately **6% per slot**. Starting at THB30,000 that is THB1,800 per slot before costs. Screen out stocks whose board lot cannot fit. Select the highest-ranked affordable stocks; keep prior targets still within the top 20 eligible affordable names.',
        '5. Round orders down to whole lots. Leave unused allocations as cash. Target quantities are fixed from pre-auction information and are not enlarged using the eventual opening price.',
        '6. Reconcile and retry legitimate residuals at the next permitted window; do not finance buys from unconfirmed sells in the same auction. Do not trade three times just because three checks occur.',
        '7. No fixed stop-loss or daily confirmed-market exit was selected. The tested daily-exit alternatives were not superior under the declared robustness rule. A portfolio halt is a separate risk policy; the user threshold remains unset and has no performance claim here.','',
        'Fifteen slots does not guarantee fifteen actual holdings. Cash, unaffordable lots and corporate-action residuals change the actual count. No margin or short sales. This study retains BANPU and THAI exclusions.','',
        '## Results for the chosen candidate','',
        '| Scenario | Full return | CAGR | Max drawdown | 2024–Sep2026 return | Recent drawdown |','|---|---:|---:|---:|---:|---:|']
    for scenario in chosen.scenario.drop_duplicates():
        f=chosen[(chosen.scenario==scenario)&(chosen.period=='full')].iloc[0];r=chosen[(chosen.scenario==scenario)&(chosen.period=='recent')].iloc[0]
        lines.append(f'| {scenario} | {pretty(f.total_return)} | {pretty(f.cagr)} | {f.max_drawdown:.2%} | {pretty(r.total_return)} | {r.max_drawdown:.2%} |')
    lines+=['',f"Base ending value: **THB{(1+base.total_return)*30000:,.0f}**, from THB30,000. Explicit modeled fees: **THB{base.fees_fraction_initial_capital*30000:,.0f}**. Average invested exposure: **{base.mean_exposure:.1%}**. Largest single holding weight: **{base.max_single_weight:.1%}**. Slippage is already in trade prices. Cash earns zero.",'',
        f"The same-exclusion, fractional price-only basket returned **{pretty(base.benchmark_total_return)}**, CAGR **{pretty(base.benchmark_cagr)}**, with **{base.benchmark_drawdown:.2%} drawdown**. It is an idealized comparison, not a 100-stock portfolio executable with THB30,000. SET100 price is shown separately in the figure and annual table.",'',
        'Base explicit fees are 0.16799% per side plus 0.10% slippage. `minimum_fee` adds THB50 minimum daily commission before VAT; `higher_cost` uses 0.27499% explicit fees, 0.20% slippage and that minimum. Fees aggregate by day, not per order/window. Higher fees can change affordable lots and later holdings, so stress results need not be monotonic.','',
        'The candidate passed all 20 full/recent comparisons against the stated basket, with a declared −25% drawdown research screen. That screen is not a promised drawdown limit or the user’s accepted risk. Worst tested drawdown was approximately −21.70%; future losses may be larger.','',
        '![Capital-constrained result](comparison.png)','',
        '## All nine candidates, including rejected refinements','',
        '| Candidate | Full base return | CAGR | Max DD | Worst full CAGR across scenarios | Passed all screens? |','|---|---:|---:|---:|---:|---|']
    for score in selection['scores']:
        r=all_results[(all_results.candidate==score['candidate'])&(all_results.scenario=='base')&(all_results.period=='full')].iloc[0]
        lines.append(f"| {score['name']} | {pretty(r.total_return)} | {pretty(r.cagr)} | {r.max_drawdown:.2%} | {pretty(score['min_full_cagr'])} | {'Yes' if score['passes'] else 'No'} |")
    lines+=['','The 5- and 8-stock variants had larger drawdowns. The highest headline return was not selected. Exactly eight capital-aware variants and the original reference were evaluated, across ten scenarios and two periods: **180 evaluations**. Every result and rejection is retained; the grid was not expanded after seeing results.','',
        '## Annual price-only returns','',
        '| Year | Selected strategy | Fractional basket | SET100 price |','|---|---:|---:|---:|']
    for r in annual.itertuples():lines.append(f'| {r.year}{" YTD" if r.year==2026 else ""} | {pretty(r.Strategy)} | {pretty(r.Fractional_price_basket)} | {pretty(r.SET100_price)} |')
    lines+=['','## Three-window operating design','',
        '| Bangkok time | Check and intended action |','|---|---|',
        '| 09:45–before 09:55 | Previous completed-day signal; size morning ATO using confirmed cash, actual board lots and current exchange metadata |',
        '| 13:45–before 13:55 | Reconcile morning fills/cancellations and buying power; retry valid residuals via afternoon ATO |',
        '| 16:30–before 16:35 | Final same-day reconciliation and justified residual/risk orders via ATC |','',
        'The actual exchange session and broker acceptance cutoff must override the clock. A late ATO can become a continuous-session market order. Order-status monitoring must continue between windows. A final daily close cannot be used to decide an order executed in that same closing auction. Holidays, halts, stale data, duplicate orders and uncertain broker acknowledgements must prevent new submissions.','',
        '**Only daily open/close proxies were backtested. There is no historical afternoon auction fill claim.** The three-window design has no broker implementation yet, as requested while choosing the strategy first.','',
        '## What still prevents live readiness','',
        '- Actual historical auction prices, volume, indicative quotes, partial-fill behavior and afternoon data are absent.',
        '- Historical SET100 effective membership, exited/delisted stocks, two missing stock sessions and entity continuity still need repair. All tested history was already seen.',
        '- Prices were reconstructed by reversing provider-reported subsequent split ratios. This is a mathematical transformation, not observed exchange tape. Provider stock-dividend/rights classifications, entitlement dates and share delivery are not fully verified.',
        '- A uniform 100-share order lot is a conservative assumption. SET can use 50 shares for qualifying high-priced stocks; actual historical/current lot metadata is required. Cash dividends, withholding, payment dates, subscriptions and terminal liquidation are excluded.',
        f"- Corporate actions leave **THB{base.ending_odd_lot_value_thb:,.2f}** of odd-lot/fractional residual value at the base endpoint. These balances are marked, not silently sold in auctions. A pure auction-only system needs an explicit residual exit process.",
        '- Broker/API support, actual fee minimum, account settlement/buying-power rules and the user’s drawdown limit remain unknown.',
        '- A frozen forward paper test, including missed/duplicate messages, reconnects and partial fills, has not happened. More tuning of known history cannot replace it.','',
        '## Reproduce and audit','',
        '```bash','.venv/bin/python -m backtest.small_capital --capital 30000 --accept-snapshot-bias --output reports/my_30000_run','```','',
        'Use `--cost-profile minimum_fee` or `--cost-profile stress` in a new output folder. The saved module is `strategy/set100_small_capital.py`; its settings are `configs/set100_selected_strategy.json`. Neither enables live orders.','',
        f"Independent ledger replay checked **{len(fills):,} fills**, verified every submitted quantity is a multiple of 100, and reconstructed NAV with maximum error **THB{max_error:.9f}**. Buy spending never used proceeds from sells in the same auction. The saved module reproduces the selected equity curve exactly.",'',
        '- [All evaluations](all_results.csv), [selection and failures](selection.json), [plan/data/code provenance](manifest.json), [verification](verification.json), [ending holdings and odd lots](ending_holdings.csv).',
        '- [SET hours](https://www.set.or.th/en/market/information/trading-procedure/trading-hours), [order types](https://www.set.or.th/en/market/information/trading-procedure/order-types), [lot sizes](https://www.set.or.th/en/market/information/trading-procedure/trading-units), [split-adjusted provider convention](https://github.com/ranaroussi/yfinance/issues/1749).',
        '- [Official DELTA split example](https://www.set.or.th/en/market/news-and-alert/newsdetails?id=2023046335&symbol=DELTA): the provider shows approximately THB74.80 on April 27, 2023; reversing the next day’s 10-for-1 split gives approximately THB748.00. Treating THB74.80 as the original quote would falsely make the stock affordable in a small historical portfolio.','']
    (OUT/'REPORT.md').write_text('\n'.join(lines))
    print(json.dumps(verification,indent=2))


if __name__=='__main__':main()
