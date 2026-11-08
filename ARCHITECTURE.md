# Architecture

FastAPI owns deterministic application authority, PostgreSQL persists identities/scopes/audit/domain state, and React provides the local interface behind Caddy HTTPS. Windmill is the intended workflow orchestrator; Home Assistant owns physical automation. Accelerated compute can run natively. Hardware subsystems stay separate. Synology remains the intended durable archive target, not the live PostgreSQL filesystem.

API access uses current active identity/session, CSRF, exact Host/Origin, explicit scope/owner checks and commit-before-release audit. Technical administration does not imply content access. The API uses a restricted database role; migration/administrative credentials stay out of the API environment. Private Work schema/roles and synthetic-only opt-in are separate from family records.

Memory, Discovery, task/reminder and document lifecycle behavior remains structured and deterministic. Source text cannot grant tool authority. Small text/Markdown document originals temporarily use bounded transactional BYTEA staging; PDF/OCR, Synology ingestion, generated answers and full document key/old-backup recovery are not delivered.

No outbound AI gateway is enabled. Unknown/high-impact actions remain blocked. Public source visibility is not publication of an application instance or approval to process real sensitive records.

Spec 050 adds an optional descriptor-safe private local archive adapter. Immutable DB root bindings and audit commit before content copying; the second transaction reauthorizes and copies bounded originals with fsync/atomic publication and exact verification. Database originals remain authoritative. Forgetting requires the bound root and removes managed disk copies before committing the DB scrub. Partial filesystem/SQL failure is reconciled by explicit retry using retained originals; no distributed atomicity is claimed. See [archive lifecycle](docs/DOCUMENT_ARCHIVE.md). PDF/OCR, a validated NAS adapter, archive encryption/key/old-restore suppression and moving originals out of BYTEA remain open.
