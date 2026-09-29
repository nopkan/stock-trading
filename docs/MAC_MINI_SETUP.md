# Mac mini setup

Deploy on the Mac mini. Preparing this repository does not deploy a service on the development laptop.
The runtime is **research-only**: InnovestX order submission is deliberately unimplemented. The latest
strategy failed extended robustness checks. Three scheduled checks record health/status; they do not
constitute a live trading scheduler or an exchange-calendar integration.

## 1. Install prerequisites and clone

Use macOS with Python 3.14, Node.js 22+ and a running Docker-compatible runtime.
On the Mac mini, Homebrew can install Python, Node and PostgreSQL client tools:

```bash
brew install python@3.14 node libpq
git clone https://github.com/nopkan/stock-trading.git
cd stock-trading
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
npm ci --ignore-scripts
.venv/bin/python -m pytest -q
```

Install/start Docker Desktop on the Mac mini if it is not already running. The three database integration
tests skip without a disposable test database; GitHub CI runs them against PostgreSQL 17. Never point
`STOCK_TEST_DATABASE_URL` at an audit database you want to preserve.

## 2. Start the dedicated Supabase stack

```bash
npm run db:start
npm run db:status
cp .env.example .env
chmod 600 .env
```

The pinned CLI uses project ID `stock-trading`: database **56322**, Studio **56323**, API **56321**,
shadow database **56320**. These avoid Supabase's usual 5432x ports used by other projects. Check for
port conflicts before starting; do not stop or reset Dropshot to make room. No cloud project is linked.

Use the database connection reported by the local CLI for `STOCK_ADMIN_DATABASE_URL`. Supabase local
development defaults are not private credentials for an internet-facing service: keep Docker's published
ports on a trusted host/network, block inbound access with the host firewall, and do not forward these
ports from the router. The app connects through loopback and a separate restricted login. The `trading`
schema is **not** exposed through Supabase's public REST schemas.

The first start applies `supabase/migrations`. For later updates, use:

```bash
npm run db:migrate
```

Do **not** use `supabase db reset`: it erases the local database. To stop while preserving volumes, use
`npm run db:stop`; do not pass `--no-backup`. Local CLI lifecycle reference:
[Supabase local workflow](https://supabase.com/docs/guides/local-development/cli-workflows).

Provision the application login interactively (no password enters shell history):

```bash
.venv/bin/python -m trading.cli provision-user
```

Edit `STOCK_DATABASE_URL` in `.env` to use `stock_runtime` and its new password. URL-encode special
characters in the password. The app's role can read and append audit records but cannot update/delete
them. Keep the admin URL restricted to setup/backup operations. Then:

```bash
.venv/bin/python -m trading.cli doctor
```

If you choose to reuse Dropshot later, review its role/schema names and migration process first; use a
separate `trading` schema and dedicated login. Do not run this project's Supabase reset/start commands
inside the Dropshot repository. The shipped default is a separate stack.

## 3. Transfer the existing research history

Downloaded provider prices, original source documents and detailed run artifacts are intentionally
excluded from the **public** Git repository. Metadata, summaries, strategy definitions and the exact
trial registry export are tracked. Existing research is preserved on the original device.

The prepared private archive is `.local/transfers/research-20260929.tar.gz`, with an adjacent SHA-256 file.
Copy both to the Mac mini by AirDrop, a private drive or SSH. Do not publish them as GitHub assets.
From the directory containing the transferred archive:

```bash
shasum -a 256 -c research-20260929.tar.gz.sha256
```

From the repository, restore using its actual file path:

```bash
.venv/bin/python -m scripts.bundle_research restore /path/to/research-20260929.tar.gz
.venv/bin/python -m scripts.registry_transfer restore
.venv/bin/python -m trading.cli import --label transferred-research-20260929
.venv/bin/python -m trading.cli verify-audit
```

Restoration checks every file's hash and refuses to overwrite a different existing file. If code/report
versions have diverged, restore with `--destination .local/restored-history` and reconcile intentionally.
Import stores exact source bytes, queryable price rows and every experiment in Supabase. Identical retries
are safe; changed data creates a new immutable snapshot. The SQLite registry remains a legacy research
cache and can be rebuilt losslessly from `research/experiments/trials.jsonl`.

Without the private bundle you can run unit tests and inspect research summaries, but cannot reproduce
the frozen market-data results. A fresh `scripts.download_data` download is possible under provider terms;
it may revise history and does not recreate the old snapshot or the saved index tape. See `DATA_GUIDE.md`.

## 4. Run an audited backtest

```bash
.venv/bin/python -m trading.cli backtest --output reports/mac-mini-first-run
```

This snapshots inputs, durably records the request, runs the frozen THB100k candidate, verifies input hashes
and imports all output files. A database failure stops the audited operation; there is no silent file-only
fallback. A crashed job can leave a `backtest.requested` event without a terminal event, which is evidence
to investigate. The older direct `backtest.*` and `research.*` commands still write files/SQLite only;
run `trading.cli import` afterward if you use them. Do not claim those legacy calls are automatically audited.

## 5. Optional three daily research checks

Set the Mac mini's **system timezone to Asia/Bangkok**. launchd calendar times use the system timezone,
not the Python timezone setting. Render the plists locally on the Mac mini so their absolute paths are right:

```bash
.venv/bin/python -m deploy.macos.install_checks
mkdir -p "$HOME/Library/LaunchAgents"
cp .local/launchd/local.stock-trading.*.plist "$HOME/Library/LaunchAgents/"
for task_plist in "$HOME"/Library/LaunchAgents/local.stock-trading.*.plist; do
  launchctl bootstrap "gui/$(id -u)" "$task_plist"
done
```

The checks run at 09:45, 13:45 and 16:30 Bangkok time. They log `window.checked` with zero orders, including
weekends; they are health checks, not assertions that SET is open. Repeated checks for the same local date
and window deduplicate. They need an active user login and a running local database. Start Docker and
`npm run db:start` after reboot before relying on the checks; this release does not install a boot daemon.
A sleeping Mac can delay launchd jobs. Logs live in `.local/logs` and should be rotated on the host.

To unload a check, use `launchctl bootout gui/$(id -u)/local.stock-trading.morning` (and the other labels).
Rendering files alone never starts a task. No plist was loaded on the development device.

## 6. Back up and verify

Put Homebrew's libpq `bin` directory on PATH, then:

```bash
export PATH="$(brew --prefix libpq)/bin:$PATH"
.venv/bin/python -m scripts.db_backup
.venv/bin/python -m trading.cli verify-audit
```

Copy `.local/backups/*.dump` and their checksums to a separate private disk/host. Git does not back up
the database. Backups contain the private `trading` schema's data, including raw artifact bytes; migrations
and role definitions are in Git. Test restore on a **new disposable Supabase stack**: apply migrations,
then restore the dump with `pg_restore --data-only --exit-on-error` using that stack's admin connection.
Never restore into a populated audit database. The hash chain detects accidental changes, but the database
owner can disable triggers or rewrite the chain; independent backup/checkpoint retention is necessary.

## InnovestX setup later

See [INNOVESTX.md](INNOVESTX.md). No credentials are required to prepare or reproduce this repository.
Selecting a broker does not validate the strategy or enable live routing.
