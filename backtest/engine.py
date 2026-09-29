from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Costs:
    fee_bps: float = 20.0
    slippage_bps: float = 10.0

    def __post_init__(self):
        if not (0 <= self.fee_bps < 10000 and 0 <= self.slippage_bps < 10000):
            raise ValueError("Costs must be between 0 and 10000 basis points")


def simulate(prices, signals, start, end, costs=Costs()):
    """One normalized cash sleeve; fractional adjusted units, marked at close.

    No rebalancing while held. Fees/slippage applied on each transition.
    Warmup signals may initiate at the first evaluation open. Zero-volume bars
    cannot execute. Missing sessions aren't generated. End positions stay open.
    """
    if not signals.index.equals(prices.index) or not signals.isin([0, 1]).all():
        raise ValueError("Signals must align exactly and contain only 0/1")
    desired = signals.shift(1).fillna(0)
    frame = prices.loc[start:end]
    cash, units, entry, roundtrips = 1.0, 0.0, None, []
    rows, fills = [], []
    fee, slip = costs.fee_bps / 10000, costs.slippage_bps / 10000
    for date, bar in frame.iterrows():
        want = desired.loc[date]
        if bar.volume > 0:
            if want == 1 and units == 0:
                price = bar.open * (1 + slip)
                units = cash / (price * (1 + fee))
                entry = {"entry_date": date, "initial_equity": cash}
                fills.append({"date": date, "side": "buy", "adjusted_price": price,
                              "adjusted_units": units, "fee": units * price * fee})
                cash = 0.0
            elif want == 0 and units > 0:
                price = bar.open * (1 - slip)
                cash = units * price * (1 - fee)
                fills.append({"date": date, "side": "sell", "adjusted_price": price,
                              "adjusted_units": units, "fee": units * price * fee})
                roundtrips.append({"entry_date": entry["entry_date"], "exit_date": date,
                                   "net_return": cash / entry["initial_equity"] - 1})
                units, entry = 0.0, None
        rows.append({"date": date, "equity": cash + units * bar.close, "exposure": int(units > 0)})
    curve = pd.DataFrame(rows, columns=["date", "equity", "exposure"]).set_index("date")
    return curve, pd.DataFrame(fills), pd.DataFrame(roundtrips)


def metrics(equity):
    if len(equity) < 2 or not np.isfinite(equity).all() or (equity <= 0).any():
        raise ValueError("Need at least two finite positive equity observations")
    returns = equity.pct_change()
    returns.iloc[0] = equity.iloc[0] - 1  # Include initial execution cost / first session.
    years = max((equity.index[-1] - equity.index[0]).days / 365.25, 1 / 252)
    peak = equity.cummax().clip(lower=1.0)
    std = returns.std(ddof=1)
    return {"total_return": float(equity.iloc[-1] - 1),
            "cagr": float(equity.iloc[-1] ** (1 / years) - 1),
            "max_drawdown": float((equity / peak - 1).min()),
            "sharpe_rf0": float(returns.mean() / std * np.sqrt(252)) if std > 0 else 0.0,
            "annualized_volatility": float(std * np.sqrt(252)), "sessions": len(equity)}
