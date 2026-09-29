import importlib
import numpy as np
import pandas as pd
import pytest

from backtest.engine import Costs, metrics, simulate
from strategy.indicators import rsi
from scripts.download_data import normalize


def bars(opens, closes=None, volumes=None):
    closes = opens if closes is None else closes
    return pd.DataFrame({"open": opens, "close": closes,
        "high": np.maximum(opens, closes), "low": np.minimum(opens, closes),
        "volume": volumes if volumes is not None else [1000] * len(opens)},
        index=pd.date_range("2020-01-01", periods=len(opens)))


def test_next_open_and_exit_gap():
    prices = bars([100, 120, 150], [110, 130, 160])
    signal = pd.Series([1, 0, 0], index=prices.index)
    equity, fills, trades = simulate(prices, signal, "2020", "2021", Costs(0, 0))
    assert equity.equity.tolist() == pytest.approx([1, 130/120, 150/120])
    assert fills.iloc[0]['date'] == prices.index[1]
    assert trades.net_return.iloc[0] == pytest.approx(0.25)


def test_round_trip_costs_and_first_day_drawdown():
    prices = bars([100, 100, 100])
    signal = pd.Series([1, 0, 0], index=prices.index)
    curve, _, trades = simulate(prices, signal, "2020", "2021", Costs(20, 10))
    expected = ((1-.001)*(1-.002))/((1+.001)*(1+.002))
    assert curve.equity.iloc[-1] == pytest.approx(expected)
    assert trades.net_return.iloc[0] == pytest.approx(expected-1)
    assert metrics(curve.equity)['max_drawdown'] == pytest.approx(expected-1)


def test_zero_volume_does_not_fill_and_no_forced_final_sale():
    prices = bars([100, 200, 300], volumes=[1, 0, 1])
    signal = pd.Series([1, 1, 0], index=prices.index)
    curve, fills, trades = simulate(prices, signal, "2020", "2021", Costs(0, 0))
    assert len(fills) == 1 and fills.iloc[0]['date'] == prices.index[2]
    assert trades.empty and curve.exposure.iloc[-1] == 1


def test_warmup_can_signal_but_cannot_earn_before_evaluation():
    prices = bars([10, 20, 30, 40])
    signal = pd.Series([1, 1, 1, 1], index=prices.index)
    curve, fills, _ = simulate(prices, signal, "2020-01-03", "2021", Costs(0, 0))
    assert curve.equity.tolist() == pytest.approx([1, 40/30])
    assert fills.iloc[0]['adjusted_price'] == 30


def test_rsi_flat_up_down():
    assert rsi(pd.Series([1.] * 20)).iloc[-1] == 50
    assert rsi(pd.Series(range(20), dtype=float)).iloc[-1] == 100
    assert rsi(pd.Series(range(20, 0, -1), dtype=float)).iloc[-1] == 0
    assert rsi(pd.Series(range(20), dtype=float)).iloc[:14].isna().all()


def test_adjustment_preserves_overnight_ratios_and_no_dividend_double_count():
    raw = pd.DataFrame({'Open': [100., 90.], 'High': [100., 90.], 'Low': [100., 90.],
        'Close': [100., 90.], 'Adj Close': [90., 90.], 'Volume': [1000, 1000], 'Dividends': [0., 10.]},
        index=pd.date_range('2020-01-01', periods=2, tz='Asia/Bangkok'))
    _, clean, invalid = normalize(raw)
    assert invalid == 0
    assert clean.adj_open.tolist() == [90, 90]
    assert clean.dividends.tolist() == [0, 10]


def test_invalid_data_and_signals_rejected():
    prices = bars([100, 100])
    with pytest.raises(ValueError):
        simulate(prices, pd.Series([1, np.nan], index=prices.index), '2020', '2021')
    with pytest.raises(ValueError):
        Costs(-1, 0)


def test_missing_date_has_no_invented_execution():
    prices = bars([100, 120, 140]).iloc[[0, 2]]
    signal = pd.Series([1, 0], index=prices.index)
    _, fills, _ = simulate(prices, signal, '2020', '2021', Costs(0, 0))
    assert fills.date.tolist() == [pd.Timestamp('2020-01-03')]
