# Data provenance and limitations

The initial request covers daily bars from **2016-01-01 through 2026-09-28**, with September 29 as the exclusive download end. The 2016 portion provides indicator warmup before 2017 evaluation. Prices are THB-denominated provider data; volume is the provider's share-volume field. Dates are exchange-local calendar dates with the timezone removed after retrieval.

## Files and meaning

| Path | Meaning |
|---|---|
| `data/universe/set100_snapshot.csv` | 100 constituents extracted from the latest linked official SET PDF as retrieved; a fixed snapshot |
| `data/universe/archived_snapshots.csv` | Successfully parsed historical source lists, each with its original URL and filename; revisions remain separate |
| `data/sources/` | Original official PDFs and constituent-list HTML |
| `data/raw/yahoo/SYMBOL.csv` | Provider-returned price and action fields before row filtering; columns normalized for readability |
| `data/prices/SYMBOL.csv` | Valid price rows plus consistently adjusted OHLC fields |
| `data/metadata/download_manifest.json` | Requested range, actual coverage, data hashes, provider version, retrieval times and failures |
| `data/metadata/coverage.csv` | One row per symbol for inspecting short histories, stale endpoints, gaps and removed rows |
| `data/metadata/universe_sources.json` | Original PDF URLs, SHA-256 hashes and extraction success/errors |

All downloaded data is real provider data. No synthetic prices or filled pre-IPO histories are included. Synthetic data exists only in unit tests. Histories shorter than five years are retained and disclosed; do not manufacture earlier bars.

## Adjustments

Yahoo's `auto_adjust=False` supplies Close and Adj Close separately. For each valid row, the pipeline applies `Adj Close / Close` to Open, High, Low and Close, retaining original provider columns too. Provider OHLC can already reflect split adjustments; do not interpret it as a guaranteed historical exchange tape. [yfinance API documentation](https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html).

Backtests trade **fractional adjusted units**, a total-return-style research approximation. They do not trade literal historical shares. Dividends and split fields remain available for audit but are **not credited again**. Volume stays as supplied by Yahoo. Dividend withholding and precise reinvestment timing are not modeled. Downloading again can revise historical adjusted prices; manifests hash the actual file used.

Rows with non-finite required values, nonpositive prices, negative volume or inconsistent OHLC are removed only from the normalized file and counted in the manifest. Raw rows remain available. Zero-volume rows are retained for marks but cannot execute. The simulator never backfills prices or creates tradable bars for missing days. It carries the last sleeve valuation across missing sessions when aligning a portfolio; long gaps can therefore understate interim volatility and delay fills.

## Membership is not yet point-in-time

The archive provides both regular lists and mid-period revisions. The PDFs' headline half-year range and publication/update date are not sufficient to infer every constituent's actual entry/exit date. Some PDFs may be updated at the same URL. This project intentionally does **not** treat the snapshot archive as an effective-date table.

The default backtest applies the downloaded current list to earlier years. It has survivorship/selection bias and is explicitly labeled exploratory. Historical SET100 research needs every effective membership interval, stocks that later exited or delisted, identifiers and corporate-action links. Archived lists are available to build that dataset, but the first price backfill covers the current 100 only. [Official SET constituent archive](https://www.set.or.th/en/market/information/securities-list/constituents-list-set50-set100).

Two old first-half-2015 PDFs fail the automatic 100-row check because of extraction/numbering anomalies. Their original files are preserved, errors recorded, and incomplete extractions omitted. All downloaded lists covering 2016–2026 pass the 100-distinct-symbol check. No missing archive constituent is guessed.

## Known company-history issues

GST was formerly THCOM. The effective ticker change was September 28, 2026, documented by SET. The download joins THCOM.BK strictly before that date and GST.BK from that date onward. The alias, effective date and source are stored in `configs/symbol_aliases.json`; the join refuses an unexplained adjustment discontinuity. This rule is for a name change, not a generic merger stitch. [SET notice](https://www.set.or.th/th/market/news-and-alert/newsdetails?id=106881901&symbol=THCOM).

BANPU's returned history starts in October 2016 and stops on August 11, 2026, despite the later requested endpoint. SET documents the BANPU/BPP amalgamation and a new BANPU listing starting August 4, 2026. The provider series needs identity and continuity reconciliation; it must not be assumed to represent a clean long history of the present security. [SET listing notice](https://www.set.or.th/en/market/news-and-alert/newsdetails?id=105585700&symbol=BANPU).

**BANPU is quarantined from all backtests through `configs/data_exclusions.json`.** Its 1/100 portfolio sleeve stays cash in every strategy and in the benchmark. Its downloaded file is retained for investigation. Removing this exclusion requires independently reconciled data, not just a successful re-download. Thus 100 files does not mean 100 fully validated histories.

SCB, GULF, STECON and TIDLOR have short returned histories associated with newer legal entities or restructurings. Other short series may reflect recent IPOs or provider coverage. No automatic merger/predecessor stitching is performed. THAI's zero-volume history also needs suspension and restructuring review before execution-grade testing. A complete endpoint does not certify data quality.

## Higher-quality upgrade path

### THB30,000 lot-constrained proxy

`research/small_capital.py` reverses reported subsequent split adjustments to
approximate then-current share prices. It applies provider split/stock-dividend
ratios to held quantities and restricts submitted orders to multiples of 100.
This is not a verified historical share/entitlement ledger: provider action
classification, delivery dates, fractional entitlements and lot-size exceptions
remain uncertain. Fractional or odd-lot balances created by actions are retained
as marked residuals; the simulator does not invent an auction liquidation.
Cash dividends are excluded from cash and NAV for both strategy and basket.
Indicators still use dividend-adjusted prices. Do not compare these price-only
results directly with the earlier adjusted-unit total-return-style results.
See [capital-aware report](../reports/small_capital_30000_20260929/REPORT.md).

### Calendar discrepancies found in the September 29 period analysis

Comparing the stock-panel calendar with observed SET100 index bars found seven
zero-volume provider rows on official 2026 SET holidays: May 1, May 4, June 1,
June 3, July 28, July 29 and August 12. The frozen momentum result has no fills
on these dates, but the rows affect session-based lookbacks and schedules.
Removing just these rows in a same-parameter diagnostic replay changes total
return from 304.77% to 304.93%, with maximum drawdown unchanged at 14.50%.
Original stock files and frozen results are preserved.

The panel also lacks two actual index sessions, January 13, 2017 and January 2,
2024. No missing stock bars were fabricated. These require provider reconciliation
before an execution-grade rerun. The holiday-only replay does not repair them.
See [period analysis](../reports/buffered_momentum_deep_dive_20260929/REPORT.md)
and its provenance file. SET100 price history is now saved under `data/indices/`;
it excludes dividends and is not SET100 TRI. The comparison explicitly flags
carried index/portfolio marks; all month/year boundary index values are observed.

SET's official data services describe five-year history for SETSMART Investor, and deeper history for certain corporate services. Check coverage, export rights, corporate actions, delisted names and account access before selecting a package. No paid service or account was created. [Official SETSMART overview](https://www.set.or.th/en/services/connectivity-and-data/data/web-based).

Yahoo/yfinance is a practical initial research source, not an exchange-certified dataset or a guaranteed automated feed. Review the provider's usage terms before sharing data or using it commercially. [yfinance project documentation](https://ranaroussi.github.io/yfinance/).
