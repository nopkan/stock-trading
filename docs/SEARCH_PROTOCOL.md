# Strategy-search protocol and audit trail

This search was requested after the original five indicator rules underperformed the same-stock buy-and-hold benchmark. It seeks five **retrospective research candidates**; no amount of searching can establish guaranteed future outperformance.

## Candidate definitions and chronological checks

A grid of 276 specifications was saved before evaluation: 12 rule families, generally 126/252-session lookbacks, 10/20 names, rebalancing every 21/63 global market sessions, and three trend-filter settings. The multi-horizon family uses fixed 63/126/252-session ranks. `search_plan.json` preserves every specification, period and code/data fingerprint. Each canonical specification receives a stable ID. The SQLite primary key includes candidate, evaluation stage and code/data/cost context; restarting the same context skips completed evaluations.

Discovery uses 2017–2020 and validation uses 2021–2023. Both periods start with fresh cash. A candidate advances only if its CAGR exceeds the same-cost benchmark in both periods and its drawdown is no worse in either. The ranking score is the smaller of the two excess CAGRs. The top two passing specifications per family are locked before the later-period evaluation.

Locked specifications are tested on 2024–September 2026 and the full 2017–September 2026 period, under base and stress costs. Each of those four checks requires higher return and no worse drawdown than its corresponding benchmark. The later period had already been examined for the original five strategies, so it is explicitly **not a virgin holdout**. Screening hundreds of variants creates multiple-testing and selection bias. These filters reduce obvious fragility but are not a statistical proof of an edge.

## Additional sensitivity audit

All configurations passing the first checks are evaluated with one additional session of execution delay, with DELTA excluded, and with THAI excluded, both for the full and recent periods. Exclusion changes are applied consistently to each strategy and its corresponding benchmark. An excluded benchmark allocation stays cash. Candidates must retain positive excess CAGR in all six tests. These are additional retrospective screens; their results must not be described as independent out-of-sample evidence.

The final list follows the original discovery/validation ranking, keeps at most one configuration per rule family, and avoids pairing strategies with daily-return correlation of 0.95 or higher. This rejects near-duplicate variants, though the five strategies still share equity/trend exposure and are not independent investment bets. `audit_dispositions.csv` records every rejection or non-selection. `selected_five.csv` is the automatic pre-audit proposal; **`retained_strategies.csv` is the final list**.

## Portfolio construction

Rankings use data known at the signal close. Each stock needs at least 252 observed price bars, an actual positive-volume current bar, and a trailing 20-session median provider price-times-volume proxy of at least THB10 million. Missing historical prices are not backfilled. Forward-filled closes are used for indicator state and valuation only; fills require actual observed prices and positive volume.

The selected strategies use positive skipped-month momentum, a close above the stock's 200-session moving average, and an equal-weight market-return proxy above its 200-session average. A market filter switching off produces cash targets at the next scheduled rebalance, not an immediate intraday exit. That proxy uses the available snapshot stocks' historical returns; it is not an official SET100 index series.

Desired weights equal 0.99 divided by the configured target number of stocks; unused slots stay cash. At a scheduled rebalance, positions are marked at the next open, sales execute first, and buys scale to available cash after costs. There is no borrowing or shorting. Weights may drift beyond their initial targets between rebalances. Orders without a usable session are skipped until the next scheduled rebalance. Daily-bar positive volume does not establish actual open liquidity; execution remains approximate. Liquidity is a provider-data proxy and not a capacity guarantee.

The benchmark retains the original 100 equal initial allocations; BANPU stays cash and each other stock is bought once when usable data permits. It is not a capitalization-weighted SET100 tracker. The candidate ranking/rotation rules differ from the original single-stock cash-allocation rules, so their return improvement includes capital-allocation effects.

## Why these rule families

Momentum is a documented systematic-equity research direction. [AQR's implementation paper](https://www.aqr.com/Insights/Research/Working-Paper/Implementing-Momentum-What-Have-We-Learned) discusses practical costs and implementation; it does not establish profitability for this Thai dataset. [MSCI's methodology](https://www.msci.com/indexes/documents/methodology/2_MSCI_Momentum_Indexes_Methodology_20231120.pdf) provides an example of combining six- and twelve-month risk-adjusted momentum. Our recipes, windows, filters and weighting are our own experiments, not an exact replication of either source.

Other tested families include high proximity, channel position, volume flow, low volatility and reversal within an uptrend. All formulae remain in `research/candidates.py` for reproducible research. Only the five promoted strategies receive active runnable modules in `strategy/`. The original rejected five modules were deleted after their source text, parameters and historical results were preserved in the registry and `legacy_strategy_sources.json`.

The first search is retained in `reports/strategy_search_20260929/`. A dense-data fixture revealed a NumPy/Pandas read-only-array edge case when applying exclusions. The second run in `reports/strategy_search_20260929_v2/` verifies the one-line writable-copy fix under a new code fingerprint. These are **the same 276 hypotheses**, not 552 new strategy ideas. Both contexts and all evaluations remain recorded.
