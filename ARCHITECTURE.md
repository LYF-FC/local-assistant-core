# Architecture

FastAPI owns deterministic application authority, PostgreSQL persists identities/scopes/audit/domain state, and React provides the local interface behind Caddy HTTPS. Windmill is the intended workflow orchestrator; Home Assistant owns physical automation. Accelerated compute can run natively. Hardware subsystems stay separate. Synology remains the intended durable archive target, not the live PostgreSQL filesystem.

API access uses current active identity/session, CSRF, exact Host/Origin, explicit scope/owner checks and commit-before-release audit. Technical administration does not imply content access. The API uses a restricted database role; migration/administrative credentials stay out of the API environment. Private Work schema/roles and synthetic-only opt-in are separate from family records.

Memory, Discovery, task/reminder and document lifecycle behavior remains structured and deterministic. Source text cannot grant tool authority. Bounded text/Markdown and PDF originals use transactional BYTEA staging. Spec 051 adds optional local PDF text extraction and spec 052 adds explicit bounded OCR. Structured fields, Synology ingestion, generated answers and full document key/old-backup recovery remain open.

No outbound AI gateway is enabled. Unknown/high-impact actions remain blocked. Public source visibility is not publication of an application instance or approval to process real sensitive records.

Spec 050 adds an optional descriptor-safe private local archive adapter. Immutable DB root bindings and audit commit before content copying; the second transaction reauthorizes and copies bounded originals with fsync/atomic publication and exact verification. Database originals remain authoritative. Forgetting requires the bound root and removes managed disk copies before committing the DB scrub. Partial filesystem/SQL failure is reconciled by explicit retry using retained originals; no distributed atomicity is claimed. See [archive lifecycle](docs/DOCUMENT_ARCHIVE.md). Broader OCR acceptance, a validated NAS adapter, archive encryption/key/old-restore suppression and moving originals out of BYTEA remain open.

## Bounded PDF derivation — spec 051

An optional non-root, read-only, network-free Poppler worker receives bounded original bytes over a private Unix socket. Native children run under default-deny seccomp and resource/time/output limits; the API never loads the parser. The worker has no database credentials or archive mount. Raw and derived hashes, parser build fingerprint, page/line spans and explicit failure states join the existing sealed version lifecycle. Review gates citations; replacement/re-extraction resets it. See [PDF ingestion](docs/PDF_INGESTION.md).

## Explicit bounded OCR — spec 052

An explicit OCR extraction mode reuses the existing private worker, document versions, review reset and raw/derived/page provenance. Fixed Poppler grayscale rendering feeds fixed English/French/Spanish Tesseract models through pipes under the same confinement; no intermediate image is persisted. OCR is limited to two pages and an 18-second processing budget. Model bytes join build provenance. See [OCR contract](docs/PDF_OCR.md).

## Planned installation and feature boundaries

Separate shared code, schema-validated private configuration and private operational state. Stable software feature/policy keys coexist with installation-local household/user/workspace identities; display names never define authorization or record mappings. Independent installations use separate data/credential namespaces and backups. Feature activation combines dependency/readiness checks with current permissions and server/worker enforcement; core identity, authorization, audit and recovery are not optional. See [INSTALL-01–12](docs/CONFIGURABLE_INSTALLATIONS.md). Current fixed seed scopes are not silently generalized or converted by this scope document.

## Planned model-selection evaluation

Application task-to-model selection is distinct from internal MoE expert routing. RND-04/05 evaluate whether either architecture or task specialization improves actual quality/resource outcomes; shared inference must not merge household/Work context or grant tool authority. Preserve replaceable adapters, bounded resource scheduling and explicit unavailable states with deterministic core availability. Configuration under INSTALL-02/03/10 follows a later evidence-backed ADR; no remote fallback or stack change is implied. See [model research](docs/LLM_RESEARCH.md).

## Scoped source answers — spec 053

A bounded reviewed-document evidence query and optional replaceable local passage selector extend the existing library. Preparation audit commits first; a fresh transaction reauthorizes and locks/rebuilds exact revisions before dispatch and audited response release. Model output selects only validated source line ranges; the application constructs quotations. A trusted protocol subprocess, without inherited credentials, has a hard 12-second deadline and one active slot per API process. No conversation/index store, tool execution or remote fallback. See [answer contract](docs/DOCUMENT_ANSWERS.md).

## Calendar and briefing — spec 054

Two local tables retain bounded full calendar windows and sealed revisions. Optimistic source revision, stable UID/recurrence identity, cursor/fetch/sequence checks and metadata audit commit together. A current-authority day read locks calendar/task/memory sources and discloses staleness, coverage, overlaps and truncation. No network adapter, recurrence expander or model is introduced.

## Recurring routines — spec 055

Finite daily/weekly IANA plans, sealed routine history and unique local-date receipts extend existing tasks/private reminders. The optional local worker holds current owner/grant/routine authority while committing task/history/reminder/cursor/receipt and metadata system audit atomically. No provider effect, new executor platform or independent completion store. The data-network-only worker profile remains opt-in. [Contract](docs/RECURRING_ROUTINES.md).
