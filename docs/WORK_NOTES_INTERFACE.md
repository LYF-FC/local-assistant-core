# Synthetic Work notes screen — spec 026

The optional Work Companion screen combines capture, inspection, explicit version confirmation, correction, forgetting and original-session request reconciliation. Sources and owners use labels; retention is chosen explicitly. Unknown owner/date remain unknown. No model, connector or automatic worker runs. Only synthetic sample text is accepted.

## Deliberate activation

The standard M2 update needs no additional activation. Preserve existing users, CA, secrets and volumes. The interface flag defaults to false. For the optional synthetic pilot, first follow the protected adapter setup in WORK_SYNTHETIC_ADAPTER.md and the explicit `app.work_notes_storage` provisioning in WORK_NOTE_CHANGES.md. Layer `infra/core/work-notes-interface.override.yml` after the base and adapter files when starting API. This enables the interface and existing capture/review/confirmation/change flags together; it supplies no credentials or user grants. Generic storage provisioning can reset these narrow grants.

Open Work Companion, load assigned workspaces, choose the synthetic workspace and open synthetic notes. Select labelled sources, a retention policy and expiry, then request a sample save. The screen reports pending until the existing trusted local one-shot executor is deliberately invoked. Request references are available in details for that operation. The existing capture, confirmation and change runbooks describe the corresponding executor commands. Never give migration/owner credentials to API.

Inspect the saved note before confirming its exact displayed version. Confirmation first records explicit review, then queues confirmation. Correction preserves kind/policy and cannot extend expiry; it returns a draft requiring fresh confirmation. The forget modal explains that application is separate and older backups can remain. Expired or source-ineligible notes expose metadata only, permitting deliberate forgetting without content disclosure.

## Read contracts and request recovery

POST `/api/v1/work/workspaces/{workspace}/notes/catalogue` with `{}` returns at most 25 notes, sources, parties, policies and current-session requests per section. Use `section`, `after` and `limit` for bounded UUID pagination. `section: "requests"` plus the original `request_id` and `operation` performs a scoped nonce lookup. POST `/api/v1/work/workspaces/{workspace}/notes/{record}/inspect` with `{}` returns one currently live draft/confirmed revision, hash and selected reference labels.

These are current-authority reads: HTTPS/Host/Origin/session/CSRF and current synthetic workspace grant precede private credential access. Restricted-role/same-target checks, RLS, SQL timeouts, private prepared inspection audit and metadata-only identity audit remain required. No new database object, privilege, queue or mutation authority is introduced. Request recovery reads metadata only; it cannot manufacture missing committed write evidence or authorize an orphan preparation. It remains scoped to the original actor, session and workspace. Pending counts are snapshots, not processing promises.

After an uncertain response, use recovery or deliberately retry the preserved same request. No automatic retry or new nonce is generated. A pending/uncertain binding blocks another submission. Acknowledgement, historical application and current note inspection are distinct. An expired pending request needs deliberate local reconciliation; expiry does not physically delete its payload. A reload discards the preserved payload, retaining only the minimal request binding needed for recovery.

## Ephemeral content and evidence

The client strictly validates scope, schema, version bindings and response lifetime. Content and selected reference labels expire within 60 seconds, bounded by session/content/party expiry. View/workspace changes, denial, credential failure, expiry and late responses abort reads and clear private content. No browser storage, URL, export, log or remote AI receives note content. Minimal request metadata may survive preview expiry for authorized reconciliation. All later writes reauthorize current state.

Spec 026 tests cover bounded/isolation/default/negative contracts, audit and commit/expiry failures, orphan recovery, strict client parsing and frozen retries. Optional verified-TLS browser checks exercise capture → separate local save → review/confirmation → correction → forgetting, uncertain-response recovery, denial and cancelled late reads, with mobile/desktop screenshots. Exact-commit CI and screenshot evidence are recorded in the delivering PR; branch verification does not imply merge, real employer data, M2 acceptance, independent key/derived-copy/old-backup recovery or production readiness.

Merged prior implementation review delivers this screen. The spec 027 candidate adds bounded browser-only labelled-debrief proposal review; see WORK_DEBRIEF_REVIEW.md. Full debrief/source lineage and remaining isolation/recovery acceptance stay open.

Spec 029 candidate adds selected current-note export through an independent default-disabled flag. It previews exact source/retention metadata and rechecks reviewed contents before an acknowledged local download. See WORK_NOTES_EXPORT.md for issuance receipts and owner-managed copy limits.


## Synthetic meeting preparation workbench — merged prior implementation review/spec 042

Select up to ten confirmed notes from the displayed page, review deterministic agenda groups and explicit action follow-up unknowns, inspect source/record-version citations, and acknowledge a separate Markdown copy. Recheck the exact reviewed selection through the existing notes-export API before building the download from its fresh response. Meeting title/time are browser-only annotations, not signed server business state. Confirmation never implies task completion. Copies are unmanaged and bounded by the earliest selected retention; no model, task creation or external send. Existing synthetic export opt-in is reused with no new schema, API grant, dependency or setting. See [meeting workbench](WORK_MEETING_WORKBENCH.md). Independent originals/latest/key/full-host/retained M2 and real-content acceptance remain open. Merged prior implementation review (historical private reference omitted) at `historical-source-reference-omitted`. Exact head `historical-source-reference-omitted` passed all four jobs on attempt 1 in run 42397144670 (historical private reference omitted): 694 backend, 569 PostgreSQL, 182 client and 31 browser tests, plus restore/TLS/non-root recovery checks. Five commits, one push and one PR CI run delivered the complete selected meeting capability.


## Selected professional review and reporting — merged prior implementation review/spec 043

The new selected review workspace provides local search/facets, owner/due summaries, UTC activity and a reviewed status report over confirmed notes. Review, meeting and JSON export have distinct keys and invalidate each other on open; acknowledgements cannot transfer between tools. See [review and reporting](WORK_REVIEW_REPORTING.md).
