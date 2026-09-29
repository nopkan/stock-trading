"""Causal portfolio research engine: real observed bars, adjusted fractional units.

Targets are chosen at a close, executed at the following calendar session's open.
Untradable orders are skipped and reconsidered at the next scheduled rebalance.
No leverage, no shorting, no filling missing OHLC. Stale close marks are explicit.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class FeeSchedule:
    commission_bps: float = 15
    exchange_bps: float = .5
    clearing_bps: float = .1
    regulatory_bps: float = .1
    vat: float = .07
    slippage_bps: float = 10
    minimum_daily_commission_thb: float = 0

    def __post_init__(self):
        if any(v < 0 or not np.isfinite(v) for v in self.__dict__.values()):
            raise ValueError('All cost inputs must be finite and nonnegative')
        if self.rate >= 1 or self.slippage_bps >= 10000:
            raise ValueError('Unreasonable cost inputs')

    @property
    def rate(self):
        return (self.commission_bps + self.exchange_bps + self.clearing_bps + self.regulatory_bps) / 10000 * (1 + self.vat)

    def daily_minimum_topup(self, traded_notional, capital):
        if traded_notional <= 0:
            return 0.0
        commission = traded_notional * self.commission_bps / 10000
        return max(0., self.minimum_daily_commission_thb / capital - commission) * (1 + self.vat)


class Panel:
    def __init__(self, frames, exclusions=(), source_hashes=None):
        self.symbols = list(frames)
        self.dates = pd.DatetimeIndex(sorted(set().union(*(f.index for f in frames.values()))))
        self.frames = frames
        self.exclusions = set(exclusions)
        self.source_hashes = source_hashes or {}
        self.close = pd.DataFrame({s: f.adj_close for s, f in frames.items()}, index=self.dates)
        self.open = pd.DataFrame({s: f.adj_open for s, f in frames.items()}, index=self.dates)
        self.high = pd.DataFrame({s: f.adj_high for s, f in frames.items()}, index=self.dates)
        self.low = pd.DataFrame({s: f.adj_low for s, f in frames.items()}, index=self.dates)
        self.volume = pd.DataFrame({s: f.volume for s, f in frames.items()}, index=self.dates)
        self.value = pd.DataFrame({s: f.close * f.volume for s, f in frames.items()}, index=self.dates)
        self.marks = self.close.ffill().fillna(0).to_numpy()
        self.opens = self.open.to_numpy()
        self.tradable = (self.open.notna() & self.close.notna() & self.volume.gt(0)).to_numpy(copy=True)
        for j, s in enumerate(self.symbols):
            if s in self.exclusions:
                self.tradable[:, j] = False
        self.openmarks = np.where(np.isfinite(self.opens), self.opens,
                                  np.vstack([np.zeros(len(self.symbols)), self.marks[:-1]]))

    @classmethod
    def load(cls):
        symbols = pd.read_csv(ROOT / 'data/universe/set100_snapshot.csv').symbol.tolist()
        exclusions = json.loads((ROOT / 'configs/data_exclusions.json').read_text())
        frames, hashes = {}, {}
        for s in symbols:
            p = ROOT / f'data/prices/{s}.csv'
            f = pd.read_csv(p, parse_dates=['date']).set_index('date')
            required = ['adj_open', 'adj_close', 'adj_high', 'adj_low', 'volume', 'close']
            if f.index.has_duplicates or not f.index.is_monotonic_increasing or not np.isfinite(f[required]).all().all():
                raise ValueError(f'Invalid input {s}')
            if (f[required[:-2]] <= 0).any().any() or (f.volume < 0).any():
                raise ValueError(f'Invalid price/volume {s}')
            frames[s] = f
            hashes[s] = hashlib.sha256(p.read_bytes()).hexdigest()
        return cls(frames, exclusions, hashes)


def summarize(dates, equity, fills, turnover, fees, exposure, max_weight):
    series = pd.Series(equity, index=dates)
    returns = np.diff(np.r_[1., equity]) / np.r_[1., equity[:-1]]
    years = max((dates[-1]-dates[0]).days / 365.25, 1/252)
    std = np.std(returns, ddof=1)
    return {'total_return': float(equity[-1]-1), 'cagr': float(equity[-1]**(1/years)-1),
        'max_drawdown': float(np.min(equity / np.maximum.accumulate(np.r_[1., equity])[1:] - 1)),
        'sharpe_rf0': float(returns.mean()/std*np.sqrt(252)) if std else 0.,
        'fills': int(fills), 'turnover_initial_capital': float(turnover),
        'fees_fraction_initial_capital': float(fees), 'mean_exposure': float(np.mean(exposure)),
        'max_single_weight': float(max_weight), 'sessions': len(equity)}, series


def simulate(panel, targets, start, end, costs=FeeSchedule(), capital=1_000_000., details=False):
    """targets: all-NaN row means no rebalance; other rows sum to at most 1.

    Sells first, then scale buys to available cash after fees and daily minimum.
    A deterministic transaction-cost reserve avoids borrowing at full allocation.
    """
    if not np.isfinite(capital) or capital <= 0:
        raise ValueError('Capital must be positive')
    targets = np.asarray(targets, dtype=float)
    if targets.shape != panel.opens.shape:
        raise ValueError('Targets shape must match panel')
    scheduled = ~np.isnan(targets).all(axis=1)
    rows = targets[scheduled]
    if not np.isfinite(rows).all() or (rows < 0).any() or (rows.sum(axis=1) > 1+1e-9).any():
        raise ValueError('Targets must be finite, nonnegative, unlevered')
    selection = np.flatnonzero((panel.dates >= pd.Timestamp(start)) & (panel.dates <= pd.Timestamp(end)))
    if len(selection) < 2:
        raise ValueError('Insufficient evaluation history')
    units, cash = np.zeros(len(panel.symbols)), 1.
    fee, slip = costs.rate, costs.slippage_bps/10000
    count, turnover, fee_total, max_weight = 0, 0., 0., 0.
    equity, exposure, trades = [], [], []
    minreserve = costs.minimum_daily_commission_thb / capital * (1+costs.vat)
    for i in selection:
        daily_notional = daily_fee = 0.
        if i > 0 and scheduled[i-1]:
            tradable = panel.tradable[i]
            price = panel.opens[i]
            opening_equity = cash + units @ panel.openmarks[i]
            budget = max(0., opening_equity-minreserve) / (1+fee+slip)
            desired = np.divide(targets[i-1] * budget, price, out=units.copy(), where=tradable)
            delta = np.where(tradable, desired-units, 0.)
            sell = np.maximum(-delta, 0.)
            sell_value = sell * np.nan_to_num(price) * (1-slip)
            cash += sell_value.sum()*(1-fee)
            units -= sell
            buy = np.maximum(delta, 0.)
            buy_value = buy * np.nan_to_num(price) * (1+slip)
            need = buy_value.sum()*(1+fee)
            scale = min(1., max(0., cash-minreserve)/need) if need > 0 else 0.
            buy *= scale
            buy_value *= scale
            cash -= buy_value.sum()*(1+fee)
            units += buy
            daily_notional = float(sell_value.sum()+buy_value.sum())
            daily_fee = daily_notional*fee + costs.daily_minimum_topup(daily_notional, capital)
            cash -= costs.daily_minimum_topup(daily_notional, capital)
            active = (sell+buy) > 1e-10
            count += int(active.sum())
            turnover += daily_notional
            fee_total += daily_fee
            if details:
                for j in np.flatnonzero(active):
                    isbuy = buy[j] > 0
                    trades.append({'date': str(panel.dates[i].date()), 'symbol': panel.symbols[j],
                        'side': 'buy' if isbuy else 'sell', 'adjusted_units': float((buy if isbuy else sell)[j]*capital),
                        'adjusted_price': float(price[j]*(1+slip if isbuy else 1-slip)),
                        'notional_thb': float((buy_value if isbuy else sell_value)[j]*capital),
                        'variable_fee_thb': float((buy_value if isbuy else sell_value)[j]*fee*capital)})
        if cash < -1e-9 or (units < -1e-9).any():
            raise ArithmeticError('Borrowing or short position detected')
        holding_value = units*panel.marks[i]
        total = cash+holding_value.sum()
        if not np.isfinite(total) or total <= 0:
            raise ArithmeticError('Invalid portfolio equity')
        equity.append(total)
        exposure.append(float(holding_value.sum()/total))
        max_weight = max(max_weight, float(holding_value.max()/total))
    result, curve = summarize(panel.dates[selection], np.array(equity), count, turnover, fee_total, exposure, max_weight)
    return result, curve, pd.DataFrame(trades)


def benchmark(panel, start, end, costs=FeeSchedule(), capital=1_000_000.):
    """Original 100 equal initial sleeves, once-only purchases; no rebalancing."""
    selection = np.flatnonzero((panel.dates >= pd.Timestamp(start)) & (panel.dates <= pd.Timestamp(end)))
    cash = np.full(len(panel.symbols), 1/len(panel.symbols))
    units = np.zeros(len(panel.symbols))
    bought = np.zeros(len(panel.symbols), dtype=bool)
    fee, slip = costs.rate, costs.slippage_bps/10000
    exposure, equities, turnover, fees, count, max_weight = [], [], 0., 0., 0, 0.
    # Original benchmark requires one earlier observed close to generate its signal.
    prior = panel.close.notna().cumsum().shift(1).fillna(0).to_numpy() > 0
    for i in selection:
        enter = panel.tradable[i] & ~bought & prior[i]
        if enter.any():
            # Reserve minimum top-up across buying sleeves so neither method borrows.
            reserve = costs.minimum_daily_commission_thb / capital*(1+costs.vat)
            budgets = np.maximum(0., cash[enter]-reserve/enter.sum())
            notionals = budgets/(1+fee)
            units[enter] = notionals/(panel.opens[i,enter]*(1+slip))
            extra = costs.daily_minimum_topup(float(notionals.sum()), capital)
            cash[enter] -= budgets + extra/enter.sum()
            bought[enter] = True
            turnover += notionals.sum()
            fees += notionals.sum()*fee+extra
            count += int(enter.sum())
        values = units*panel.marks[i]
        total = cash.sum()+values.sum()
        equities.append(total)
        exposure.append(values.sum()/total)
        max_weight = max(max_weight, values.max()/total)
    result, curve = summarize(panel.dates[selection], np.array(equities), count, turnover, fees, exposure, max_weight)
    return result, curve
