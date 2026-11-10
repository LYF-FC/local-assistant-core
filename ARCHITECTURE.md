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

## Invoice field review — spec 056

Two protected invoice current/history tables derive only from existing reviewed document revisions. Fixed bounded label extraction proposes six fields; explicit human decisions and source-line/page/hash evidence remain separate from suggestions. Current-source drift withholds stale values/match keys. Scoped read-only duplicates use exact bytes or human-reviewed issuer/number; creator authority and metadata audit commit protect all release paths. Aggregate document forgetting atomically scrubs derived history/keys. No new worker, model, network adapter or original store. See [contract](docs/INVOICE_REVIEW.md).

## Reviewed invoice filing plans — spec 057

An optional versioned plan extends the invoice aggregate and sealed revision snapshots. Deterministic bounded logical folder/name suggestions and manual alternatives share current owner/source/grant locks and metadata audit. Approval/withdrawal are invoice revisions with permanent `execution_authorized: false`; no file/job/network adapter exists. Field review/reset clears the current plan and document drift withholds it. No new schema or service. [Contract](docs/INVOICE_FILING_PLANS.md).

## Offline email intake — spec 058

One immutable envelope table links exact raw-message bytes to initial document revision 1/attachment checksum. Bounded standard-library MIME decoding accepts one attachment and delegates original validation/PDF extraction to existing document creation. Owner serialization and one DB transaction protect per-owner/scope exact replay, quotas and audit. Shared attachments never expose raw email; metadata/exports remain creator-only. Aggregate source forgetting scrubs the envelope and derived invoice/plan history, retaining only a private exact-message replay tombstone. No mail network/job/model adapter. [Contract](docs/OFFLINE_EMAIL_INTAKE.md).

## Feature overview and scope review — spec 059

The feature dashboard is an offline generated documentation artifact, outside the application/runtime. The canonical register, reviewed stage/snapshot metadata and separately labelled per-reference critique generate Markdown/HTML deterministically. Only the exact validated artifact/data paths may take documentation CI; generator/template/policy changes remain full. Shared-implementation suggestions preserve domain stores/authority, not a global JSON database, memory/index or agent per feature. No deployed service or integration changes. [Review](docs/FEATURE_REVIEW.md).


### Installation configuration foundation (spec060 branch)

[Installation setup](docs/INSTALLATION_SETUP.md) adds a sealed singleton UUID/revision, bounded schema1 language/timezone defaults and immutable matching history. Current technical-admin authority uses a dedicated membership lock under the existing user→singleton transaction boundary; task scopes stay restricted. Session/source/payload-bound preview receipts confer no standalone authority. The static catalogue describes build/setup readiness without probing hosts or activating capabilities. Templates omit identity/records/secrets; backups preserve identity. Existing namespace and runtime controls remain authoritative.


### Approved later review/refactoring programme

[The programme](docs/DEFERRED_REVIEW_PROGRAMME.md) is approved after existing scope/later stages. All baseline 149 assessments and sixteen shared implementation boundaries are retained. REV-01–06 trace six additional supporting refinements/outcomes; they do not introduce six subsystems or a global cross-scope store. Future refactors must preserve domain authority, scoped identity, audit/provenance/export and recovery compatibility with explicit migration/rollback acceptance. No runtime, schema, orchestrator or provider decision changes in this planning batch. Spec060 is now merged in PR15, retaining the bounded architecture described above.


### Spec062 branch: ephemeral scoped overview

[Daily overview](docs/DAILY_OVERVIEW.md) composes existing strict client briefing/reminder/document reads with one abort/generation/deadline boundary. Authority denials clear the batch; ordinary section failures remain explicit. At most60seconds from request start, hidden-tab/selection/session/view clearing, no persistence or background refresh. No new server store, grant, queue, mutation or external adapter. Source navigation preserves scope and rereads current server authority; task/reminder/calendar/document panels remain authoritative.


### Spec063 design: restricted financial records

[Financial capture](docs/FINANCIAL_CAPTURE.md) will use dedicated server-validated records/revisions while reusing existing identity, finance_private grants, audit and transport. Do not implement it solely as a client-side JSON convention in generic Memory or inherit automatic context eligibility. Explicit unknown/forecast and record-only plan review have distinct semantics. No new table, route, schema or inference path is implemented by this design batch.


### Spec064 branch — financial storage/API

[Financial records/revisions](docs/FINANCIAL_REGISTER_API.md) implement the dedicated schema boundary specified in spec063, reusing current identity/audit/transport. Scope is always finance_private plus current owner; no Memory/context projection. A fixed finance membership lock leaves task scopes unchanged. Owner locks serialize quotas and record locks serialize expected-revision changes. DB guards seal identity/current/history and permit history scrubbing only after terminal forgetting. No queue, model, provider or financial executor is introduced.


### Spec065 branch — strict ephemeral financial UI

[The financial UI](docs/FINANCIAL_UI.md) validates owner/scope/kind/schema/revision/history/export receipts before rendering or downloading. It reuses protected finance POSTs and server authority; no Memory projection or new permission surface. One cancellation generation and a 60-second privacy deadline gate reads/mutations/downloads. Hidden/session/view/denial clearing includes drafts and acknowledgements; conflicts preserve a blocked draft until discard/reload or expiry. Source strings render as text, Markdown fences escaped validated JSON and no browser persistence/polling is added.


### Spec066 branch — bounded operations observations

[Operations overview](docs/OPERATIONS_OVERVIEW.md) reuses current technical-admin session/CSRF/installation membership locks and existing SELECT grants. Fixed runtime package metadata/configuration states and a caller-owned technical-scope job status sample feed a strict ephemeral UI. No audit SELECT, payload query, filesystem/network/service probe, new grant/schema or execution capability. Metadata-only read audit must commit before release; failures withhold all observations.
