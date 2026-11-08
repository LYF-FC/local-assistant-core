# Decisions

Local structured authority, explicit current permissions, transactional minimal audit, restricted roles and deterministic workflows are foundational. Production and external integrations remain gated. Small document BYTEA staging is temporary; durable archive remains separate. See [architecture](ARCHITECTURE.md), [security](SECURITY.md) and [CI](docs/CI_COMPUTE.md).

## Scope and delivery reconciliation

The complete generic [register](docs/FEATURE_REGISTER.md), [MVP acceptance](docs/MVP_ACCEPTANCE.md) and [explicit reconciliation](docs/SCOPE_RECONCILIATION.md) supersede abbreviated source-snapshot planning as an exhaustive scope description. Short views must retain parent mappings and may not remove long-term requirements. Overlaps remain explicit; private configuration and historical evidence stay outside Git.

Development proceeds in substantial dependency-aware batches after owner review/merge of the planning PR. Finish local verification before one completed batch push where practical; required CI failures and review fixes justify additional runs. There is no commit cap or fixed PR countdown. No auto-merge. Synthetic engineering, merged delivery, host/provider acceptance and release certification are distinct.

FastAPI/PostgreSQL/React, Windmill/Home Assistant and separate NOMAD boundaries remain. Local storage/test adapters can unblock development without real NAS/provider access. Calendar writes, alternate orchestrators/frameworks, external AI, production and private namespace conversion remain separately reviewed choices, not incidental authority from this scope.

## Local archive transition — spec 050

Keep original bytes in PostgreSQL while introducing explicitly provisioned local disk copies. A pre-copy committed immutable root binding makes cleanup obligations durable; status re-verifies bytes rather than persisting a stale success flag. This deliberately separates storage failure/recovery acceptance from PDF/OCR parser changes. It does not replace Synology as the intended durable archive layer or activate a live share. No configuration change can silently discharge a bound document's managed-copy cleanup obligation.

## PDF derivation — spec 051

Extend the existing document lifecycle rather than create a second ingestion store. Preserve exact originals on extraction failure, expose bounded failure states, and require explicit owner review before citation. A separate local worker confines native parsing; upload idempotency is owner-scoped and payload-bound. Re-extraction creates an unreviewed version with build provenance. OCR and structured field extraction remain separate dependencies; this supersedes no original storage or deletion contract.

## Explicit bounded OCR — spec 052

OCR is an explicit owner derivation, never an automatic fallback or accuracy assertion. Preserve the exact source and previous derivations; expose uncertainty and require fresh review before citations. Keep the existing text mode as default and use an additive validator migration. Structured fields/uncertainty and filing remain separate retained outcomes.
