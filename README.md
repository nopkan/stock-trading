# SET100 trading research and audit runtime

Python strategy research, whole-board-lot backtesting, and a local Supabase audit database.
Target host: **Mac mini**. Intended broker: **InnovestX**. Current capital scenario: **THB100,000**.

**Research only. Live trading is disabled and no broker order adapter is implemented.** The latest candidate
returned +565.15% in one fitted run but failed extended robustness checks. See the
[full result](reports/capital_100000_20260929/REPORT.md) and
[final decision](reports/capital_100000_20260929/final_decision.json).

## Start on the Mac mini

Follow [MAC_MINI_SETUP.md](docs/MAC_MINI_SETUP.md) for installation, private data transfer, database setup,
backups and optional three daily research checks. No service is deployed by cloning this repository.

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
npm ci --ignore-scripts
.venv/bin/python -m pytest -q
```

Start the dedicated local database **on the Mac mini** with `npm run db:start`, provision the restricted
application login, restore the private research bundle, and import it as documented. The database uses
port 56322; Studio uses 56323. It does not reuse or reset Dropshot's stack.

Once configured and historical data has been restored:

```bash
.venv/bin/python -m trading.cli doctor
.venv/bin/python -m trading.cli import --label initial-research
.venv/bin/python -m trading.cli backtest --output reports/my-audited-run
.venv/bin/python -m trading.cli verify-audit
```

## Repository layout

| Directory | Purpose |
|---|---|
| `strategy/` | Reusable strategy definitions and frozen experimental candidates |
| `backtest/` | Engines and replay commands; recent engines use whole order lots |
| `research/` | Search definitions, immutable trial exports and deduplication records |
| `trading/` | Database imports, audit events, research CLI and disabled broker boundary |
| `supabase/` | Local configuration and versioned PostgreSQL migrations |
| `deploy/macos/` | Mac mini launchd file generator; never auto-installs tasks |
| `data/` | Tracked universe/provenance; downloaded price/source files stay private |
| `reports/` | Tracked summaries; detailed generated runs stay local |
| `configs/`, `templates/`, `tests/` | Parameters, strategy templates and verification |
| `.local/` | Ignored transfer bundles, backups and host logs |

## What Git contains

Code, dependency locks, migrations, configuration templates, research summaries, source hashes and a
lossless JSONL export of every historical trial. Source market-data downloads, detailed generated outputs,
SQLite runtime files, environments, credentials and database volumes are excluded. Nothing from previous
research is deleted: the private transfer bundle preserves detailed results and provider source files.
Git alone is not a database or market-data backup.

The audited CLI stores source bytes, structured prices, experiment records and result artifacts in local
PostgreSQL. Legacy research/backtest commands still write files/SQLite; import their outputs afterward.
Database audit events are append-only and idempotent. No audit record implies that a real broker trade occurred.

## Documentation

- [Mac mini setup and transfer](docs/MAC_MINI_SETUP.md)
- [Database schema and audit semantics](docs/DATABASE.md)
- [InnovestX integration status](docs/INNOVESTX.md)
- [Research history and commands](RESEARCH.md)
- [Data limitations](docs/DATA_GUIDE.md) and [cost assumptions](docs/THAI_TRADING_COSTS.md)

GitHub CI runs the unit suite and migrations/audit integration tests against a disposable PostgreSQL 17
service. Local database tests skip when `STOCK_TEST_DATABASE_URL` is absent. Raw historical data is not
needed for the test suite. No GitHub workflow deploys or trades.
