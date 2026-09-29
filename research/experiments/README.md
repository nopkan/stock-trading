# Experiment registry

Start with [STRATEGY_LEDGER.md](STRATEGY_LEDGER.md) or [STRATEGY_LEDGER.csv](STRATEGY_LEDGER.csv): one row per distinct hypothesis.

`all_trials.csv` contains every saved evaluation, including different periods, fees, code contexts and diagnostics. `registry.sqlite3` is the local legacy deduplication store (not committed). `trials.jsonl` is its lossless portable export; restore with `python -m scripts.registry_transfer restore`. Import both source artifacts and structured trials into Supabase with `python -m trading.cli import`. Candidate IDs identify canonical rules and parameters; context IDs identify data, code and cost conditions. Do not erase rejected records.

Latest: [THB100,000 study](../../reports/capital_100000_20260929/REPORT.md), 448
search/sensitivity evaluations plus 45 further diagnostic runs. The frozen
candidate failed the extended robustness audit. `final_decision.json` supersedes
the preliminary shortlist pass. The records below describe earlier batches.

Earlier: [THB30,000 capital-aware study](../../reports/small_capital_30000_20260929/REPORT.md)
evaluated eight new affordability-aware recipes plus a retest of the original
buffered recipe, 180 evaluations total. The prior auction study added three
recipes. There are **563 distinct recipes after resolving
`CANDIDATE_ALIASES.json`**, not 564: preserve the alternate-ID records for audit.
Candidate `b142b3be5b992c7b` is the one selected experimental THB30,000 rule;
the selection is not approval for live trading. See each report's `selection.json`
for every failed scenario and `all_results.csv` for numerical outcomes.

The 276 candidate recipes are reusable research definitions in `research/candidates.py`; only five are promoted to active strategy modules. The five rejected original modules survive as audit text in `legacy_strategy_sources.json`.
