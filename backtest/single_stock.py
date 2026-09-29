"""Reusable CLI: python -m backtest.single_stock --strategy all --start 2017-01-01 ..."""
import argparse
import hashlib
import importlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from backtest.engine import Costs, metrics, simulate

ROOT = Path(__file__).resolve().parents[1]
STRATEGIES = []  # Original five rejected modules retired; custom strategies still work.


def load_prices(path):
    frame = pd.read_csv(path, parse_dates=["date"]).set_index("date")
    cols = ["adj_open", "adj_high", "adj_low", "adj_close", "volume"]
    if not set(cols).issubset(frame):
        raise ValueError(f"{path}: missing adjusted OHLCV columns")
    frame = frame[cols].rename(columns=lambda c: c.removeprefix("adj_"))
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError(f"{path}: duplicate or unsorted dates")
    if not np.isfinite(frame).all().all() or (frame.iloc[:, :4] <= 0).any().any() or (frame.volume < 0).any():
        raise ValueError(f"{path}: non-finite or invalid values")
    return frame


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--strategy", required=True, help="Custom binary-signal module name in strategy/")
    p.add_argument("--params", default="{}", help='JSON overrides for a single strategy')
    p.add_argument("--start", default="2017-01-01", help="Evaluation start, inclusive; earlier bars are warmup")
    p.add_argument("--end", default="2023-12-31", help="Evaluation end, inclusive")
    p.add_argument("--universe", type=Path, default=ROOT / "data/universe/set100_snapshot.csv")
    p.add_argument("--symbols", nargs="+")
    p.add_argument("--data-dir", type=Path, default=ROOT / "data/prices")
    p.add_argument("--output", type=Path, default=ROOT / "reports/latest")
    p.add_argument("--fee-bps", type=float, default=20)
    p.add_argument("--slippage-bps", type=float, default=10)
    p.add_argument("--allow-missing", action="store_true", help="Keep missing stocks as cash sleeves, report all gaps")
    p.add_argument("--accept-snapshot-bias", action="store_true", help="Required acknowledgement for fixed present-day universe")
    a = p.parse_args()
    if pd.Timestamp(a.start) >= pd.Timestamp(a.end):
        p.error("start must precede end")
    if not a.accept_snapshot_bias:
        p.error("This is a fixed snapshot, not historical SET100 membership. Pass --accept-snapshot-bias for exploratory runs.")
    overrides = json.loads(a.params)
    if not isinstance(overrides, dict) or (a.strategy == "all" and overrides):
        p.error("--params must be a JSON object and requires a single strategy")
    names = STRATEGIES if a.strategy == "all" else [a.strategy]
    if any(not re.fullmatch(r"[a-z][a-z0-9_]*", n) for n in names):
        p.error("Invalid strategy module name")
    symbols = a.symbols or pd.read_csv(a.universe).symbol.tolist()
    if len(set(symbols)) != len(symbols) or not symbols:
        p.error("Universe must be nonempty with unique symbols")
    prices, issues, hashes = {}, [], {}
    exclusions = json.loads((ROOT / "configs/data_exclusions.json").read_text())
    calendar = pd.DatetimeIndex([])
    for symbol in symbols:
        if symbol in exclusions:
            issues.append({"symbol": symbol, "issue": "quarantined_cash_sleeve: " + exclusions[symbol]["reason"]})
            continue
        path = a.data_dir / f"{symbol}.csv"
        if not path.exists():
            issues.append({"symbol": symbol, "issue": "missing_file_cash_sleeve"})
            if not a.allow_missing:
                raise FileNotFoundError(f"{path}; download it or explicitly use --allow-missing")
            continue
        frame = load_prices(path)
        hashes[symbol] = hashlib.sha256(path.read_bytes()).hexdigest()
        prices[symbol] = frame
        evaluation = frame.loc[a.start:a.end]
        calendar = calendar.union(evaluation.index)
        if evaluation.empty:
            issues.append({"symbol": symbol, "issue": "no_bars_in_period_cash_sleeve"})
        elif evaluation.index[-1] < pd.Timestamp(a.end) - pd.Timedelta(days=7):
            issues.append({"symbol": symbol, "issue": "early_end_stale_mark"})
        if frame.index[0] > pd.Timestamp(a.start):
            issues.append({"symbol": symbol, "issue": "short_history_cash_before_first_bar"})
        if frame.index.to_series().diff().dt.days.max() > 10:
            issues.append({"symbol": symbol, "issue": "calendar_gap_over_10_days"})
    calendar = calendar.sort_values()
    if len(calendar) < 2:
        raise ValueError("No usable evaluation calendar")
    costs = Costs(a.fee_bps, a.slippage_bps)
    a.output.mkdir(parents=True, exist_ok=True)
    aggregates, summaries, symbol_rows, run_parameters, source_hashes = {}, [], [], {}, {}
    for name in list(dict.fromkeys(names + ["buy_hold"])):
        module = importlib.import_module("strategy." + name)
        params = dict(module.DEFAULTS)
        if name != "buy_hold":
            params.update(overrides)
        run_parameters[name] = params
        source_hashes[name] = hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
        sleeves, exposures, fills, trips = {}, {}, [], []
        for symbol in symbols:
            if symbol not in prices or prices[symbol].loc[a.start:a.end].empty:
                sleeves[symbol] = pd.Series(1.0, index=calendar)
                exposures[symbol] = pd.Series(0.0, index=calendar)
                symbol_rows.append({"strategy": name, "symbol": symbol, **metrics(sleeves[symbol]),
                                    "completed_trades": 0, "open_at_end": 0, "cash_only": True})
                continue
            frame = prices[symbol]
            signal = module.generate_signals(frame.copy(), **params)
            curve, orders, trades = simulate(frame, signal, a.start, a.end, costs)
            sleeves[symbol] = curve.equity.reindex(calendar).ffill().fillna(1.0)
            exposures[symbol] = curve.exposure.reindex(calendar).ffill().fillna(0.0)
            symbol_rows.append({"strategy": name, "symbol": symbol, **metrics(sleeves[symbol]),
                                "completed_trades": len(trades), "open_at_end": int(curve.exposure.iloc[-1]), "cash_only": False})
            if not orders.empty:
                fills.append(orders.assign(symbol=symbol))
            if not trades.empty:
                trips.append(trades.assign(symbol=symbol))
        equity = pd.DataFrame(sleeves).mean(axis=1)  # Fixed initial equal allocations, no daily rebalance.
        aggregates[name] = equity
        trades = pd.concat(trips, ignore_index=True) if trips else pd.DataFrame(columns=["net_return"])
        orders = pd.concat(fills, ignore_index=True) if fills else pd.DataFrame(columns=["date", "side"])
        summaries.append({"strategy": name, **metrics(equity),
            "mean_sleeve_exposure": float(pd.DataFrame(exposures).mean().mean()),
            "completed_trades": len(trades), "fills": len(orders),
            "win_rate": float(trades.net_return.gt(0).mean()) if len(trades) else None,
            "universe_size": len(symbols), "quarantined_symbols": len(set(symbols) & set(exclusions))})
        orders.to_csv(a.output / f"{name}_fills.csv", index=False)
        trades.to_csv(a.output / f"{name}_trades.csv", index=False)
    summary = pd.DataFrame(summaries)
    summary["total_return_minus_buy_hold"] = summary.total_return - summary.loc[summary.strategy.eq("buy_hold"), "total_return"].iloc[0]
    summary.to_csv(a.output / "comparison.csv", index=False)
    pd.DataFrame(aggregates).rename_axis("date").to_csv(a.output / "equity.csv")
    pd.DataFrame(symbol_rows).to_csv(a.output / "per_symbol.csv", index=False)
    pd.DataFrame(issues, columns=["symbol", "issue"]).to_csv(a.output / "data_issues.csv", index=False)
    (a.output / "run.json").write_text(json.dumps({
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "start": a.start, "end": a.end,
        "fee_bps_per_side": a.fee_bps, "slippage_bps_per_side": a.slippage_bps,
        "bias": "fixed present-day snapshot; NOT a point-in-time SET100 backtest",
        "execution": "previous observed close signal, next positive-volume observed open; fractional adjusted units",
        "portfolio": "fixed initial equal sleeves; cash before availability; stale marks over missing sessions",
        "end_positions": "marked to close, not force-liquidated; unrealized returns included; no final exit fee",
        "symbols": symbols, "parameters": run_parameters, "price_sha256": hashes,
        "data_exclusions": {s: exclusions[s] for s in symbols if s in exclusions},
        "strategy_sha256": source_hashes,
        "indicators_sha256": hashlib.sha256((ROOT / "strategy/indicators.py").read_bytes()).hexdigest(),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "engine_sha256": hashlib.sha256((ROOT / "backtest/engine.py").read_bytes()).hexdigest(),
        "issues": issues}, indent=2))
    print("EXPLORATORY SNAPSHOT BACKTEST — survivorship bias; adjusted fractional units")
    print("Quarantined to cash:", ", ".join(s for s in symbols if s in exclusions) or "none")
    print(summary.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    print(f"Saved: {a.output.resolve()} | data flags: {len(issues)}")


if __name__ == "__main__":
    main()
