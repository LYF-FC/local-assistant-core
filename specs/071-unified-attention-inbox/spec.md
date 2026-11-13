# 071 — Unified attention inbox (first slice)

**Status: draft for owner review. Nothing here is implemented.** Drafting this spec changes no implementation status, status counts, verification or owner acceptance. Gate 2 stays open; CORE-08 and UI-01 stay **partial**. The Gate 2 criterion is unchanged and quoted exactly: "Dashboard exposes agenda, pending approvals, reminders, failures and authorized search." This spec defines one bounded slice of that existing scope. It does not complete or accept it, and it does not approve the five-priority implementation order (still "Proposed — awaiting owner confirmation"). The owner has confirmed this scope as the next item to develop and resolved the three decisions in [Owner decisions](#owner-decisions); that authorizes this draft only.

## Baseline

- `main` = `cec91ff49a5064ff6eae149ad43bef7398868aa9` (Merge PR #32), rechecked when this draft was written.
- Foundations reused: PR #17 daily overview ([DAILY_OVERVIEW.md](../../docs/DAILY_OVERVIEW.md), spec 062); PR #22 scoped search ([SCOPED_RECORD_SEARCH.md](../../docs/SCOPED_RECORD_SEARCH.md), spec 067); approvals foundation ([APPROVALS.md](../../docs/APPROVALS.md), merged #26); task, reminder, document, filing and notification read paths; PR #31 restart-recovery evidence for filing and notifications; PR #32 documentation reconciliation.
- Retained requirement (CORE-08, UI-01): expose pending approvals, tasks, failures and authorized search with evidence, current action status and uncertainty, and a safe path to the authoritative source or existing action flow. [FEATURE_DEPENDENCIES.md](../../docs/FEATURE_DEPENDENCIES.md) lists UI-01 behind "scoped APIs, agenda, search, approvals and durable job outcomes" and says pending approvals are a separate retained dependency, not inferred from the task/document APIs.

## Owner decisions

1. The first slice covers **generic pending approval records only** (today only `validation.noop`). Domain-specific queues are later work.
2. The approvals list is an **audited read**: one metadata-only audit event per list request, including each paginated request. If the audit write fails, withhold the results and report the approvals source as unavailable.
3. A user's own pending request is labelled **"Requested by you."** Nothing in the UI suggests self-approval is prohibited; current rules permit it.

## What the slice delivers

One explicit **Inbox** view in the existing records workspace. For one granted scope at a time it composes existing read paths plus one new read-only approvals query. It is a **read-and-link surface**: it cannot decide, cancel, consume, retry, acknowledge, file, send, complete or alter anything, and it adds no authority, queue, worker, schema, grant or live adapter.

| Section | Source (authoritative) | Existing API | Slice-1 selection |
|---|---|---|---|
| Pending approvals | `approvals` rows | **New** `POST /api/v1/approvals/query` | pending, unexpired, bound |
| Failures: filing | filing executions | `POST /api/v1/filing/query` | `state=failed`, and separately `state=unknown` |
| Failures: notifications | notification deliveries | `POST /api/v1/notifications/query` | `state=failed`, and separately `state=unknown` |
| Documents needing review | documents | `POST /api/v1/documents/query` with `reviewed_only=false` | unreviewed or extraction-failed, selected client-side as the daily overview does |
| Reminders | task reminders | `POST /api/v1/reminders/query` | `state=delivered` (default), owner-only |
| Tasks | manual tasks | `POST /api/v1/tasks/query` | `status=open`, `due=overdue` |

That is eight requests per refresh (filing and notification failures need two single-valued state reads each). Authorized search is **not re-implemented**: the Inbox offers an entry that opens the existing scoped search view (spec 067). It adds no query, index, ranking or retrieval behaviour.

Tasks are limited to open overdue tasks as a bounding choice. Due-soon and no-due-date tasks are not inferred as "needing attention" and are later work (see [Exclusions](#explicit-exclusions-and-later-work)).

## Source rules

| Source | Visibility | Ownership/grant | Freshness and expiry | Uncertainty to show |
|---|---|---|---|---|
| Approvals | Every current member of the selected scope sees every pending record in it | Current session, exact scope grant | Only `pending` with a stored `expires_at` later than the read time. Expiry is 60–3600 s from creation. | Expiry time; "stored status may lag expiry until the record is opened" |
| Filing | **Owner only**, scope-bound | Owner, scope | Row `updated_at`; revision | `unknown` = "outcome not confirmed"; the "Synthetic destination only" notice is preserved; `reason`, `attempts` shown |
| Notifications | **Owner only**, scope-bound | Owner, scope | `updated_at`; revision; `next_attempt_at` | `unknown` = "delivery not confirmed"; `reason`, `attempts`, `channel` |
| Documents | Owner or shared scope; shared records read-only for non-owners | Scope grant, edit attribution | Document review/extraction state | "Text review, not invoice-field or filing approval" as in the overview |
| Reminders | **Owner only**, even in a shared scope | Owner, scope | State; due time | Delivered is not the same as seen; acknowledgement stays in the reminders view |
| Tasks | Owner's own, or shared scope; shared read-only for non-owners | Scope grant | Due time against read time | None beyond overdue wording |

Filing, notification and reminder records of other members are never shown, even in a shared scope. A scrubbed filing execution carries no document or plan link.

## Pending approvals: `POST /api/v1/approvals/query`

Verified against current code before choosing this shape. Existing approval routes are `POST ""` (create), `GET /{id}`, and `POST /{id}/decide|cancel|consume`; **there is no list or query route**. Peer domains use `POST /query` with a scope in the body (tasks, reminders, documents, filing, notifications), so this name and shape follow the established pattern. A `POST /query` path does not collide with `POST /{id}/…` (different path shape).

**Request:** `scope` (required, one currently granted scope) and optional `after` (cursor). No other filters in slice 1.

**Authority:** the same protected-read pattern as the peer query routes: active HTTPS session and trusted Host/Origin, CSRF token (peer query POSTs require it), exact scope grant, `SET LOCAL lock_timeout`/`statement_timeout`, session refresh. Missing or invalid session is 401; a scope the actor does not hold or a missing CSRF token is 403; malformed input 422. The implementation must reuse the peer denial codes and denial auditing rather than invent new ones, and must follow the peer routes' codes (403 for a non-held scope).

**Selection (SQL, not post-filtering):** `scope_key = :scope` and the scope is in the actor's current memberships; `status = 'pending'`; `expires_at IS NOT NULL AND expires_at > now`; `payload_hash` and `policy_version` present. Unbound legacy rows cannot authorize a decision or consumption (APPROVALS.md), so they are not listed as pending. Order by `id`; cursor is `id > after`; read 26 rows, return 25, `next_cursor` set only when a 26th row exists. No total and no count of omitted rows.

**No state change by the read.** The list takes the same shared row locks as peer queries and writes **no approval row**. It does not apply the lazy `pending → expired` transition (`GET /{id}` does that, under `FOR UPDATE`); expired-but-still-`pending` rows are simply excluded by the `expires_at` predicate. Only the audit event and session `last_seen_at` are written.

**Response:** `schema_version`, `mode: "approval_page"`, `checked_at`, `page_limit: 25`, `items`, `next_cursor`. Each item carries only:

`id`, `scope`, `action_type`, `status` (always `pending`), `requested_at`, `expires_at`, `requested_by_you` (boolean computed server-side by comparing the stored requester with the actor).

It deliberately omits `request_payload`, `payload_hash`, `policy_version`, `approved_by` and the requester's identifier. The existing `GET /{id}` returns the payload and hash because it is the reviewer's exact-record fetch; the list is a pointer, not a review surface.

**Audit (owner decision 2):** exactly one event per list request, written in the request transaction and committed before the response is released, as peer queries do. Event `approval.query`, result `success`, actor, `scope_key` = the requested scope, `entity_type` = `approval`, metadata limited to `{"returned": n}` with `n ≤ 25`. No record IDs, payload, hash, cursor value or filter text in the event. Each paginated request records its own event. If the audit write or commit fails, **no results are released**: the client receives a non-success response and shows "Approvals unavailable." It never renders that as "no pending approvals." The implementation must confirm no existing database check on `audit_events.event_type` rejects a new value, and must add a migration only if one does.

**Labels (owner decision 3):** when `requested_by_you` is true the item reads **"Requested by you."** Otherwise it reads "Requested by another member of this scope." No copy states or implies that a requester cannot approve their own request.

## Item model, grouping and deduplication

Common card fields: `kind`, source record `id`, `scope`, plain-language title, **status label**, **evidence line**, **uncertainty line** (where applicable), `read_at` (the source's `checked_at`), and an optional **Open** control. Titles are inert text; source content is never rendered as markup or fetched.

- **Status labels** are read-only descriptions in the source's own vocabulary ("Awaiting a decision", "Failed", "Outcome not confirmed", "Delivered, not acknowledged", "Open, overdue", "Needs review"). They never read as an available action.
- **Evidence** is the minimum that explains why the item is here: approval `action_type` and `expires_at`; filing/notification `state`, `reason`, `attempts`, `updated_at`; document review/extraction state; reminder due/delivered time; task due time.
- **Grouping:** by section, in the order Approvals, Failures (filing, notifications), Documents needing review, Reminders, Tasks. **No cross-source ranking, scoring, total or badge count.** Within a section the source's own stable `id` order is kept; the UI does not claim it is oldest-first or most-urgent-first. A section header states "First page" and, when `next_cursor` exists, "More records exist; this is not a complete count."
- **Deduplication:** identity is (source kind, record `id`). The same record appearing twice (for example across a refresh) renders once. If a notification or filing record is read in two state queries because it changed between reads, the higher `revision` wins; on a tie the later read wins and the card notes "changed during refresh." A document that is both unreviewed and extraction-failed is **one** card with two labels. Separate record kinds are never merged: a filing failure is not hidden behind its document. A filing or notification card may show a related-record reference (the document, or the reminder) as a link only when that record is visible to the actor and not scrubbed; the reference does not create a second inbox item.

## Navigation (read-and-link)

Opening an item passes only the minimum: kind, record `id`, scope, and revision where the source has one. **No payload, title, evidence text or status is carried.** The destination re-reads the record under the user's **current** authorization before rendering, validates id, scope, ownership and revision, and uses its own confirmation steps for anything consequential. A stored inbox snapshot never becomes authority.

Existing destinations (`Destination` in the records workspace) cover calendar, tasks, reminders and documents. For the new kinds:

| Item | Destination in slice 1 |
|---|---|
| Task | Tasks view, selected scope |
| Reminder | Reminders view, selected scope |
| Document needing review | Documents view, selected scope and document |
| Notification failure | **Reminders view** for the related reminder (owner-only). The delivery record itself has no screen; the card shows its evidence and no Open on the delivery. |
| Filing failure | **Documents view** for the related document when not scrubbed. The execution has no screen; the card shows evidence and no Open on the execution. |
| Pending approval | A **read-only approval detail** view (new, minimal): explicit open calls the existing `GET /api/v1/approvals/{id}`, shows status, scope, action type, expiry and the "Requested by you" label, and has **no** decide, cancel or consume control. It does not render `request_payload` in slice 1. |

The approval detail view is the only new screen. It is read-only and exists because no approvals UI exists today. Decision, cancellation and consumption UI is later work. The existing `GET` records its own audit read event and may apply expiry; that is existing, documented behaviour reached only by an explicit open.

If the destination read returns 401/403/404/410, or the record is no longer visible, the destination shows a plain "no longer available or not permitted" state, returns the user to the Inbox, and the denied item is removed. 401 signs out.

## Refresh, freshness and failure

- **Explicit refresh only.** No automatic query on open, no polling, no background reload, no retry loop.
- **Not an atomic snapshot.** Sources are read concurrently (`Promise.allSettled`) at slightly different instants. The view says so, shows each section's `read_at`, and never asserts cross-source consistency.
- **Expiry:** the whole view expires at the earlier of 60 seconds from refresh start and the earliest `expires_at` among displayed approvals. At expiry, all items, cursors and evidence are cleared and the view shows "Refresh to see current items." An approval past its own `expires_at` is removed even earlier than the view.
- Items, cursors and state are cleared on hidden tab, scope/view/session/membership change, logout and expiry. Late responses are discarded (generation and abort guards). Paging one section cannot extend another's deadline.
- **Unavailable sources:** each section is available or unavailable. A failed, timed-out, malformed, or audit-failed source shows "unavailable" with a **per-source Retry** control that re-reads only that source. It is never shown as empty and never contributes a zero.
- **Partial results:** available sections still render. The view states which sources loaded.
- **Authorization denial (401/403/404/410) from any source clears every section, the query state and cursors** and withdraws all item content, following the overview and search; 401 also signs out. Malformed responses count as unavailable. No raw error text is shown.
- **Empty states:** when **every** source loaded and nothing matched: "Nothing needs attention in the sources that loaded." This sentence is **only** shown when every section loaded. If any source is unavailable, the view shows "Some sources are unavailable. Nothing is shown for them, which does not mean nothing needs attention," and sections that loaded and are empty say "None in this first page."

## Privacy: never cached or exposed

The inbox never stores, logs, transmits or displays: approval `request_payload`, `payload_hash`, `policy_version`, `approved_by`, or another member's user identifier; any session or CSRF token; query bodies or cursors beyond the in-memory view; item content in URLs, `localStorage`, `sessionStorage`, IndexedDB, telemetry or service-worker caches. State lives in memory only. The new endpoint and audit event contain no payload or hash. Reminders, filing and notification records of other members are never requested into a view where they would be visible.

## Mobile and accessibility

The existing interface checks apply: no horizontal page scroll at a 390×844 viewport; single-column layout with collapsible sections; controls operable by keyboard with visible focus and accessible names; status and unavailable messages in a live `role="status"` region; meaning never carried by colour alone. The inbox applies the **existing** usability obligations only. It does not claim REV-03 (accessibility and interruption recovery), which remains an after-existing-scope item.

## Explicit exclusions and later work

| Not in slice 1 | Why / dependency |
|---|---|
| Deciding, rejecting, cancelling or consuming an approval from the UI | Needs its own spec: decision UX, payload-hash/policy-version display, self-approval presentation. `validation.noop` only today. |
| Domain-specific queues (invoice plan approval, memory review, discovery review, filing approval) | Each has its own authority and state machine; add one at a time after the generic path is proven (owner decision 1). |
| Dead-letter and background-job failures | `POST /operations/read` is `technical_admin`-only and returns aggregate counts with no per-job IDs. Needs a per-job read path and an owner decision on that scope. |
| Calendar source status, conflicts | Already in the day briefing; merge later if wanted. |
| Due-soon and no-due-date tasks; acknowledged/cancelled reminders | Not "needs attention" without a policy; later. |
| Rendering approval payloads | Needs a reviewed redaction/display contract. |
| Retry, acknowledge, re-file, resend, complete from the inbox | Each is a consequential action with its own confirmation; stays in its owning flow. |
| All-library or semantic search; Memory/Work/Finance search | Separate retained dependencies (spec 067 and the register). |
| Cross-source ranking, totals, badges, push or e-mail alerts, polling | Need a combined-ordering and notification contract. |
| Delivery-record and filing-execution screens | No existing UI; slice 1 links to the related reminder/document instead. |
| Private remote/mobile host acceptance | Gate 2's other outstanding criterion; real-device evidence is separate. |

## Acceptance scenarios (measurable, for a future implementation)

Each is binary and testable. IDs are for traceability.

**Positive**
- A1. With a pending unexpired approval, an overdue open task, an unreviewed document, a failed filing, an unknown notification and a delivered reminder in one scope, one refresh shows exactly one card for each, in the section order above, each with status label and evidence.
- A2. The approvals response contains only the listed item fields; a response-schema test fails if `request_payload`, `payload_hash`, `policy_version`, `approved_by` or the requester id appears.
- A3. A user's own pending request reads "Requested by you"; another member's reads "Requested by another member of this scope." Neither text mentions a self-approval restriction.
- A4. 26 pending approvals return 25 items and a `next_cursor`; the next page returns the remainder; no total or omitted count appears.

**Authorization and privacy**
- P1. A non-member of scope S gets the peer denial for S and sees no approval of S; a member of S sees S's pending approvals regardless of who requested them.
- P2. Another member's reminder, filing execution and notification never appear in a shared scope.
- P3. A shared task and a shared document appear read-only for a non-owner.
- P4. After refresh, browser storage, URL and telemetry contain none of the item titles, ids, payloads or hashes.

**Expiration and freshness**
- E1. An approval with `expires_at` in the past, status still `pending`, is absent from the list and the read made no approval-row write.
- E2. Approved, rejected, cancelled, consumed and expired approvals never appear; an unbound legacy pending row never appears.
- E3. The view clears all items at 60 seconds, or at the earliest displayed approval's `expires_at` if sooner, and shows "Refresh to see current items."
- E4. A hidden tab, scope change, view change, logout or membership change clears items; a late response after clearing is discarded.

**Audit**
- U1. Each list request, including each page, writes exactly one `approval.query` event with metadata `{"returned": n}` and nothing else identifying records; three pages produce three events.
- U2. With the audit write forced to fail, the response releases no items, the Approvals section shows unavailable, other sections still render, and the view does not say "nothing pending."

**Partial failure**
- F1. With filing forced to fail, filing shows "unavailable" with a Retry; all other sections render; the empty-state sentence "Nothing needs attention…" is not shown.
- F2. Retry on one section re-requests only that source (one request).
- F3. A malformed response from one source marks only that source unavailable and renders no raw error.
- F4. With every source succeeding and returning nothing, the view shows "Nothing needs attention in the sources that loaded."

**Navigation**
- N1. Opening a task, reminder or document passes only kind, id, scope (and revision where present) and the destination rereads under current authorization.
- N2. If the user's grant to the scope is revoked after refresh, Open yields the "no longer available or not permitted" state, the inbox clears, and no stale item remains.
- N3. A pending approval opens the read-only detail view; it renders no decide, cancel or consume control and no payload.

**Duplicates**
- D1. The same record read twice renders once. A notification that changes state between its two reads renders once, higher revision winning. A document both unreviewed and extraction-failed renders as one card with two labels. A filing failure and its document appear as two separate cards.

**No state-changing requests**
- S1. Across load, refresh, retry, paging, Open and expiry, the browser sends **no** `POST`/`PUT`/`PATCH`/`DELETE` request other than the eight read queries and the approvals query, and never calls `/approvals/{id}/decide|cancel|consume`, any filing or notification action, reminder acknowledge/complete, task transition, or document review/forget. A network-recording test asserts the exact request set.
- S2. Cross-site and no-CSRF requests to the new route are refused.

## Tests needed (not added or run in this documentation-only task)

- **Unit (TypeScript):** source composition with `Promise.allSettled`; section state (available/unavailable); expiry deadline calculation; dedup key and revision tiebreak; denial clearing; empty-state selection; label text for "Requested by you."
- **API (backend):** approvals-query matrix (member, non-member, each status, expired-pending, unbound legacy, cursor and 26th-row behaviour); response-field allow-list; audit event shape and count per request; audit failure withholds results; no approval row mutation; CSRF/Origin/session denials; uniform denial for non-held scopes.
- **Integration (PostgreSQL):** real scope memberships and visibility; lock and statement timeout behaviour; concurrent decision racing a list read; audit committed with the response. Note the local non-superuser role reproduces known baseline integration failures; CI is the cleaner signal.
- **UI (Playwright):** the scenarios above, a 390×844 viewport with no horizontal scroll, keyboard operation and live-region announcements, partial-failure rendering, expiry clearing, revoked-grant navigation, and the S1 network-recording assertion.
- **Repository checks:** existing `make check`, security/privacy and generated-dashboard checks. This spec adds no generated output.

## Risks and unresolved decisions

1. **Navigation gaps.** Filing executions, notification deliveries and approvals have no screen today. This spec proposes related-record links and a minimal read-only approval detail. If the owner prefers evidence-only cards with no Open for approvals, the approval detail view is dropped and approvals become evidence-only. **Decision needed.**
2. **Approval payload in the detail view.** Defaulted to "not rendered." Revisit with the first domain-specific queue.
3. **Task scope of "attention."** Defaulted to open overdue only. Reviewer may widen.
4. **Audit event type.** `approval.query` assumes no database check rejects the value; implementation must verify and add a migration only if needed.
5. **Denial codes.** Peer query routes answer 403 for a non-held scope and for a missing/invalid CSRF token, and 401 for a missing session (verified in the shared task `authority()`); the new route must reuse those, with its own event prefix, and must not invent a different status.
6. **Mostly-empty approvals** in real use until domain actions exist; the section will usually be empty by design.
7. **Risk of reading as a decision surface.** Mitigated by labels, no action controls, and test S1.
8. **Eight reads per refresh** are bounded by 25 rows each and explicit refresh; no load measurement is claimed here.
9. This spec does not approve the five-priority order, and a spec exists in `specs/` without being listed as implemented anywhere.

## Traceability

| Behaviour | Requirement | Contract / source |
|---|---|---|
| One Inbox view of approvals, failures, documents, reminders, tasks; search entry | CORE-08, UI-01 | FEATURE_REGISTER rows; MVP_ACCEPTANCE Gate 2 (criterion unchanged) |
| Approvals visibility, statuses, expiry, binding, no new authority | CORE-04 | APPROVALS.md; `approvals.py`, `approval_routes.py` |
| One audited read per list request; audit failure withholds | CORE-05 | APPROVALS.md audit rules; peer `tasks.query` audit pattern |
| Explicit refresh, 60-second expiry, per-source unavailable, denial clearing | CORE-08, UI-01 | DAILY_OVERVIEW.md (spec 062); SCOPED_RECORD_SEARCH.md (spec 067) |
| Task and reminder reads | REM-01 | task and reminder query routes |
| Document reads and source state | CORE-10 | document query route; DAILY_OVERVIEW.md |
| Filing failures, uncertainty wording | DOC-03 | filing query route; PR #31 evidence |
| Notification failures, uncertainty wording | CORE-11 | notification query route; NOTIFICATIONS.md; PR #31 evidence |
| Read-only link-out with reread under current authorization | UI-01 | spec 067 destination rule |
| Mobile viewport and usability checks | CORE-09, UI-01 | existing e2e viewport checks; REV-03 explicitly not claimed |
| Dependencies and later queues | UI-01 | FEATURE_DEPENDENCIES.md |

Nothing in this table changes a requirement's status.
