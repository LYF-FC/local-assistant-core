# Plan / analyze

**Status: proposed plan for owner review. Nothing here is implemented.** Drafting this plan changes no implementation status, status counts, verification or owner acceptance. Gate 2 stays open; CORE-08 and UI-01 stay partial. It does not approve the five-priority order. Scope, requirements and acceptance scenarios are those of [spec.md](spec.md) and are not widened here.

## Approach

Add one explicit **Inbox** view that composes existing protected reads for one granted scope at a time, plus one new read-only backend query for pending generic approvals. It follows the pattern already proven by the daily overview (spec 062) and scoped search (spec 067): client-side composition with `Promise.allSettled`, explicit refresh, per-section `available`/`unavailable` state, a 60-second view expiry, authorization denial clearing every section, and navigation that carries only minimal identity so the destination re-reads under current authorization.

1. **Backend, approvals list (the only server change).** Add `POST /api/v1/approvals/query` beside the existing approval routes. It reuses the peer query pattern (session, CSRF, exact scope grant, lock and statement timeouts, session refresh, denial codes), selects `pending`, unexpired, bound rows for the requested scope with `id` cursor paging (25 plus a 26th-row sentinel), writes no approval row, applies no lazy expiry, and records one metadata-only audit event per request. It returns only the allow-listed item fields and a server-computed `requested_by_you`. No schema, migration or grant change is planned; that holds only if the audit event-name recheck below finds no new constraint.
2. **Client composition.** Add a typed source adapter (`attention-inbox.ts`, name provisional) that issues the eight reads: approvals, tasks (open, overdue), reminders (delivered), documents (`reviewed_only=false`, unreviewed or extraction-failed selected client-side), filing (`failed` and `unknown`) and notifications (`failed` and `unknown`). Strict per-source parsers validate scope, owner/visibility, selected filters, ID and cursor bounds, revision and freshness, and project to the minimal card fields. Malformed or failed sections become `unavailable`, never empty.
3. **Inbox view.** Add the Inbox panel to the existing records workspace and view switcher. It renders grouped sections, status/evidence/uncertainty lines, per-source retry, the empty-state wording rules and the non-atomic notice. It embeds an entry to the existing scoped search view and re-implements nothing from it.
4. **Navigation.** Reuse the existing task, reminder and document destinations. Notification failures link to the related reminder and filing failures to the related document, only when visible and not scrubbed. **Pending approvals are evidence-only**: no destination, no Open, decide, cancel or consume control, and no request to `GET /approvals/{id}` or its operation routes.

## Files expected to change at implementation (provisional)

Approvals service and routes (`backend/app/approvals.py`, `approval_routes.py`); new client adapter, panel and unit tests under `frontend/src/`; the view switcher and workspace in `RecordsWorkspace.tsx`; a new Playwright spec under `frontend/e2e/`; backend tests beside `test_approvals.py` and a PostgreSQL integration test; a new contract document, plus the master gate entry, the register rows and the regenerated overview and dashboard in the same PR, as the repository rules require for a PR that changes delivered behaviour. This plan itself edits none of them.

## Constitution and data/permission analysis

- **Authority:** current identity and exact scope grant on every read; no new permission, role, grant, approval authority or executor. The inbox cannot decide, cancel, consume, retry, acknowledge, file, send or complete anything.
- **Data:** no new table, store, cache or export. Approval payload, hash, policy version, approver and requester identifiers are never selected into the response or held in the client. Browser state is in memory only.
- **Privacy:** owner-only sources (reminders, filing, notifications) stay owner-only even in a shared scope; shared tasks and documents stay read-only for non-owners.
- **Audit:** one metadata-only event per list request, committed before release; audit failure withholds the approvals results. Verified at `cec91ff`: `public.audit_events.event_type` is a free `String(128)` with no check, enum, foreign key or lookup, and only append-only triggers guard the table. The code does not fix an event name, so `approval.query` stays a **proposal**. **Implementation-time requirement:** re-confirm no later migration or code adds an event-name constraint or allow-list, and pin the final name with a test. A migration is needed only if that recheck finds a constraint.
- **Models and egress:** none. Deterministic local APIs only; no outbound or AI call.
- **Migration, export, backup, restore:** no migration planned; no new data to back up or restore. Existing backup and restore evidence remains distinct and is not claimed again.
- **Constitution conflicts:** none identified. Any conflict found later is reported, not silently resolved.

## Requirement mapping (owner-confirmed)

CORE-08 and UI-01 (the inbox); CORE-04 (approval authority, unchanged); CORE-05 (audit); CORE-10 (documents); DOC-03 (filing failures); CORE-11 (notification failures); REM-01 (manual tasks and private reminders, as the register words it); ORG-03 as well, for routine-generated tasks; CORE-09 (mobile). REV-03 is not claimed. Nothing in the mapping changes a requirement's status.

## Evidence plan

Per repository rules, audit and permission changes need negative tests and actual disposable PostgreSQL evidence with the real runtime role. Planned, for a future implementation only: unit tests for composition, expiry, dedup, denial clearing and labels; backend API tests for the approvals allow-list, visibility, status and expiry exclusion, paging, audit shape and failure, and no row mutation; PostgreSQL integration tests for real memberships, timeouts, a concurrent decision racing a list read, and the `butler_runtime` audit insert and induced failure; a Playwright workflow at 390×844 with a network-recording assertion that no state-changing request is sent. Run the required `make check` components and the integration suite once before a single grouped push; no test is added or run by this documentation package. Local non-superuser PostgreSQL reproduces known baseline integration failures; hosted CI is the cleaner signal, and deliberate skips are never reported as passes.

## Risks carried from the spec

Approvals have no in-app destination (evidence-only is deliberate); the audit event name needs the recheck above; whether the existing task response marks routine origin is checked at implementation time and origin is shown only if it already exists; eight reads per refresh are bounded by 25 rows each with no load measurement claimed; the approvals section will usually be empty until domain actions exist.
