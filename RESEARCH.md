# SET100 strategy research lab

## Latest: THB100,000 search

[The full report](reports/capital_100000_20260929/REPORT.md) records 152 recipes,
448 base/sensitivity evaluations and 45 additional diagnostic runs. A frozen
three-stock high-proximity candidate returned **+565.15%**, with **−16.62%**
drawdown, after modeled fees and slippage. **It failed the extended robustness
audit:** median return across 42 rebalance offsets was +133.37%, worst drawdown
was −58.13%, and three names supplied 74.6% of the favourable run's profit.
This meets the numerical historical target in one run, not a reliable +304.77%
expectation. No strategy is approved for live funding.

The experimental module is
[`strategy/set100_high_proximity_100000.py`](strategy/set100_high_proximity_100000.py).
All failed trials remain recorded; the previous THB30k work is preserved below.

```bash
.venv/bin/python -m backtest.capital_ranked --accept-snapshot-bias --output reports/my_100000_replay
```

## THB30,000 strategy selection

The earlier request used **THB30,000** and three auction decision
windows. [The capital-aware report](reports/small_capital_30000_20260929/REPORT.md)
records **180 evaluations of nine recipes** using 100-share order multiples,
pre-auction sizing, cash constraints, minimum fees and execution stress.
One experimental candidate is saved in
[`strategy/set100_small_capital.py`](strategy/set100_small_capital.py), with
settings in [`configs/set100_selected_strategy.json`](configs/set100_selected_strategy.json).

Its price-only base result is **+69.54% total / 5.58% CAGR / −19.18% maximum
drawdown**, 2017–September 28, 2026. Cash dividends are excluded; prices are
reconstructed from provider split adjustments. This is not the earlier
dividend-adjusted fractional-share backtest, and not verified auction execution.
Actual afternoon auction data, historical membership/action/lot verification,
broker setup, a user drawdown threshold and forward paper results are still
missing. **No live trading is enabled.**

```bash
.venv/bin/python -m backtest.small_capital --capital 30000 --accept-snapshot-bias --output reports/my_30000_run
```

This engine is distinct from the old fractional-unit engine. The original five
research modules remain available below; they are not additional live choices.

Five portfolio strategies were retained after testing **276 configurations across 12 families**, with the original five failed rules also recorded. All five retained candidates beat the same-cost buy-and-hold basket in the specified retrospective checks. **This is fixed-current-membership research, not proof of future outperformance or a historical-membership SET100 index simulation.**

Start with [the results](reports/strategy_search_20260929_v2/RESULTS.md), [every strategy tried](research/experiments/STRATEGY_LEDGER.md), [broker-cost assumptions](docs/THAI_TRADING_COSTS.md), and [the search protocol](docs/SEARCH_PROTOCOL.md).

## Latest momentum challenge

[The refinement report](reports/momentum_refinement_20260929/RESULTS.md) records **271 additional variants**. Buffered momentum with 15 stocks and 5% target cash improved the fitted full-period return from **262.29% to 304.77%**, with drawdown **14.50% versus 14.79%**. A 10% cash variant returned **278.00%** with **13.76%** drawdown. Both include the same fees and slippage.

Neither passed every robustness requirement: the drawdown advantage disappears under delayed fills and THAI exclusion. The existing active five remain unchanged. `strategy/experimental_buffered_momentum.py` is an optional research prototype, outside `active.json`:

```bash
.venv/bin/python -m backtest.run --strategy experimental_buffered_momentum --accept-snapshot-bias --output reports/my_buffered_run
.venv/bin/python -m backtest.run --strategy experimental_buffered_momentum --params '{"reserve":0.10}' --accept-snapshot-bias --output reports/my_buffered10_run
```

The [refinement ledger](research/experiments/REFINEMENT_LEDGER.md) preserves all new trials; the combined CSV ledger now contains **552 distinct specifications**. These results reuse previously examined data and current membership; no new out-of-sample superiority has been established.

## Active strategies

| Python module | Rule family |
|---|---|
| `strategy/rank_multi_horizon.py` | Combined 3-, 6-, 12-month momentum ranks |
| `strategy/rank_volume_flow.py` | Signed-volume leaders with a positive trend |
| `strategy/rank_consistent_trend.py` | Momentum weighted by consistency of positive sessions |
| `strategy/rank_downside_momentum.py` | Momentum divided by downside volatility |
| `strategy/rank_high_proximity.py` | Stocks nearest their trailing six-month high |

`strategy/active.json` records exact parameters and candidate IDs. The original rejected five modules were removed after preserving their definitions in `research/experiments/legacy_strategy_sources.json`. Their previous reports remain available for audit.

## Run each strategy

The local environment is installed. From this project folder:

```bash
source .venv/bin/activate
python -m backtest.run --strategy all --start 2017-01-01 --end 2026-09-28 --accept-snapshot-bias --output reports/my_new_comparison
```

To test one strategy or the more expensive broker/execution scenario:

```bash
python -m backtest.run --strategy rank_multi_horizon --cost-profile stress --capital 1000000 --accept-snapshot-bias --output reports/my_stress_test
```

Each output directory is preserved; choose a new directory for a new run. The CLI refuses to overwrite an existing run. The registry records evaluation results and canonical strategy IDs. A direct replay is intentional verification, not a new strategy idea.

The base scenario charges **0.16799% explicit fees plus 0.10% slippage per side**. Stress uses 0.27499% explicit fees plus 0.20% slippage and a THB50 daily minimum commission before VAT. Starting capital defaults to THB1 million. These are representative published rate assumptions; see the linked cost research.

## Folder layout

```text
StockTrading/
├── strategy/                 # Five active modules plus explicitly experimental prototype
├── data/
│   ├── prices/               # 100 normalized price files
│   ├── raw/yahoo/            # Provider fields retained for audit
│   ├── universe/             # Fixed SET100 snapshot and historical source lists
│   ├── sources/              # Official SET PDFs and original source HTML
│   └── metadata/             # Coverage, checksums and download manifests
├── templates/                # Portfolio and single-stock strategy templates
├── backtest/                 # Main CLI plus original single-stock simulator
├── research/                 # Portfolio engine, candidate recipes, search and audits
│   └── experiments/          # Permanent deduplicated registry and strategy ledger
├── scripts/                  # Data retrieval and report/ledger verification
├── configs/                  # Broker costs, ticker aliases and data exclusions
├── reports/                  # Results, curves, fills, plans and rejected candidates
├── tests/                    # Timing, causality, costs, exclusions and CLI checks
└── docs/                     # Research, costs and data limitations
```

## Add a strategy without repeating a failure

First inspect `research/experiments/STRATEGY_LEDGER.csv`. It records all 552 distinct specifications tried, including rejected ideas. Every evaluation, period and cost profile is in `all_trials.csv`; SQLite is the authoritative store. The 271 later refinements also have a separate readable `REFINEMENT_LEDGER.md`.

```bash
cp templates/strategy_template.py strategy/my_strategy.py
python -m backtest.run --strategy my_strategy --accept-snapshot-bias --output reports/my_strategy
```

`generate_targets(panel, **parameters)` returns close-of-session portfolio weights aligned with the panel dates and symbols. An all-NaN row means no rebalance; other rows must be nonnegative and sum to at most 1. The engine delays execution once. Keep signals causal, test prefix invariance, and record changes as new specifications. The template copies an existing momentum recipe as an interface example; changing its filename alone does not make it a new idea.

For a custom binary 0/1 single-stock rule, use `templates/single_stock_strategy_template.py` and `python -m backtest.single_stock --strategy your_module --accept-snapshot-bias --output reports/your_single_stock_run`. That older research model retains equal initial stock allocations and does not rotate capital. Set its `--fee-bps 16.799 --slippage-bps 10` explicitly to match the representative variable fee assumption; it does not implement daily minimum commissions.

## Resume the recorded search

```bash
python -m research.search --stage screen --folder reports/strategy_search_20260929_v2
python -m research.search --stage confirm --folder reports/strategy_search_20260929_v2
python -m research.audit --folder reports/strategy_search_20260929_v2
python -m scripts.report_search
```

Already recorded evaluations in the same context are skipped. If data, engine or costs change, the frozen plan rejects that context; use a new folder and explain the retest. **The final list is `retained_strategies.csv`.** `selected_five.csv` is the earlier pre-audit proposal. An older search directory preserves the verification history around an array-copy fix; repeated verification is not counted as another 276 ideas.

## Data and coverage

Initial download: 233,382 daily rows across 100 files, requested January 2016–September 28, 2026. Ninety-one series span at least five years; 77 span at least ten. These spans do not certify completeness. BANPU is quarantined; the other 99 files end September 28, 2026. New listings and company restructurings have shorter histories. See [coverage](data/metadata/COVERAGE.md) and [data guide](docs/DATA_GUIDE.md).

```bash
python -m scripts.fetch_universe --archive
python -m scripts.download_data --start 2016-01-01 --end 2026-09-29 --resume
```

Download end is exclusive; backtest end is inclusive. Exclude an incomplete session. Preserve source copies and manifests with experiments. Actual historical membership intervals, delisted names and complete corporate-action reconciliation are not yet implemented.

## Reproduce the environment

Use Python 3.14:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
python -m pytest -q
```

Direct dependencies are in `requirements.txt`; the complete tested environment is in `requirements-lock.txt`. Matplotlib renders the results chart.

The model uses fractional adjusted units, delayed daily execution and approximate liquidity. It has no live broker connection. Open positions are marked to the last close without a forced final sale. The 2024–2026 period has been examined; it is no longer an untouched holdout. Do not interpret retrospective search winners as guaranteed future market-beating strategies.
