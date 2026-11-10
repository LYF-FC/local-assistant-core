# Daily overview — spec062 foundation (merged PR #17)

Open **Daily overview** from Local records, choose one granted scope, a day and an IANA timezone, then **Refresh overview**. This joins existing baseline CORE-08/09, UI-01 and ORG-02 foundations into one bounded review entry. The current session landing stays unchanged; no background request is started by signing in. Only synthetic/local records are used for acceptance. No new live source, external message, model request, permission, worker or private deployment is activated.

## What is shown

- Day agenda and open due tasks from the existing briefing: source coverage/status/staleness, tentative occurrences, possible overlaps, due/overdue tasks and unknown assignment. Existing limits remain 25 calendar sources/100 events/25 tasks/10 memory references; the overview does not display private memory content. Undated/later tasks and truncated source lists are explicitly outside this view. No listed occurrence is not proof of an empty day, and ready/configured status is not a live-provider health check.
- The current user's private in-app reminders, even in a shared scope: first 25 records, showing scheduled/delivered states, deferral reasons and paused preferences. Delivered means in-app, not external notification; enabled preferences do not prove a worker is running. Closed reminders may occupy the first page, so a zero visible active count is not a complete inbox claim.
- Documents needing text/extraction attention on the first 25 authorized library records: unreviewed sources and explicit PDF extraction failures. More pages may contain review work. A reviewed text is not approved invoice fields, a filing instruction or external action authority. Shared records may be read-only; creator review remains required. No original/excerpt body is retained by the overview.

Each list is a separate server read, not an atomic global snapshot or a new authority store. The overview does not include the complete approval inbox, professional records, finance records, infrastructure/model/job health or all future review queues. Existing source panels and acceptance contracts remain authoritative; this is not complete UI-01/CORE-08/MVP acceptance.

## Freshness, privacy and failures

Exactly three existing protected first-page reads run in parallel only on explicit refresh: briefing, private reminder query and document query. No automatic pagination, retry, polling, search across scopes or downloaded overview copy. Each existing parser checks the source receipt; the projection additionally binds document actor and private source ownership to the current session. Technical administration never creates a content grant. Unsupported/ungranted scopes are refused before requests.

Authentication/permission denial clears the whole overview;401 also returns to sign-in. Ordinary service or malformed-response failures show that section as unavailable rather than empty, while independently available sections remain visible. Raw server errors are not echoed. Results wait for the batch to settle and are guarded against abort-ignoring or delayed transports. Changing scope/day/timezone clears results before another read; no automatic follow-up occurs.

Cards expire no later than 60seconds after the read starts or the briefing's earlier server expiry. They clear on expiry, hidden tab, session/view changes and authority denial, requiring explicit refresh. A slow/failed response cannot extend freshness from its completion time. No storage, URL, cookie, telemetry or log contains overview payloads. No data leaves the local origin. The default day uses local calendar components and an explicit browser timezone (UTC fallback), not UTC date slicing or inferred installation preferences.

## Source navigation and current authority

Open a pending document to reread its current version in Documents. The overview passes only source metadata, and a changed title/revision is loaded from the server before content or actions appear. Open the scoped task list or reminder inbox to inspect current records; reminder navigation includes all states so scheduled entries are not silently hidden by the destination's usual delivered-only default. Calendar navigation retains the selected scope/day/timezone, then requires the existing explicit read. Ordinary navigation clears source context. All destination grants and mutation checks remain unchanged; this overview cannot acknowledge, complete, approve, file, send, export or alter a record.

## Evidence and retained scope

[Spec062](../specs/062-daily-overview/spec.md) defines bounds/negative cases; [convergence](../specs/062-daily-overview/convergence.md) records verification. New tests cover protected bounded reads, private actor/owner/scope mismatch, authority denial, ordinary failure, abort/expiry limits, local date handling and document attention states. Synthetic trusted HTTPS covers real records, other-owner privacy, shared read-only records, current-source navigation, scoped destination context, pagination limits, service failures, delayed selection/view responses, hidden/expired state, no polling and revoked-session sign-in.

No backend/schema/grant change or new migration/restore claim. Existing source read audit and deterministic stores are reused. Interface changes require frontend/container coverage plus scope/final gate under the unchanged CI policy. All 155 references and the original 99 cohort are preserved; the approved review/refactoring programme and REV additions remain deferred after existing scope. Open branch work is not counted as a merged feature or a full retained-contract completion.
