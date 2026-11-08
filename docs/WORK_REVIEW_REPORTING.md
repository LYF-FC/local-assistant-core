# Selected professional review and reporting

Spec 043 is merged in prior implementation review. It combines selected professional-memory review, search/facets, owner and due-date views, dated activity summaries, source/version inspection and a reviewed status-report download. It uses no model and sends no private content to an external service.

## Open and select

Use a checked checkout with the existing synthetic Work notes and notes-export opt-ins described in [notes export](WORK_NOTES_EXPORT.md). No new flag, migration, permission, dependency or credential is needed. Defaults remain disabled. Preserve existing users, project, volumes and host trust when updating; test fixtures belong only on disposable test stacks.

In Work Companion, load an explicitly assigned workspace and current notes, then choose **Review work and prepare a report**. Select up to ten available confirmed notes from the displayed page and load the review. Drafts are excluded. Nothing automatically pages or selects your workspace, and this is not a complete professional-memory search.

## Review the selected snapshot

Search selected labels, source labels, owner labels or note IDs. Combine kind, explicit owner, source, action due-date and activity filters; all filters intersect. Owner/source IDs distinguish equal labels. Counts and owner groups reflect only visible notes and show the selected denominator. Citations remain stable when filtering or sorting; gaps in citation numbering are intentional.

Due buckets compare explicit dates with the reviewed server snapshot: before snapshot; from snapshot up to seven days later; later; or Unknown. The seven-day upper boundary is excluded. Non-actions do not match action due-date filters. The same reference time is captured for the fresh download so metadata refresh cannot silently change the reviewed classification. A past due date does not prove an action is incomplete. Completion remains Unknown; confirmation is not completion. Names or text such as Done never assign status or a commitment.

Activity views use current record `created_at` or `updated_at`, with explicit UTC bounds: start included, end excluded, maximum 366 days. These are not an event history, a comparison with a saved previous report, or proof of net progress. Created/updated counts may overlap. Default bounds cover the seven days before the snapshot. A future part of a chosen window contains no observed future events. Review order supports selection order, due date and most recently updated; ties keep selection order.

The title, query, filters and activity window stay in browser memory. They are not sent to the API, persisted as preferences or signed server business records. Opening JSON export or meeting preparation closes the review and invalidates its private state; opening review does the same for those tools. They cannot reuse acknowledgements.

## Download a reviewed visible report

Inspect the visible notes, source UUIDs, note UUID/revision, snapshot validity and earliest selected retention. Acknowledge **I reviewed the visible report and will manage its copy and retention**, then download. An empty projection or invalid title/window cannot download. Every filter, title, window or order edit revokes acknowledgement; changing selection requires another snapshot.

Download re-fetches **all originally selected notes**, including locally filtered-out notes, with drafts excluded, the exact reviewed hash and copy acknowledgement. The report is then built from that fresh authorized response with the captured local filters/reference time. Only visible notes and their citations appear in the Markdown; the header states the visible/selected denominator. If a hidden selected note changed or became unavailable, the whole review must be prepared again rather than silently narrowing authority. A fresh export ID and generated time identify the checked bundle.

The Markdown includes local filter/window annotations, summary, ID-based owner groups, current record timestamps, explicit unknowns and source/version footnotes. Dynamic text is escaped; output is limited to 64 KiB without truncation. Filenames contain validated workspace/export UUIDs rather than a private report title. The earliest retention of the entire selected set remains the copy deadline even when the visible report is narrower.

The existing export receipt attests to note-bundle preparation, not a signed report, actual file saving or deletion. The downloaded file is an unmanaged copy. Forgetting, source withdrawal, expiry or session revocation cannot retrieve or erase it. Keep it locally and delete it by the stated deadline. No message, calendar entry or task state is written.

## Lifecycle and limits

Existing current membership/session, source/owner/policy, revision, retention, Origin and CSRF checks govern each API export. Relevant note reads/writes/paging, denial, expiry, workspace/session changes, close, cancellation and unmount clear/abort report state and suppress late file creation. Blob URLs are revoked. The existing conservative snapshot deadline still applies; there is no localStorage or report store.

This expands synthetic product usefulness without enabling real employer content, backend-wide search, task completion, inference or a connector. Original/source/latest completeness, independent key/other-derived/unmanaged copies, full-host restore, retained M2 and real-content acceptance remain separate. See [Work Companion](WORK_COMPANION.md), [meeting preparation](WORK_MEETING_WORKBENCH.md) and [recovery assessment](RECOVERY_ASSESSMENT.md).

## Verification

Pure tests exercise intersecting facets, ID grouping, unknowns, exact activity/due boundaries, pinned reference time during fresh export, stable ordering/citations, invalid timestamps/options, report projection/provenance/escaping, empty and oversized output. Actual HTTPS browser tests cover controls, fresh hash/ack/selection binding, no report annotations in API bodies, responsive layouts, empty/invalid views, acknowledgement/selection and sibling-tool invalidation, injected 401/403/409 refusals, cancellation of a held actual backend response, expiry and navigation unmount. Injected refusal responses supplement existing server authorization tests; they do not prove new server checks.

Use disposable Linux containers for local real-browser execution with CA trust only inside that browser container. Never alter an owner's host CA store as a test side effect. Full final exact-head four-job CI remains required and is recorded in the PR, without an evidence-only source push. Existing backend/schema/dependencies and workflows are unchanged; the new cases join the existing container browser job.

## Merged delivery

Merged prior implementation review (historical private reference omitted) at `historical-source-reference-omitted`. Exact head `historical-source-reference-omitted` passed all four jobs on attempt 1 in run 42400297126 (historical private reference omitted): 694 backend, 569 PostgreSQL, 212 client and 39 browser tests, plus recovery/TLS/container checks. Five commits, one push and one PR CI run delivered selected professional review/reporting. Independent owner-host/recovery and real-content gates remain open.
