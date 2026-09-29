"""Download real Yahoo daily data; preserve provider fields and an audit manifest."""
import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]


def normalize(raw):
    raw = raw.copy()
    raw.index = raw.index.tz_localize(None).normalize()
    raw.index.name = "date"
    raw = raw.rename(columns={"Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Adj Close": "adj_close", "Volume": "volume",
        "Dividends": "dividends", "Stock Splits": "stock_splits"})
    required = ["open", "high", "low", "close", "adj_close", "volume"]
    if not set(required).issubset(raw):
        raise ValueError("Provider did not return required OHLCV and adjusted close")
    valid = np.isfinite(raw[required]).all(axis=1) & (raw[required[:5]] > 0).all(axis=1)
    valid &= raw.volume.ge(0) & raw.high.ge(raw[["open", "close", "low"]].max(axis=1) - 1e-6)
    valid &= raw.low.le(raw[["open", "close", "high"]].min(axis=1) + 1e-6)
    clean = raw.loc[valid].copy()
    if clean.empty or clean.index.has_duplicates or not clean.index.is_monotonic_increasing:
        raise ValueError("Empty, duplicate or unsorted history")
    factor = clean.adj_close / clean.close
    for col in ["open", "high", "low", "close"]:
        clean["adj_" + col] = clean[col] * factor
    return raw, clean, int((~valid).sum())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--start", default="2016-01-01")
    p.add_argument("--end", default="2026-09-29", help="Exclusive end date; omit current incomplete session")
    p.add_argument("--universe", type=Path, default=ROOT / "data/universe/set100_snapshot.csv")
    p.add_argument("--symbols", nargs="+", help="Optional explicit SET symbols")
    p.add_argument("--resume", action="store_true", help="Reuse matching successfully downloaded files")
    a = p.parse_args()
    if pd.Timestamp(a.start) >= pd.Timestamp(a.end):
        p.error("start must precede end")
    tickers = a.symbols or pd.read_csv(a.universe).symbol.drop_duplicates().tolist()
    aliases = json.loads((ROOT / "configs/symbol_aliases.json").read_text())
    out = ROOT / "data/metadata/download_manifest.json"
    previous = json.loads(out.read_text()) if out.exists() else {}
    cached = {r["symbol"]: r for r in previous.get("symbols", [])}
    items = []
    for number, symbol in enumerate(tickers, 1):
        target = ROOT / f"data/prices/{symbol}.csv"
        item = {"symbol": symbol, "provider_symbol": symbol + ".BK"}
        if (a.resume and previous.get("requested_start") == a.start
                and previous.get("requested_end_exclusive") == a.end
                and cached.get(symbol, {}).get("status") == "ok" and target.exists()
                and hashlib.sha256(target.read_bytes()).hexdigest() == cached[symbol].get("sha256")):
            item = cached[symbol]
        else:
            for attempt in range(3):
                try:
                    frame = yf.Ticker(symbol + ".BK").history(start=a.start, end=a.end,
                        auto_adjust=False, actions=True, repair=False, timeout=30)
                    if symbol in aliases and pd.Timestamp(a.start) < pd.Timestamp(aliases[symbol]["effective_date"]):
                        alias = aliases[symbol]
                        old_end = min(a.end, alias["effective_date"])
                        old = yf.Ticker(alias["previous_yahoo_symbol"]).history(start=a.start, end=old_end,
                            auto_adjust=False, actions=True, repair=False, timeout=30)
                        if old.empty:
                            raise ValueError("Verified prior-symbol history unavailable")
                        # Reject a silent adjustment discontinuity across the rename.
                        # Future post-rename dividends need explicit cross-segment adjustment.
                        recent = frame.loc[frame.index.tz_localize(None) >= pd.Timestamp(alias["effective_date"])]
                        if not recent.empty and (not np.isclose(old['Adj Close'].iloc[-1] / old.Close.iloc[-1], 1)
                                or not np.isclose(recent['Adj Close'].iloc[0] / recent.Close.iloc[0], 1)):
                            raise ValueError("Rename history needs cross-segment corporate-action adjustment")
                        frame = pd.concat([old, recent]).sort_index()
                        item["alias"] = alias
                    if frame.empty:
                        raise ValueError("No history returned")
                    raw, clean, invalid = normalize(frame)
                    (ROOT / "data/raw/yahoo").mkdir(parents=True, exist_ok=True)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    raw.to_csv(ROOT / f"data/raw/yahoo/{symbol}.csv", date_format="%Y-%m-%d")
                    clean.to_csv(target, date_format="%Y-%m-%d")
                    first, last = clean.index.min(), clean.index.max()
                    item.update(status="ok", rows=len(clean), first_date=str(first.date()),
                        last_date=str(last.date()), invalid_rows_removed=invalid,
                        zero_volume_rows=int(clean.volume.eq(0).sum()),
                        max_calendar_gap_days=int(clean.index.to_series().diff().dt.days.max()) if len(clean) > 1 else 0,
                        starts_late=bool(first > pd.Timestamp(a.start) + pd.Timedelta(days=10)),
                        ends_early=bool(last < pd.Timestamp(a.end) - pd.Timedelta(days=7)),
                        years_observed=round((last-first).days/365.25, 2),
                        sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                        downloaded_at_utc=datetime.now(timezone.utc).isoformat())
                    item.pop("error", None)
                    break
                except Exception as exc:
                    item.update(status="error", error=str(exc))
                    if attempt < 2:
                        time.sleep(2 * (attempt + 1))
            time.sleep(0.15)
        items.append(item)
        manifest = {"provider": "Yahoo Finance via yfinance", "yfinance_version": yf.__version__,
            "requested_start": a.start, "requested_end_exclusive": a.end,
            "universe_file": str(a.universe), "requested_symbols": len(tickers),
            "adjustment": "adj_close / provider close applied to OHLC; no separate dividend cash flows",
            "membership": "fixed snapshot; survivorship and selection bias", "symbols": items}
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(manifest, indent=2))
        pd.DataFrame(items).to_csv(ROOT / "data/metadata/coverage.csv", index=False)
        print(f"{number}/{len(tickers)} {symbol}: {item['status']} {item.get('rows', 0)} rows", flush=True)
    failed = [x["symbol"] for x in items if x["status"] != "ok"]
    if failed:
        print("Failed symbols (never silently replaced):", ", ".join(failed))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
