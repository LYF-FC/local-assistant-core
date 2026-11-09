# Reviewed invoice filing plans

[Spec 057](../specs/057-invoice-filing-plans/spec.md) adds the proposal/review part of DOC-03 on [human-reviewed invoices](INVOICE_REVIEW.md). Use synthetic documents during development. No data leaves the installation. This feature creates no file, folder, network connection or execution job.

## Suggest, correct and approve

Open a reviewed invoice in document detail. A suggestion requires confirmed issuer, invoice number and issue date; unknowns never invent values. Fixed policy `invoice-filing-v1` converts labels to bounded ASCII slugs and suggests `invoices/<year>/<issuer>/<date>_<issuer>_<number>_<full-document-uuid>.pdf` (or `.txt`). The UUID distinguishes sources when labels normalize to the same slug; it does not certify business identity. Labels that cannot produce a usable slug require a manual destination.

Alternatively, enter both a logical folder and filename. Folders begin `invoices/` and contain one or two lowercase ASCII alphanumeric/hyphen/underscore segments, each at most 64 characters. Filenames use lowercase ASCII letters/digits/dots/hyphens/underscores, at most 160 characters, and the original `.pdf`/`.txt` suffix. Traversal, separators in names, repeated dots, reserved Windows device names, encoded/absolute/drive/URL/Unicode/control paths are rejected. The complete logical path is at most 384 bytes. Manual destinations express a naming decision, not a correction of invoice field truth.

Inspect possible invoice duplicates separately. These hints cannot inventory destination folders or guarantee absence of collisions. Approval requires two explicit acknowledgements: the saved plan alone is approved, and duplicate hints do not check destination collisions. Approval cannot authorize any future worker; every plan permanently records `execution_authorized: false`. The UI never claims that filing occurred. Any later execution feature needs its own current permissions, destination/root validation, exact action authorization and recovery tests.

Withdraw a proposed/approved plan or save a replacement proposal. Changes to saved invoice fields or candidate reset clear the current plan and require new review. Unsaved field edits disable plan changes until saved or reloaded. Any document revision/review withdrawal withholds old fields and paths; historical provenance remains creator-only. Revision conflicts keep local drafts for explicit reconciliation, without automatic retry.

## Permissions, history and operations

Only the creator may change a plan. Shared readers inspect current eligible plans; private content still needs creator identity and the current grant. Administration grants no content privilege. Current source, invoice and session authority stay locked through metadata audit commit; path/value content stays out of audit/logs. Plans share invoice revision history, five-revision export pages and the 100 active revision limit. At that limit, proposal changes, approval and withdrawal pause; terminal forgetting remains available.

No new tables, migration, dependency, configuration or service is added: optional versioned payloads use existing migration 0028 protections. Legacy invoice payloads without plans remain readable. Normal logical backups include plan provenance and state; the full restore sentinel verifies approved plans remain non-executable and forgotten histories stay scrubbed. Before rollback, stop writers and preserve a protected backup/export; older application versions do not implement plan invalidation and must not continue invoice writes as if this contract remained enforced.

Invoice-only forgetting terminally scrubs all plans/history/keys and retains the original. Document forgetting scrubs source and derived content/history atomically. Withdrawal preserves history; it is not erasure. Downloaded exports and older backups cannot be recalled. UI drafts stay in memory and clear with source/revision/scope/view/session changes.

Restricted mail/email provenance, destination authorization/configuration, real root/symlink/collision/capacity checks, limited local/Synology apply/rollback and crash/retry-safe exactly-once effects remain open. DOC-04 inventory, reorganization previews and rollback manifests are distinct retained scope. Retained established-rule auto-filing remains future configured execution policy; these plan records do not implement or authorize it. Proposal review alone does not complete MVP-03 or authorize private adoption.
