"""Period analysis of frozen e9a522bb24938501; no optimization or new trials."""
from pathlib import Path
import hashlib
import json
import re
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
from research.portfolio import ROOT, Panel

OUT = ROOT / 'reports/buffered_momentum_deep_dive_20260929'
SAVED = ROOT / 'reports/momentum_reserve_20260929'
ID = 'e9a522bb24938501'
CAPITAL = 1_000_000.
NAMES = ['Strategy', 'Buy_hold', 'SET100_price']


def period_table(curves, frequency):
    """Continuous-account returns, anchored to the preceding period close."""
    rows = []
    previous = curves.iloc[0]
    for key, group in curves.iloc[1:].groupby(curves.index[1:].to_period(frequency)):
        row = {'period': str(key), 'start_boundary': previous.name.strftime('%Y-%m-%d'),
               'end_date': group.index[-1].strftime('%Y-%m-%d'), 'sessions': len(group)}
        for name in curves:
            path = pd.concat([pd.Series([previous[name]], index=[previous.name]), group[name]])
            row[name + '_start'] = previous[name]
            row[name + '_end'] = group[name].iloc[-1]
            row[name + '_return'] = group[name].iloc[-1] / previous[name] - 1
            row[name + '_drawdown'] = (path / path.cummax() - 1).min()
        row['excess_buy_hold'] = row['Strategy_return'] - row['Buy_hold_return']
        row['excess_SET100_price'] = row['Strategy_return'] - row['SET100_price_return']
        rows.append(row)
        previous = group.iloc[-1]
    return pd.DataFrame(rows)


def ledger_diagnostics(panel, curve, fills):
    """Replay actual fills and attribute marked P&L, including execution costs."""
    holdings = pd.Series(0., index=panel.symbols)
    previous_values = holdings.copy()
    cash = CAPITAL
    groups = {pd.Timestamp(d): g for d, g in fills.groupby('date')}
    records, contributions = [], []
    for date, equity in curve.items():
        trades = pd.Series(0., index=panel.symbols)
        fees = pd.Series(0., index=panel.symbols)
        slip, notional, count = 0., 0., 0
        if date in groups:
            group = groups[date]
            signs = group.side.map({'buy': 1., 'sell': -1.})
            units = (group.adjusted_units * signs).groupby(group.symbol).sum()
            holdings.loc[units.index] += units
            signed = (group.notional_thb * signs).groupby(group.symbol).sum()
            trades.loc[signed.index] = signed
            fee = group.variable_fee_thb.groupby(group.symbol).sum()
            fees.loc[fee.index] = fee
            cash -= trades.sum() + fees.sum()
            opens = panel.open.loc[date, group.symbol].to_numpy()
            slip = float((group.adjusted_units.to_numpy() * np.abs(group.adjusted_price.to_numpy() - opens)).sum())
            notional, count = group.notional_thb.sum(), len(group)
        values = holdings * panel.marks[panel.dates.get_loc(date)]
        nav = cash + values.sum()
        np.testing.assert_allclose(nav, equity * CAPITAL, rtol=1e-10, atol=1e-5)
        pnl = values - previous_values - trades - fees
        contributions.append(pnl.rename(date))
        records.append({'date': date, 'equity_thb': nav, 'cash_thb': cash,
                        'exposure': values.sum() / nav, 'stocks': int((values > 1e-5).sum()),
                        'max_stock_weight': values.max() / nav, 'fees_thb': fees.sum(),
                        'slippage_thb': slip, 'traded_notional_thb': notional, 'fills': count})
        previous_values = values
    daily = pd.DataFrame(records).set_index('date')
    pnl = pd.DataFrame(contributions)
    np.testing.assert_allclose(pnl.sum(axis=1), daily.equity_thb.diff().fillna(daily.equity_thb.iloc[0] - CAPITAL), atol=1e-5)
    return daily, pnl


def episodes(series):
    peak, peak_date, current = series.iloc[0], series.index[0], None
    result = []
    for date, value in series.items():
        if value >= peak:
            if current:
                current.update(recovery=date.strftime('%Y-%m-%d'), calendar_days=(date-current.pop('_peak')).days)
                result.append(current)
                current = None
            peak, peak_date = value, date
        else:
            dd = value / peak - 1
            if current is None:
                current = {'peak': peak_date.strftime('%Y-%m-%d'), '_peak': peak_date, 'trough': date.strftime('%Y-%m-%d'), 'drawdown': dd}
            if dd < current['drawdown']:
                current.update(trough=date.strftime('%Y-%m-%d'), drawdown=dd)
    if current:
        current.update(recovery='Unrecovered', calendar_days=(series.index[-1]-current.pop('_peak')).days)
        result.append(current)
    return sorted(result, key=lambda r:r['drawdown'])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    raw = ROOT / 'data/sources/index_research/tradingview_set100_frames.json'
    messages = [json.loads(x) for f in json.loads(raw.read_text()) for x in re.split(r'~m~\d+~m~', f) if x.startswith('{')]
    bars = [b['v'][:5] for m in messages if m.get('m') == 'timescale_update' for b in m['p'][1]['s1']['s']]
    index = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close'])
    index['date'] = pd.to_datetime(index.pop('timestamp'), unit='s', utc=True).dt.tz_convert('Asia/Bangkok').dt.tz_localize(None).dt.normalize()
    index = index.set_index('date').sort_index()
    assert not index.index.has_duplicates and (index.close > 0).all()
    # Published independent checkpoints; fail loudly on symbol/date mismatch.
    for d, value in [('2024-12-30',1959.79), ('2025-12-30',1788.35), ('2026-09-28',2317.78)]:
        assert np.isclose(index.loc[d, 'close'], value, atol=.005), (d, index.loc[d, 'close'])
    index = index.loc[:'2026-09-28']  # Exclude today's incomplete, delayed bar.
    price_path = ROOT / 'data/indices/set100_tradingview_daily.csv'
    price_path.parent.mkdir(exist_ok=True)
    index.to_csv(price_path)
    paths = {'Strategy': SAVED/ID/'full_base_equity.csv', 'Buy_hold': SAVED/'benchmark_full_base.csv'}
    curves = pd.DataFrame({n:pd.read_csv(p,index_col='date',parse_dates=True).equity for n,p in paths.items()})
    anchor = index.loc[index.index < curves.index[0]].index[-1]
    assert anchor == pd.Timestamp('2016-12-30')
    non_sessions = curves.index.difference(index.index)
    holidays = pd.to_datetime(['2026-05-01','2026-05-04','2026-06-01','2026-06-03','2026-07-28','2026-07-29','2026-08-12'])
    assert non_sessions.equals(pd.DatetimeIndex(holidays)), 'Unexpected missing index observations'
    # Known SET holidays have zero-volume Yahoo placeholder rows. Preserve the
    # frozen strategy calculation; carry the prior observed index mark ONLY on
    # these verified closures, explicitly flagged in the exported daily file.
    index_marks = index.close.reindex(index.index.union(curves.index)).ffill()
    curves['SET100_price'] = index_marks.reindex(curves.index)
    frozen_curve = curves.Strategy.copy()
    portfolio_observed = curves.index.copy()
    missing_stock_dates = index.loc[curves.index[0]:curves.index[-1]].index.difference(curves.index)
    curves.loc[anchor] = [1., 1., index.loc[anchor,'close']]
    curves = curves.sort_index()
    # Include every actual index session for index risk measures. The frozen
    # portfolio has no observations on two sessions: carry its last mark and
    # identify these explicitly, without inventing tradable stock bars.
    curves = curves.reindex(curves.index.union(index.loc[anchor:curves.index[-1]].index)).ffill()
    curves['SET100_price'] = index_marks.reindex(curves.index)
    curves.assign(index_observed=curves.index.isin(index.index),portfolio_observed=curves.index.isin(portfolio_observed)).to_csv(OUT/'daily_comparison.csv', index_label='date')
    fills = pd.read_csv(SAVED/ID/'full_base_fills.csv', parse_dates=['date'])
    assert not fills.date.isin(non_sessions).any()
    daily, pnl = ledger_diagnostics(Panel.load(), frozen_curve, fills)
    daily.to_csv(OUT/'daily_diagnostics.csv')
    pnl.to_csv(OUT/'daily_stock_pnl_thb.csv', index_label='date')
    annual, monthly = period_table(curves,'Y'), period_table(curves,'M')
    for table, freq, filename in [(annual,'Y','annual_comparison.csv'),(monthly,'M','monthly_comparison.csv')]:
        groups = daily.groupby(daily.index.to_period(freq))
        for key, group in groups:
            i = table.index[table.period.eq(str(key))][0]
            table.loc[i,'sessions'] = len(group)  # original model calendar
            for col in ['fees_thb','slippage_thb','traded_notional_thb','fills']:
                table.loc[i,col] = group[col].sum()
            table.loc[i,'mean_exposure'] = group.exposure.mean()
            table.loc[i,'cash_only_sessions'] = group.stocks.eq(0).sum()
            table.loc[i,'max_stock_weight'] = group.max_stock_weight.max()
        table.to_csv(OUT/filename,index=False)
    annual_pnl = pnl.groupby(pnl.index.year).sum()
    contributions=[]
    for year, row in annual_pnl.iterrows():
        start = annual.loc[annual.period.eq(str(year)), 'Strategy_start'].iloc[0]*CAPITAL
        for symbol,value in row.items():
            contributions.append({'year':year, 'symbol':symbol, 'net_pnl_thb':value,'return_contribution':value/start})
    pd.DataFrame(contributions).to_csv(OUT/'annual_stock_contributions.csv', index=False)
    total_pnl = pnl.sum().sort_values(ascending=False)
    total_pnl.rename('net_pnl_thb').to_csv(OUT/'stock_contributions.csv',index_label='symbol')
    drawdowns = {n:episodes(curves[n]) for n in NAMES}
    pd.DataFrame([{'portfolio':n,**r} for n,rows in drawdowns.items() for r in rows]).to_csv(OUT/'drawdown_episodes.csv',index=False)
    summary = {'start':'2017-01-04','end':'2026-09-28','candidate':ID,'months':len(monthly),
               'fees_thb':daily.fees_thb.sum(), 'slippage_thb':daily.slippage_thb.sum(),
               'mean_exposure':daily.exposure.mean(), 'cash_only_sessions':int(daily.stocks.eq(0).sum()),
               'sessions':len(daily),'positive_months':int(monthly.Strategy_return.gt(1e-12).sum()),
               'flat_months':int(monthly.Strategy_return.abs().lt(1e-12).sum()),
               'winning_months_buy_hold':int(monthly.excess_buy_hold.gt(0).sum()),
               'winning_months_SET100_price':int(monthly.excess_SET100_price.gt(0).sum()),
               'winning_years_buy_hold':int(annual.excess_buy_hold.gt(0).sum()),
               'winning_years_SET100_price':int(annual.excess_SET100_price.gt(0).sum()),
               'drawdowns':{n:rows[:5] for n,rows in drawdowns.items()}}
    years = (curves.index[-1]-curves.index[1]).days/365.25
    for n in NAMES:
        normalized = curves[n]/curves[n].iloc[0]
        summary[n] = {'total_return':normalized.iloc[-1]-1, 'cagr':normalized.iloc[-1]**(1/years)-1,
                      'max_drawdown':(normalized/normalized.cummax()-1).min()}
        rolling = normalized.resample('ME').last().pct_change(12).dropna()
        summary[n]['worst_rolling_12m'] = rolling.min()
        summary[n]['best_rolling_12m'] = rolling.max()
    down = monthly.SET100_price_return < 0
    summary['average_month_when_index_down'] = {n:monthly.loc[down,n+'_return'].mean() for n in NAMES}
    summary['average_month_when_index_up'] = {n:monthly.loc[~down,n+'_return'].mean() for n in NAMES}
    summary['best_month'] = monthly.loc[monthly.Strategy_return.idxmax(),['period','Strategy_return']].to_dict()
    summary['worst_month'] = monthly.loc[monthly.Strategy_return.idxmin(),['period','Strategy_return']].to_dict()
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2))
    hashes = {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [raw,price_path,*paths.values(),SAVED/ID/'full_base_fills.csv',ROOT/'configs/thai_trading_costs.json']}
    provenance = {'retrieved':'2026-09-29','source':'https://www.tradingview.com/symbols/SET-SET100/',
        'transport':'Public unauthenticated TradingView chart stream, SET:SET100, daily, 5000 bars',
        'series':'SET100 price index, not SET100FF, not TRI; excludes dividends; index has no execution costs',
        'downloaded_last_date':'2026-09-29','retained_last_date':'2026-09-28',
        'retained_first_date':str(index.index[0].date()),'baseline_date':str(anchor.date()),
        'checkpoint_sources':['https://www.ivglobal.co.th/uploads/research/260105.pdf','https://www.investing.com/indices/set-100-historical-data'],
        'checks':'2024-12-30=1959.79; 2025-12-30=1788.35; 2026-09-28=2317.78. All month/year boundaries have observed index closes.',
        'holiday_marks': [str(d.date()) for d in non_sessions],
        'holiday_method':'Seven zero-volume Yahoo holiday rows remain in frozen strategy calculations; index prior close carried only on these verified SET closures, no strategy fills on them. They can still affect indicator/rebalance session counting. Model sessions include these rows.',
        'holiday_source':'https://www.set.or.th/en/about/event-calendar/holiday',
        'missing_stock_calendar_dates':[str(d.date()) for d in missing_stock_dates],
        'missing_stock_calendar_method':'2017-01-13 and 2024-01-02 have observed index bars but no panel stock observations. Frozen portfolio values are carried only for the comparison chart and flagged portfolio_observed=False. No new bars/trades invented. Full actual index calendar is used for index drawdown.',
        'TRI_status':'Full SET100 TRI history could not be retrieved from public sources; not estimated or substituted.',
        'sha256':hashes}
    (OUT/'provenance.json').write_text(json.dumps(provenance,indent=2))
    (price_path.parent/'set100_tradingview_provenance.json').write_text(json.dumps(provenance,indent=2))
    # Multiplication must reproduce every annual and full-period return.
    for n in NAMES:
        np.testing.assert_allclose((1+monthly[n+'_return']).prod()-1,summary[n]['total_return'],atol=1e-12)
        for _,a in annual.iterrows():
            np.testing.assert_allclose((1+monthly.loc[monthly.period.str.startswith(a.period),n+'_return']).prod()-1,a[n+'_return'],atol=1e-12)
    fig, axes = plt.subplots(2,1,figsize=(12,8),sharex=True,gridspec_kw={'height_ratios':[2,1]})
    labels=['Buffered momentum · net','Buy-and-hold basket · net','SET100 price index · no dividends']
    colors=['#007e87','#936138','#637181']
    for n,label,color in zip(NAMES,labels,colors):
        series=curves[n]/curves[n].iloc[0]
        axes[0].plot(series.index,series*100,label=label,color=color,lw=1.7)
        axes[1].plot(series.index,series/series.cummax()-1,color=color,lw=1.1)
    axes[0].set_title('Buffered momentum: where the advantage came from',loc='left',fontsize=16)
    axes[0].set_ylabel('Starting value = 100'); axes[0].legend(frameon=False,fontsize=9)
    axes[1].set_ylabel('Drawdown'); axes[1].yaxis.set_major_formatter(PercentFormatter(1))
    for ax in axes: ax.grid(alpha=.18); ax.spines[['top','right']].set_visible(False)
    fig.text(.09,.015,'4 Jan 2017–28 Sep 2026 | Fixed current stock universe; retrospective selection. Index excludes dividends.',fontsize=9)
    fig.tight_layout(rect=[0,.04,1,1]); fig.savefig(OUT/'comparison.png',dpi=170); plt.close(fig)
    fig,axes=plt.subplots(3,1,figsize=(13,10))
    for ax,n,label in zip(axes,NAMES,labels):
        z=monthly.assign(year=monthly.period.str[:4],month=monthly.period.str[5:].astype(int)).pivot(index='year',columns='month',values=n+'_return').reindex(columns=range(1,13))
        ax.imshow(z.to_numpy(),cmap='RdYlGn',vmin=-.15,vmax=.15,aspect='auto')
        for i in range(len(z)):
            for j in range(12):
                v=z.iloc[i,j]
                if pd.notna(v): ax.text(j,i,f'{v:.1%}',ha='center',va='center',fontsize=8)
        ax.set_xticks(range(12),['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'])
        ax.set_yticks(range(len(z)),z.index);ax.set_title(label,loc='left',fontsize=12)
    fig.suptitle('Monthly returns · September 2026 ends on September 28',fontsize=15)
    fig.tight_layout();fig.savefig(OUT/'monthly_heatmap.png',dpi=170);plt.close(fig)
    (OUT/'workbook_inputs.json').write_text(json.dumps({'annual':annual.to_dict('records'),'monthly':monthly.to_dict('records'), 'summary':summary,'provenance':provenance,'top_stocks':total_pnl.head(10).to_dict()},indent=2))
    print(annual[['period','Strategy_return','Buy_hold_return','SET100_price_return','Strategy_drawdown','mean_exposure']].to_string(index=False))
    print(json.dumps(summary,indent=2))


if __name__ == '__main__':
    main()
