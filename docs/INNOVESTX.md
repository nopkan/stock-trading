# Intended broker: InnovestX

The user selected InnovestX on September 29, 2026. Environment defaults and the broker boundary now use
`innovestx`. `trading/brokers/innovestx.py` deliberately rejects submit/cancel requests; it is an integration
boundary, **not** a working broker connector. No API keys, account numbers or credentials are committed.

InnovestX exposes a [SET API portal](https://trade.innovestx.co.th/api-portal/set). The official
[Settrade developer portal](https://developer.settrade.com/open-api/) and
[Settrade SDK examples](https://github.com/settrade/stt-open-api-sdk-example) are integration references.
The portal requires account-specific access; this project has not verified this user's equity API
entitlement, broker/app identifiers, order permissions or auction cutoffs. InnovestX's separate digital-asset
Open API is not the SET100 equity integration.

When an approved equity API account is available, verify the actual SDK/API contract for balances,
buying power, board lots, market status, ATO/ATC orders, cancellations, partial fills and order-status
reconciliation. Use a supported sandbox first. Do not guess broker IDs or copy credentials from sample code.

Every future action must have an immutable intent ID recorded **before** submission, with subsequent
acknowledgements/fills/reconciliation appended to `trading.audit_events`. Idempotency in the database alone
does not prevent duplicate broker orders: the adapter must reconcile ambiguous responses and use broker
client IDs where supported. A database outage must prevent new submissions. Never store API secrets,
authorization headers or PINs in audit payloads; the audit helper redacts common structured secret fields.

The existing capital-specific strategy is experimental and failed the extended timing/contributor audit.
Changing `.env` to enable live mode raises an error. Live routing requires a separately validated strategy,
broker integration, exchange calendar/feed, risk limits and operational reconciliation implementation.
