# Local audit database

Supabase supplies PostgreSQL 17 and Studio. The application uses `psycopg` directly over a local database
connection, avoiding a service-role HTTP token. Migrations create a private `trading` schema; application
tables are not in the public Data API. `stock_app` is a no-login permission role, granted to the host-specific
`stock_runtime` login. Row-level security grants the application read/insert access; UPDATE, DELETE and
TRUNCATE are rejected. Audit events can only be appended through a security-definer function.

| Table | Audit purpose |
|---|---|
| `artifacts` | Exact original bytes addressed by SHA-256; database verifies the checksum |
| `snapshots` | Immutable manifest plus metadata for a dataset or result bundle |
| `snapshot_files` | Original relative path and artifact hash for every snapshot file |
| `market_bars` | Queryable per-snapshot OHLCV, adjusted close and action fields linked to source bytes |
| `research_trials` | Exact historical contexts, parameters, results and original creation timestamps |
| `audit_events` | Append-only requests, decisions, results and future broker action records |
| `audit_chain_health` | Verify stored event hashes and their previous-event links |

Price/quantity/fee values belong in PostgreSQL NUMERIC or decimal strings in JSON, not rounded display
values. Provider bars retain both unadjusted/provider fields and adjusted fields in the source record.
No historical membership, missing prices or future broker responses are fabricated during import.

`append_event` serializes chain writes with a transaction advisory lock. Event keys are unique. Identical
retries return the original event; a reused key with a different kind, actor or payload raises an error.
The original occurrence time is retained on a retry. Corrections must append a new event referencing the old
event. Recording a broker order intent must not be treated as evidence that an order was acknowledged or filled.

Examples of future event kinds: `signal.calculated`, `risk.rejected`, `order.intent`, `broker.acknowledged`,
`broker.unknown`, `order.fill`, `order.cancelled`, `positions.reconciled`, `cash.snapshot`. These are a storage
convention, not implemented broker capabilities. Today's runtime records imports, research requests/results
and blocked-for-live scheduled checks. Detailed historical fills are preserved as exact output artifacts.

All file imports are one database transaction. A failed parse/import rolls back the new snapshot and bars.
Source bytes are read once for storage; structured rows are parsed from the stored bytes. A changed file
creates a new snapshot instead of rewriting the old one. The imported registry retains its original candidate
IDs and does not rename failed strategies as new discoveries.

The hash chain and triggers protect against mistakes and ordinary application writes. A database owner
can alter/drop schema objects, so this is not tamper-proof storage against its administrator. Keep independent
checksummed backups and verify restores. See [Mac mini setup](MAC_MINI_SETUP.md).
