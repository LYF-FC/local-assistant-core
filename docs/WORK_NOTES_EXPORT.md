# Selected synthetic Work notes export — spec 029

The optional Work notes screen can preview and download up to ten explicitly selected current notes from one synthetic workspace. Confirmed notes are the default; unconfirmed drafts require an explicit option. This is a manual JSON copy, not an import, transcript archive, history export, model context or execution approval.

## Activation and use

Standard setup remains disabled. The independent `BUTLER_WORK_NOTES_EXPORT_ENABLED` flag defaults to false and also requires the existing notes-interface and protected-adapter setup. The deliberate complete-interface overlay now includes export. Existing `app.work_notes_storage` provisioning supplies its restricted read/prepared-audit privileges; no migration, new grant, owner credential or export directory is added. Preserve current users, CA, secrets and volumes.

Load the assigned synthetic workspace and open notes. Choose **Export selected notes**, select up to ten notes on the current page, and choose **Preview selected export**. Hidden, expired and forgotten notes cannot be selected. Changing pages/options/selections clears the preview; selecting drafts requires the explicit checkbox. The server rejects a stale/unavailable selection as a whole rather than silently omitting an item.

Review the current text, state/version, sources, unknown owner/date and retention limit. Acknowledge that you will manage the separate downloaded copy, then choose **Download reviewed JSON**. This performs a fresh server request with the same selections and a hash of the reviewed contents/references. Revoked access, withdrawn sources, changed versions or changed reference availability fail without a file. There is no download from an old browser-only preview.

The archive contains schema/mode/workspace/export IDs, generation/retention times, current records with actor/timestamps/policy/source IDs, current registered reference labels and explicit unknowns. It includes no old revisions, raw debrief, session credential or inspection hash. Existing sample sources do not become durable transcript provenance by appearing in an export. The filename contains only workspace/export UUIDs. Ten selected notes and a canonical UTF-8 size ceiling of 32 KiB bound the operation; choose fewer notes if too large.

## API and current authority

POST `/api/v1/work/workspaces/{workspace}/notes/export` with `purpose: "preview"`, `selections: [{id, expected_revision}]` and optional strict `include_drafts: true`. Default draft inclusion is false. A download uses `purpose: "download"`, identical selections/draft option, the preview's `reviewed_hash` and strict `acknowledge_copy_limits: true`. Actor/workspace overrides, duplicate/oversized selections, stale revisions and extra fields are rejected.

Every request checks HTTPS/Host/Origin/session/CSRF/current synthetic workspace grant before private credential loading. It validates the restricted same-database role, locks records in UUID order and checks current live source/policy/owner references. Required private prepared-read audit and metadata-only identity commit precede release. Expiry is checked again after the identity commit. No new write authority or stored server archive is created.

Preview validity is at most 60 seconds, bounded by session/note/party expiry. The archive's declared retention is the earliest note/reference retention, not the short preview/session deadline. A changed source-reference state cannot silently alter the reviewed download because its current content/retention hash must match. No public audit or archive carries that transient inspection/review hash.

## Receipt, retention and copies

Each preview/download preparation records a unique export ID in `work.notes_export_preview_prepared` or `work.notes_export_download_prepared` identity audit, with workspace, original session, record/revision bindings, bytes, declared retention and draft policy. It stores no note text, source/owner labels or content hash. Private per-note prepared-read audit is retained. The file's export ID can be matched to its workspace-bound preparation receipt by an authorized audit operator.

A receipt proves preparation, not successful browser saving, destination security, file integrity after editing, encryption or deletion. A cancelled/failed browser response may still have a preparation receipt. `managed_copy: false` and `current_revisions_only: true` describe the actual archive contract; no automatic import/execution authority follows from the file.

**Butler cannot erase a downloaded file when the note is forgotten or retention ends.** The owner must manage that file and its independently copied/backed-up versions. Live note forgetting still scrubs the normal operational records; independent exports, older backups, document keys and future derived stores remain separate recovery/reconciliation gates. There is no cryptographic deletion or full-host recovery claim.

The screen clears selected preview content on mutation, reload, denial/credential failure, expiry, view/workspace/session change or explicit export cancellation. An aborted late response cannot create a file. Short-lived Blob URLs are revoked; no local/session storage, shared cache, background job, logging or external AI receives content.

## Verification and next work

Negative source/database/client cases cover scope, default flags, explicit draft inclusion, all-or-nothing staleness/expiry/source denial, exact hash/reference binding, byte ceiling and private/public audit/commit/expiry failures. Actual HTTPS browser tests inspect the downloaded JSON and verify acknowledgement, fresh download, expiry and cancellation/denial/navigation without late file creation; screenshots cover mobile/desktop. Logical restore includes a metadata-only export-receipt sentinel. Exact final-head CI and visual evidence are recorded in the delivering PR.

Next: bounded retention/restore reconciliation and remaining independent source/key/derived-copy/old-backup/host acceptance. Real employer data, durable transcripts and full spec 005 remain gated.


## Synthetic meeting preparation workbench — merged prior implementation review/spec 042

Select up to ten confirmed notes from the displayed page, review deterministic agenda groups and explicit action follow-up unknowns, inspect source/record-version citations, and acknowledge a separate Markdown copy. Recheck the exact reviewed selection through the existing notes-export API before building the download from its fresh response. Meeting title/time are browser-only annotations, not signed server business state. Confirmation never implies task completion. Copies are unmanaged and bounded by the earliest selected retention; no model, task creation or external send. Existing synthetic export opt-in is reused with no new schema, API grant, dependency or setting. See [meeting workbench](WORK_MEETING_WORKBENCH.md). Independent originals/latest/key/full-host/retained M2 and real-content acceptance remain open. Merged prior implementation review (historical private reference omitted) at `historical-source-reference-omitted`. Exact head `historical-source-reference-omitted` passed all four jobs on attempt 1 in run 42397144670 (historical private reference omitted): 694 backend, 569 PostgreSQL, 182 client and 31 browser tests, plus restore/TLS/non-root recovery checks. Five commits, one push and one PR CI run delivered the complete selected meeting capability.


## Selected professional review and reporting — merged prior implementation review/spec 043

Status-report download checks all originally selected confirmed notes with the existing reviewed hash/ack before projecting a local filtered subset. The report records visible/selected scope and fresh export metadata, retaining the pinned reviewed reference time for due classifications. Existing receipts do not authenticate local report annotations or prove saving/deletion. See [review and reporting](WORK_REVIEW_REPORTING.md).
