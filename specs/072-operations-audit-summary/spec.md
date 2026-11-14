# 072 — Operations audit summary (first OPS-10 slice)

**Status: draft contract, implemented on a local branch. Nothing here is verified, merged or accepted.** This advances existing requirement OPS-10 ("Periodic operational audit: summarize actions, errors, access changes, overdue jobs and capacity trends") by one narrow, reviewed projection. It adds no requirement, changes no gate and promotes no status.

## Problem and outcome

The Operations overview (spec 066) states that audit review is unavailable because the runtime role has INSERT-only audit access. A technical administrator therefore cannot answer "were there sign-in denials, access changes or administrative actions recently?" without a privileged database session. The outcome is an explicit, audited, bounded **count-only summary of security and administrative audit events** for a fixed recent window, produced by a narrow database projection so the runtime role never gains general audit SELECT.

## Scope

- One protected request, `POST /api/v1/operations/audit-summary`, and one section in the existing Operations overview with an explicit **Load audit summary** control. Nothing loads with the overview and nothing polls.
- A reviewed projection: `public.butler_audit_summary(p_token text, p_end timestamptz, p_hours integer)`, `SECURITY DEFINER`, fixed `search_path`, `EXECUTE` revoked from PUBLIC and granted only to `butler_runtime`. The function takes the caller's session token, never an actor identifier, and derives the actor itself (see Authorization).
- Counts per fixed **category** and fixed **outcome** over a fixed window (24 hours or 7 days, chosen from a closed set).

## Explicit exclusions (remain open, unclaimed)

Overdue-job reporting, capacity and trend reporting, scheduled or periodic report generation, delivery or export of reports, alerting, per-event listings, per-actor or per-scope breakdowns, event metadata, any household, financial, Work, document, task, memory or approval event, long-range history, worker/backup/storage/certificate observation, and independent clean-host recovery (Gates 6, 10 and 11 stay open). The existing `operations/read` response and its `activity: not_available` field are unchanged.

## Data source and provenance

`public.audit_events`, read only inside the function. Only rows whose `event_type` starts with `auth.`, `admin.` or `operations.` are considered; every other event type is neither counted nor reported (content-domain activity volume is not exposed). The function returns only `(category, outcome, events)`; it never returns an id, actor, scope, entity, metadata, before/after snapshot, timestamp of an individual event or any text from a row.

## Categories and outcomes (closed catalogue, in this order)

| Key | Event types |
|---|---|
| `sign_in` | `auth.login`, `auth.logout`, `auth.session_bootstrap` |
| `denied_access` | `auth.login_denied`, `auth.session_denied`, `auth.scope_denied`, `auth.csrf_denied`, `auth.host_denied`, `auth.origin_denied`, `auth.tls_required`, `auth.bootstrap_type_denied`, `auth.rate_limited`, `operations.session_denied` |
| `access_change` | `admin.user_created`, `admin.password_changed`, `admin.user_status_changed`, `admin.scope_changed` |
| `recovery_admin` | `admin.recovery_assessed`, `admin.restored_*`, `admin.work_restore_*` |
| `other_admin` | any other `admin.*` |
| `operations_read` | `operations.read`, `operations.audit_summary` |
| `other_security` | any other `auth.*` or `operations.*` |

Outcomes: `success`, `denied` (rows whose `result_status` is exactly `denied`), `other` (any other status). The catalogue is code-defined; a new event type lands in an `other_*` category until reviewed. Unknown event types are never reported by name.

## Authorization

`authority(...)` with scope `technical_admin`, the same path as `operations/read`: HTTPS, exact Host/Origin, current session, CSRF, current grant, installation membership lock, session revalidation after the query. Technical administration grants nothing over household, financial or Work records, and this summary contains none. Defence in depth, with the actor bound inside the database: the function takes the raw session token, hashes it (`sha256`, hex, the same digest `identity.resolve` stores in `auth_sessions.token_hash`) and itself looks up a session that is unrevoked, unexpired and not idle beyond the 30-minute limit, whose user is active and currently holds `technical_admin`. Otherwise it raises `42501`. It also rejects `p_hours` outside `{24, 168}` and a token outside 40 to 128 characters. Either failure is a server error with no payload.

**Why a token and not an actor id.** Every application user connects as the same `butler_runtime` role, so a caller-supplied actor UUID is a claim the database cannot check: any runtime-role session could pass another administrator's valid id. A live session token is the existing trusted identity credential (the route authenticates the request with the same token), and only that token's session can authorize the call. Supplying another administrator's UUID, a stored hash (`token_hash` is not the token), a decorated token or the token of a revoked, expired, idle, inactive-user or grant-revoked session is refused. There is no `uuid` overload.

**Residual limit (stated, not hidden).** `butler_runtime` may INSERT and UPDATE `auth_sessions`; a process already running as the runtime role with arbitrary SQL could insert a session row for a technical administrator and use its token. That is a pre-existing property of the shared runtime role (it already lets such a process forge sessions for every route), not something this function can close, and it yields counts only. The token is passed as a bound query parameter: with statement logging of parameters enabled a live token could appear in the PostgreSQL log, which is the same exposure as the session lookup that already precedes it.

## Request and response

Request (strict, extra keys forbidden): `{"scope":"technical_admin","window":"24h"|"7d"}`.

Response `200`: `schema_version` 1, `scope`, `actor_id`, `checked_at`, `valid_until` (+60 s), `window` (echo), `window_start`, `window_end`, `categories` (exactly the seven keys in catalogue order, each `{key, success, denied, other}` non-negative integers), `totals` (`success`, `denied`, `other`, equal to the column sums), `excludes` (the fixed exclusion statement id list: `content_domain_events`, `overdue_jobs`, `capacity`, `per_event_detail`). No other keys. `window_end` is the request's checked time; the summary excludes the audit event written by this same request.

## Bounds, retention, resources

At most 7 × 3 aggregate rows leave the database. Window is capped at 7 days; the function scans only `occurred_at` within the window using the existing index; the transaction sets `lock_timeout` 2 s and `statement_timeout` 5 s (a timeout is an unavailable response, never partial counts). Audit retention is unchanged (append-only, no deletion); the summary says nothing about events older than the window.

## Failure, partial and unavailable semantics

There is no partial result: any database, function, timeout, session-expiry or audit-write failure withholds the whole response. The client shows sanitized "unavailable" text, never zeros. Zero means "no counted events in this window", not that the system is healthy, secure or unobserved-attack-free; a window that predates retained history is indistinguishable from a quiet one and the UI says so. Counts are not a complete security log.

## Audit behaviour

Reading the summary appends one metadata-only event `operations.audit_summary` (`metadata: {window}`), committed with the request before release; if the append fails the entire response is withheld (the route's existing transaction behaviour). The function performs no write.

## Concurrency and transactions

One request transaction. The installation scope lock and session revalidation follow `operations/read`. The projection is `STABLE`, read-only, and takes no row locks on audit rows; concurrent audit inserts are either included or not (snapshot at statement start). No new lock order is introduced.

## Migration and recovery

One migration adds the function and `REVOKE ALL ... FROM PUBLIC`. Downgrade drops the function. The runtime grant (`GRANT EXECUTE`) is applied by `runtime_role.configure` alongside the other reviewed functions. The migration alters no table, trigger, existing function or existing grant; the append-only triggers on `audit_events` are untouched. Restored databases receive the function through the normal migration chain.

## UI

A "Audit summary (security and administrative events)" section inside the Operations overview, with a window selector (24 hours / 7 days) and an explicit **Load audit summary** button. It shows the seven categories with three counts each, the totals, the checked/valid-until times and the limitations text. It clears within 60 seconds, on hidden tab, scope/session/grant change or failure, never stores data in browser persistence, URLs or downloads, and discards late responses.

## Acceptance (positive and negative)

- A1. A technical administrator receives the exact allow-listed shape and correct counts for synthetic events across all categories and outcomes, inside and outside the window.
- A2. Content-domain events (for example `documents.*`, `tasks.*`) and unknown event types never appear in any count.
- A3. Non-technical-admin, revoked grant, expired session, missing CSRF, wrong Host/Origin, extra request keys and an invalid window are denied without payload.
- A4. The runtime role still cannot SELECT from `audit_events`, cannot call the function with another technical administrator's id (no such parameter exists; a UUID is refused), with a stored token hash, or with the token of a session that is revoked, expired, idle, inactive-user or without a current grant, and cannot call it with a window other than 24 or 168 hours.
- A5. An induced audit-insert failure withholds the response and leaves no `operations.audit_summary` row.
- A6. The response never contains ids, actors, scopes, timestamps of events, metadata or exception text; strict client parsing rejects any extra or out-of-order key, a negative or non-integer count, and totals that do not equal the column sums.
- A7. The function is `SECURITY DEFINER` with a fixed `search_path`, is not executable by PUBLIC, and the migration round-trips (upgrade, downgrade, upgrade) on PostgreSQL.
- A8. Zero results render as "no counted events", never as healthy; the UI clears on hidden tab, expiry, session change and failure.

## What this cannot establish

That the system is healthy or secure; that all events are audited; anything about content-domain activity; overdue work; capacity; backups; independent recovery; anything on a real private host. Synthetic observations are not real-host evidence. Owner acceptance and independent verification are separate and not claimed.
