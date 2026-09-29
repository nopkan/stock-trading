# Working in this project

## Deployment and audit

- Intended host is the Mac mini, not this development device. Intended broker is
  InnovestX; account API entitlement and live order routing are not configured.
- Follow docs/MAC_MINI_SETUP.md and docs/DATABASE.md. Local Supabase project
  `stock-trading` uses ports 5632x and a private `trading` schema. Do not reset or
  reuse Dropshot's database without an explicit migration plan.
- Secrets, provider downloads, SQLite runtime state and detailed results stay out
  of the public Git repository. Preserve them via the checksummed private bundle.
- Use trading.cli for audited runs. Legacy scripts still use files/SQLite; import
  their results afterward. Export the registry with scripts.registry_transfer
  before committing new experiment records. Append corrections; never rewrite
  prior audit events. Live broker methods must continue to reject requests.
- Run pytest before pushing; PostgreSQL integration tests need a disposable
  STOCK_TEST_DATABASE_URL. Never point that variable at the audit database.

## Research rules

This is a SET100 research project. Keep reusable strategy logic in `strategy/`,
provider data and provenance in `data/`, and execution/metrics in `backtest/`.
Use `.venv/bin/python` for commands. Read `docs/DATA_GUIDE.md` before interpreting
results and `docs/STRATEGY_RESEARCH.md` before proposing indicator changes.

- Never fabricate missing market history or silently replace a ticker.
- Preserve source URLs, raw data, downloaded ranges and checksums.
- Treat the current universe as a fixed snapshot. Archived lists are not yet
  effective-date membership intervals. Label all current results accordingly.
- Respect `configs/data_exclusions.json`; reconcile questionable histories
  against primary sources before removing an exclusion.
- Signal functions return close-of-session desired state. Execution is delayed
  in the common engine. Keep strategies causal and test prefix invariance.
- Keep an untouched evaluation period and record all parameter experiments.
- Use separate report directories for new experiments. Include the benchmark,
  costs, drawdown, exposure and data-quality limitations with results.
- Before proposing a strategy, inspect `research/experiments/STRATEGY_LEDGER.csv`
  and the SQLite registry. Do not repeat rejected specifications as new ideas.
  Canonical IDs identify recipes across contexts; retests require a documented
  reason such as changed costs, corrected engine, new data or user request.
- The five retained strategies are in `strategy/active.json`; use
  `python -m backtest.run`. `retained_strategies.csv` in the v2 search report is
  the final selection; `selected_five.csv` is the earlier pre-audit proposal.
- Use the researched costs in `configs/thai_trading_costs.json`. Describe them
  as representative published rates, not a measured market-wide average.
- The later momentum challenge evaluated 271 additional recipes (552 total).
  Read `reports/momentum_refinement_20260929/RESULTS.md` and
  `research/experiments/REFINEMENT_LEDGER.md` before further tuning.
  `experimental_buffered_momentum.py` is deliberately outside the active five:
  it improved fitted return/drawdown but failed strict sensitivity dominance.
  No dates through 2026-09-28 remain untouched. Do not relabel them out-of-sample.
- Run `.venv/bin/python -m pytest -q` after changes to financial logic.
- This project currently has no broker credentials or live order submission.
  Research results alone are not an instruction to place orders.
- Latest requested capital is THB100,000; InnovestX selected, API not set up.
  Read reports/capital_100000_20260929/REPORT.md and final_decision.json first.
  The 152-recipe batch produced candidate 60ee10de14d6268a (+565.15% base),
  but all-offset and profit-contributor audits failed: median offset +133.37%,
  worst drawdown -58.13%. Do not describe it as robust or live-ready.
  Frozen experimental module: strategy/set100_high_proximity_100000.py;
  replay via backtest.capital_ranked. The preliminary selection.json pass is
  superseded by final_decision.json. Preserve all 493 recorded evaluations.
  Earlier THB30,000 research remains below as historical context.
  Read reports/small_capital_30000_20260929/REPORT.md before further tuning.
  One experimental candidate b142b3be5b992c7b is in
  strategy/set100_small_capital.py and configs/set100_selected_strategy.json.
  Use backtest.small_capital for it, not the fractional-weight engine.
  Its cash-dividend-excluded, split-reconstructed daily-price proxy is not an
  actual auction backtest. Afternoon auctions, historical lot/action metadata,
  membership, broker routing and user drawdown threshold remain unvalidated.
- Preserve CANDIDATE_ALIASES.json: two old auction IDs differ only because of
  integer/float serialization. Do not count alias records as new hypotheses.
