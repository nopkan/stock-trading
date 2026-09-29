import numpy as np
import pandas as pd
from scripts.analyze_buffered_momentum import period_table, episodes


def test_continuous_period_returns_compound_and_include_first_loss():
    dates = pd.to_datetime(['2020-12-30','2021-01-04','2021-01-29','2021-02-01','2021-02-26','2022-01-04'])
    frame = pd.DataFrame({name:[1.,.8,.9,1.,1.1,1.21] for name in ['Strategy','Buy_hold','SET100_price']},index=dates)
    months, years = period_table(frame,'M'), period_table(frame,'Y')
    assert np.isclose(months.Strategy_drawdown.iloc[0],-.2)
    assert np.isclose(years.Strategy_return.iloc[0],.1)
    assert np.isclose(years.Strategy_return.iloc[1],.1)
    assert np.isclose((1+months.Strategy_return).prod()-1,.21)
    assert months.period.iloc[-1] == '2022-01'


def test_drawdown_crosses_year_boundary_and_records_recovery():
    series = pd.Series([1.,1.2,.9,1.1,1.2,1.08], index=pd.to_datetime(['2020-12-01','2020-12-30','2021-02-01','2021-03-01','2021-04-01','2021-05-01']))
    rows=episodes(series)
    assert np.isclose(rows[0]['drawdown'],-.25)
    assert rows[0]['peak']=='2020-12-30'
    assert rows[0]['recovery']=='2021-04-01'
    assert rows[1]['recovery']=='Unrecovered'
