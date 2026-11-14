# Operations overview — merged PR21

An explicitly granted technical administrator can open **Operations overview** and choose **Reload operations observations**. This reports bounded local engineering observations. There is no background polling, privileged shell, outbound probe, model call or action control. Technical administration does not expose another member's financial, household or Work records.

## What the view can establish

A successful authenticated API request and its database transaction were reachable at the reported check time. Archive/parser configuration and the local-answer flag are disclosed only as configured-but-unverified, disabled or unknown. Configured paths, addresses, model tags, credentials and raw exceptions never enter the response. No configured flag means that a dependency is healthy.

The software inventory shows the declared API build, running Python version and installed FastAPI/SQLAlchemy/psycopg/Pydantic package metadata. Missing or unsupported metadata is unknown. Installed versions are distinct from latest available, supported stable and approved versions; no approval, license, advisory, compatibility or exception assessment is inferred. Full RND-01 catalogue, model/container/database/host inventory and dated official-source scouting remain required.

Worker heartbeat, overdue work, storage/NAS headroom, backup age, independent restore, certificate validity, remote hardware and independent failure alerting remain **unknown**. Database/API reachability cannot report an outage of the application itself. Independent observation and actual-host procedures are separate retained MVP gates.

## Bounded private job sample

Only jobs requested by the current administrator in `technical_admin`, created in the last 24 hours, are sampled. The latest 25 statuses contribute fixed queued/running/succeeded/dead-letter/other counts. A 26th row signals additional jobs; the count is neither a global total nor an overdue-work measure. No ID, payload, result text, approval content, lease or other user's job is selected. Zero means no sampled matching rows, not that all workers are idle or healthy.

Audit review: the runtime role intentionally has INSERT-only audit access and still does. The overview itself reads no audit data. A separate, explicit **Audit summary** is described below. Reading this view still appends metadata-only access audit, committed before release; an audit failure withholds the entire response.

## Audit summary (spec 072, first OPS-10 slice; local branch, unmerged)

A technical administrator can choose a window (last 24 hours or 7 days) and **Load audit summary**. Nothing loads with the overview and nothing polls. The result is a count table of security and administrative audit events by a fixed category (sign-in/out, denied or rate-limited access, access changes, recovery administration, other administrative, operations views, other security) and outcome (succeeded, denied, other).

- **Read path:** the only audit read is the reviewed `SECURITY DEFINER` function `public.butler_audit_summary` (migration 0037; `EXECUTE` granted to the runtime role by role configuration, revoked from PUBLIC, fixed `search_path`). It returns only `(category, outcome, count)`; the runtime role still has no table SELECT on `audit_events`, and the append-only triggers are untouched. The function itself refuses an actor without a current `technical_admin` grant and any window other than 24 or 168 hours.
- **What it counts:** only `auth.`, `admin.` and `operations.` events. Household, financial, Work, document, task, memory and approval activity is neither counted nor reported. It never returns an id, actor, scope, entity, metadata, individual timestamp or text.
- **Request:** protected POST `/api/v1/operations/audit-summary`, strict `{scope:"technical_admin", window:"24h"|"7d"}`, the same HTTPS/Origin/session/CSRF/grant/installation-lock path as the overview. Lock and statement timeouts (2 s, 5 s) make a slow query an unavailable response, never partial counts.
- **Audit of the read:** one metadata-only `operations.audit_summary` event (window only), committed before release; if it cannot be written the entire response is withheld. The summary excludes the event written by its own request.
- **Client:** strict parsing (exact keys, fixed category order, integer counts, totals equal to column sums, window echo, 60-second validity); clears on hidden tab, expiry, session or grant change and failure; no browser persistence, URL or download.
- **What it cannot show:** that the system is healthy or secure; a complete security log (an unreviewed event type is grouped under an "other" category); anything about content activity; overdue work; capacity trends; periodic or scheduled reports; delivery or alerting. A zero is "no counted events in this window", also when the window predates retained history. Synthetic evidence only; no real host, provider or private data. These items stay open under OPS-10, and Gates 6, 10 and 11 are not changed.

This supersedes the initial spec066 draft's direct audit-query idea, not the original requirement.

## Privacy and failure

Protected POST `/api/v1/operations/read` requires strict `{scope:"technical_admin"}`, HTTPS, exact Host/Origin, current session, CSRF and current grant. Existing installation membership locking prevents grant changes during the transaction; session authority is revalidated after querying. No schema, migration, DB grant, dependency, fixture, production setting or private-deployment change is introduced.

The client strictly validates schema, actor/scope, fixed catalogue IDs, source/state coherence, window/deadline, count bounds and totals. All observations clear after at most 60 seconds from request start, on hidden tab, view/session/membership changes or failure. Late results cannot repopulate a cleared view. Ordinary service failures and malformed responses show sanitized unavailable status; a 401 returns to sign-in. Reload is explicit. Nothing is stored in browser persistence, URLs, downloads or telemetry.

## Evidence and remaining MVP work

[Spec066](../specs/066-operations-overview/spec.md) and its convergence distinguish branch checks from merge/release evidence. [PR20](https://github.com/LYF-FC/local-assistant-core/pull/20) already merged financial capture UI; the [dashboard](FEATURE_DASHBOARD.html) records that evidence without promoting full FIN-06 acceptance. PR21 is merged engineering, not full monitoring or MVP acceptance.

This batch advances existing OPS-09/RND-01 foundations. Complete monitoring, scheduled audit/scouting, unified approvals/search, real-model multilingual quality, live calendar/channel/intake/filing adapters, outage/restart acceptance, independent clean-host/key/archive recovery and separately authorized private adoption remain. All original155 scope references, original99 comparison and later/deferred ordering are preserved. The MVP is not declared finished by a green component suite.

PR21 merged at `4001230471d19f83fe9c9a8ef3d6d38622381dfc`; exact head `2c5cdb27d6dd9a24ba54b17d925dc5f70fa4d507` run42880083517 passed all six jobs. Initial main push run42882633058 was in progress when checked; no full-main/host certificate is inferred.
