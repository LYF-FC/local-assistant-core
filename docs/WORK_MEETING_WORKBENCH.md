# Synthetic meeting preparation workbench

Spec 042 is merged in prior implementation review. This is a selected-note preparation tool, not a meeting recorder or task executor. It uses no model and sends no content to an external provider.

## Availability and preparation

Use a checked checkout with the existing synthetic Work notes and notes-export opt-ins from [notes export](WORK_NOTES_EXPORT.md), the current authenticated session, and an explicitly assigned synthetic workspace. Standard POC defaults remain disabled. There is no new flag, migration, permission, credential or dependency. Preserve the owner's existing project, users, volumes and CA settings when updating; do not run test fixture scripts against that stack.

Read the current page of notes, then choose **Prepare a meeting**. Enter a short title using letters, numbers, spaces, underscores, periods or hyphens; optionally set an explicit meeting time. Select one to ten currently available confirmed notes from this page. Drafts are excluded, and the page is not a complete workspace inventory. Title and time remain annotations in browser memory and are not sent to the export API or persisted as meeting records.

Preview the brief. Actions, decisions, questions and observations are grouped deterministically; each record retains a generated citation and source/record-version details. Owner absence, unavailable owner, missing due date, unknown meeting time and action completion stay explicit unknowns. Due-by/after classification uses only an explicit meeting time and stored due date. Confirming a note does not mark an action complete or infer a commitment from its text.

## Reviewed download and copy responsibility

Review the exact selected contents, provenance, current snapshot deadline and earliest retention. Acknowledge **I will manage the meeting copy and its retention**, then choose **Download reviewed meeting Markdown**. The client calls the existing export API again with drafts excluded, the reviewed hash and acknowledgement. It creates Markdown only from the freshly authorized response; a stale or refused review must be prepared again. A new export ID is expected. The API never receives the local meeting title/time.

Markdown includes source labels and UUIDs, note UUID/revision, owner reference, generated/export timestamps, workspace, retention and known unknowns. Dynamic text is escaped; the output is capped at 64 KiB without truncation and the filename contains validated UUIDs, not private titles. A meeting at or beyond retention receives a warning; choosing a later time cannot extend retention.

The existing preparation receipt attests to the governed JSON note bundle, not a server-signed meeting document, actual file saving or deletion. The Markdown includes user annotations. The downloaded file is an unmanaged separate copy: source withdrawal, forgetting, session revocation and expiry cannot retrieve or erase it. Manage it locally and delete it by the earliest copy-retention deadline. No upload, email, task creation or calendar write occurs.

## Privacy lifecycle

Changing title, time or selection invalidates review and acknowledgement. Relevant note reads/writes/paging, workspace or session changes, denial, expiry, close, cancellation and unmount clear/abort private meeting state and suppress late downloads. Blob URLs are revoked. Existing conservative snapshot deadlines apply. Nothing is stored in localStorage. Other derived views share the parent cancellation boundary and use distinct React keys.

Current source/owner/revision/retention, permission, session, Origin and CSRF checks remain authoritative at the export API. This bounded synthetic feature does not accept real employer content or replace independent originals/latest-source evidence, key recovery, other derived/unmanaged copy handling, full-host restore and retained owner M2 acceptance.

## Verification

Local evidence: make check passed 694 backend and 182 client tests, production build, Ruff/format and repository policy; 16 real PostgreSQL export cases passed. The meeting model/Markdown add 28 client cases. Five isolated browser cases exercise review/download/invalidation, stale refusal, session/expiry and late cancellation. Six additional cases use the real isolated HTTPS stack and backend to verify selection/citations/unknowns, exact fresh download/hash/ack, annotations absent from request bodies, responsive layout, denial, expiry/unmount and a genuinely held backend response cancelled before download. Refusal cases deliberately intercept error responses; they do not claim to replace server authorization tests. Local browser TLS trusts only the disposable container's test CA, not the owner's host trust store.

The local mock harness is development-only, explicitly test-gated and absent from the production build. Linux local real-browser mode additionally requires the fixed disposable database/project/origin and isolated Caddy namespace. Hosted tests retain their existing CI project guard. All fixtures are synthetic. Six real meeting tests join the existing container job; no new job, workflow, trigger or dependency is introduced. Final four-job exact-head evidence belongs in the PR; local testing is not owner-host acceptance.

## Merged evidence

Merged prior implementation review (historical private reference omitted) at `historical-source-reference-omitted`. Exact head `historical-source-reference-omitted` passed all four jobs on attempt 1 in run 42397144670 (historical private reference omitted): 694 backend, 569 PostgreSQL, 182 client and 31 browser tests, plus restore/TLS/non-root recovery checks. Five commits, one push and one PR CI run delivered the complete selected meeting capability. Independent owner-host/recovery and real-content gates remain open.
