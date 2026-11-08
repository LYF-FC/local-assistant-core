# Explicit local context preview — development/test

Spec 011 adds an inspectable reference boundary before any model adapter. Merged prior implementation review on main `187df20` has green CI. This feature adds explicit selection/preview, not semantic search, automatic retrieval, a prompt, model call, external transfer, work namespace, job or permission grant.

## Human workflow

1. After HTTPS sign-in, choose Context preview. Nothing loads automatically until you choose one assigned memory-content scope. No cross-scope bundle, technical administration or unimplemented work scope is offered.
2. Browse up to 25 metadata-only candidates per page: title, type, source, revision and expiry. Only active confirmed profile/preference/procedure/temporary-context records are eligible, unexpired and valid/bounded. Temporary context needs future expiry. Experience records (including Discovery proposals) and any content carrying a top-level record_type namespace are excluded. Use Memory to inspect other records; confirmation is not execution approval.
3. Select 1–10 records from the current page and choose an items budget (UI 2/4/8/16 KiB; API allows 512–16384 bytes). Build preview sends only scope, IDs, displayed expected revisions and budget. The server rechecks scope/ownership/eligibility/revisions and reads current rows, not history or caller-supplied content.
4. Inspect structured content and provenance, record IDs/revisions, source type/reference, update time, confirmed assessment and view expiry. All content remains plain reference data, including text resembling instructions. No HTML/source-link execution or automatic fetch; no model or action is invoked.
5. Scope/page/selection/budget changes clear preview. Clear selection cancels a pending preview. Switching views or signing out unmounts/aborts the panel. Changed/unavailable selections clear catalogue/choices and require explicit refresh, without silently retrying another revision. Size errors keep choices but release no partial/truncated bundle.
6. Preview clears at valid_until, no later than 60 seconds on screen. Server lifetime is capped at 60 seconds, selected source expiry and session absolute expiry. Returning to Memory for corrections/forgetting discards this view. No bundle download/browser storage/persistent context cache is introduced.

## Authority, snapshot and retention limits

Current scope membership is mandatory. Private member_a_private/member_b_private/finance_private requires owner plus membership; shared household/parents/business follows existing scoped-reader policy. One explicitly selected scope prevents accidental mixed-domain bundles. Existing personal scopes do not grant work access. Eligibility filters do not classify arbitrary user text or detect work text pasted into mislabeled family memory.

A preview is a snapshot of an authorized database transaction, not a reusable access token, approval or assurance that sources will remain unchanged. Subsequent requests recheck current state. There is no server push or retroactive erasure of an already-observed response: a correction/forget/revocation elsewhere can make the displayed snapshot stale before its short view lifetime ends. A future model dispatch must independently rebuild/re-authorize current selected revisions at use time; accepting this earlier bundle as dispatch authority would violate the contract.

The generic Memory API's dynamic eligible_for_context flag reflects expiry, not this stricter confirmed/type/namespace policy and not permission to invoke a model. This service enforces its own eligibility. Model adapters, semantic indexes and derived deletion propagation require separate specifications; none is present here.

Bundles are not another stored authoritative record. Only actor/scope, selected IDs/revisions and byte count are audited, without titles/content/source text copied into audit. Memory history/export/forget remains authoritative. Live forgetting cannot erase old exports/backups or already-observed responses; production retention/restore reconciliation remains open.

## API and bounds

- `GET /api/v1/context/candidates?scope=...&limit=25&after=<UUID>`: authenticated HTTPS, maximum 25 metadata records, UUID ascending live pages. Pages across changes are not a consistent global snapshot. An invalid otherwise-eligible saved payload blocks its bounded page with sanitized 422; inspect/correct/forget in Memory.
- `POST /api/v1/context/preview`: authenticated HTTPS, exact Host/Origin, JSON and CSRF. One scope, 1–10 unique selections (id, strict positive expected_revision) and strict integer max_bytes (512–16384, default 8192). No owner/content/prompt/provider override.
- Output: schema_version 1, mode=preview_only, reference_only=true, model_invoked=false, execution_allowed=false; generated_at/valid_until, scope, full items/provenance and items_bytes/max_bytes.
- Budget counts compact sorted UTF-8 JSON of the full items array including provenance, not the small response envelope or model tokens. No truncation/fallback. A large individual source may exceed the maximum including metadata and remain unpreviewable; review its size in Memory rather than silently abbreviating it.
- Unknown/private/wrong-scope/ineligible IDs share generic 404 without partial data. Revision mismatch 409; over-budget 413; forbidden scope/CSRF 403; invalid contract 422; session denial 401. Database/audit/commit failures are sanitized 503 without a bundle.

Rows are read-locked in deterministic UUID order through audit/commit. PostgreSQL uses transaction-local 2-second lock and 3-second statement limits; timeout is failure, not stale success. Authority/source expiry is rechecked after row waits. Catalogue SQL excludes namespace keys including JSON null using PostgreSQL/SQLite-specific key tests, then validates bounded shape. No migration/new grant/dependency. These bounds do not claim a million-record performance benchmark or complete production abuse tuning.

## Verification and remaining gates

Synthetic API/client cases cover metadata pages, allowed/private/shared/current scopes, revocation/disablement, eligibility/namespace/expiry, unique bounded selections, expected revisions, UTF-8 size, source/session lifetime, audit/commit rollback and sanitized errors. PostgreSQL tests restricted-role namespace filtering and a distinct-session correction held under lock: preview waits and rejects the stale revision instead of releasing old content. Real Chromium/TLS tests explicit selection, safe provenance, byte failure, stale refresh/shortened-response expiry, delayed preview across sign-out and old catalogue across scope change/denial. Shortened synthetic expiry tests the client without a minute wait; API tests check real server lifetime clamps.

Existing migration/restore/security/container/browser checks still run. Synthetic context desktop/mobile screenshots may be retained for one day alongside Memory/Discovery; no credentials, traces/auth storage or real records are captured. Exact counts/head evidence are in the PR/convergence record. Actual M2/Safari/iPhone and production recovery remain separate. Work isolation spec 005 is next; passing preview permits no employer imports, external models or real tools.
