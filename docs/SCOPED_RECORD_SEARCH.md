# Scoped task and document search — spec067 branch

Choose **Search records**, select one granted household/member-private scope and enter keywords. Search starts only when submitted. It checks manual task title/details across all statuses and document title/extracted text, including unreviewed text. Sources may be uncertain: results label task state, document review and non-ready extraction. Keyword matching is literal and case-insensitive under the existing server contracts; it is not semantic retrieval or generated advice.

## Pages and failures

Results are grouped by library, at most25 per library page, with independent explicit next-page controls. No combined relevance ranking, global total or complete match count is presented. Requesting the next document page leaves the task page unchanged; later pages and unsearched libraries may contain additional work. A failed or malformed library is unavailable, never called empty. Any authority denial withdraws all results and the query;401 returns to sign-in.

Only the selected granted scope is searched. Shared records can belong to another member and remain read-only; private records must belong to the current actor. Finance, Memory, Work, approvals and other libraries are outside this view. Technical administration alone grants no supported search scope. Original pending-approval/unified inbox and broader search requirements remain retained.

## Current sources and navigation

Select **Read current task/document** to reread the protected current source. Search hits contain only metadata, not task details or document bodies. The current task preview can show its dated status/details; the document preview shows provenance/hash/review/extraction metadata. Existing document read receipts include text transiently during validation, but search state/navigation never retains it. Nothing is fetched from a source reference or interpreted as HTML.

A source may have changed since matching. ID, scope, owner, creation identity and monotonic revision are checked before presenting it. Gone/forgotten sources clear the search; stale or mismatched receipts do not become current authority. **Open full task/document record** carries only minimal identity/revision metadata. The destination rereads with current authorization; full document text is retained only in the existing document view, not in search or the workspace navigation target. Source edits keep existing server revision/owner controls.

## Privacy and implementation boundary

Query, result and current-source state stay in memory. Queries use protected POST bodies, never URL parameters, browser storage, telemetry or local exports. Printable nonblank text is bounded to160Unicode characters. All search state clears on hidden tab, scope/view/session/membership changes, denial and at most60seconds from query start. Unsent drafts also expire; page/source requests cannot extend the original result deadline. Abort/generation guards reject late responses. No polling, auto-pagination, model calls, mutations, downloads or actions are introduced.

The view reuses existing HTTPS/Host/Origin/session/CSRF and task/document owner/grant enforcement and commit-before-release audit. The strict client adds owner/edit attribution, selected filters, freshness/cursor and current-source binding checks. Backend/schema/grants/dependencies/fixtures/harnesses remain unchanged; existing PostgreSQL/recovery evidence is not relabelled as a new run.

[Spec067](../specs/067-scoped-record-search/spec.md) and its convergence describe branch verification. The [dashboard](FEATURE_DASHBOARD.html) now records merged PR21 operations foundations:19/99 named features partial (MVP18/21),40/155 total partial,14 public engineering batches. No full retained feature is accepted. Current search work remains branch engineering. Whole-MVP approvals, broader search, live adapters/model quality, monitoring/outage and independent host/key/archive recovery gates remain open; real activation/private adoption need separate authorization. All155 requirements, original99 cohort/milestones and deferred order are preserved.
