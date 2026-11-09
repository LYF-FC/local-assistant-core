# Calendar snapshots and daily briefing — spec 054

This development foundation imports complete normalized synthetic calendar windows and builds a deterministic scoped day view. It does not connect Apple/iCloud, parse ICS/CalDAV, expand recurrence rules, poll accounts, write events, mirror calendars or send reminders. Those retained requirements need their own adapter/activation evidence. See [specification](../specs/054-calendar-briefing/spec.md).

## Use

Open **Calendar and briefing**, choose an assigned shared or creator-private scope and add a labelled source. Paste a complete normalized JSON window, preview it, then explicitly import. The server validates the entire window and commits source/history/audit together. A source label is not an account or permission grant. Shared members can read current data; the creator alone can import, mark unavailable, inspect/download history or forget. Technical administrators gain no private content access.

A minimal synthetic example (replace `fetched_at` with the actual synthetic capture instant before testing):

```json
{
  "complete": true,
  "cursor": "synthetic-window-1",
  "fetched_at": "2026-11-08T12:00:00Z",
  "timezone": "Europe/Paris",
  "start_date": "2026-10-25",
  "end_date": "2026-10-26",
  "events": [{
    "kind": "timed",
    "uid": "synthetic-appointment",
    "recurrence_id": "",
    "sequence": 0,
    "title": "Synthetic appointment",
    "description": "Synthetic source text",
    "status": "confirmed",
    "timezone": "Europe/Paris",
    "start": "2026-10-25T09:00:00+01:00",
    "end": "2026-10-25T10:00:00+01:00"
  }]
}
```

All-day occurrences use `kind: "all_day"`, `start_date`/`end_date` instead of `start`/`end`; end dates are exclusive. Dates remain dates. Timed values must be aware instants: UTC or offsets consistent with their source IANA zone. Stored timed values normalize to UTC while preserving the source zone. A recurring occurrence carries its original stable `recurrence_id` even after moving. The future adapter must supply correctly expanded instances, complete provider pagination and a monotonic event `sequence`; this interface does not establish that a real provider has those semantics.

A full window covers 1–31 local dates and at most 100 occurrences/64 KiB of serialized JSON. Each occurrence must overlap coverage. Provider UID + recurrence ID identifies an occurrence within one local source; deterministic occurrence UUIDs also bind the local source UUID. Duplicate titles across calendars are not silently merged. States are confirmed, tentative or cancelled; cancelled instances remain in the snapshot/history but do not enter the agenda.

## Reconciliation and failure

Import includes the source's current expected revision. A changed accepted snapshot advances one source revision. Exact replay is a successful no-op even after a lost acknowledgement; it never clears an offline/failed status. Reused historical cursors with different data, older/equal capture times on changed snapshots, fetch times over 60 seconds in the future, stale expected revisions, backwards sequences and changed event content at equal sequence refuse without partial mutation. Event sequence checks consult preserved history, including omitted instances. Changed source windows can contain moved exceptions, explicit cancellations and omissions.

Only omissions inside overlapping old/new coverage count as removals. Omitted occurrences outside that overlap are explicitly unknown. The current snapshot covers only its stated window; historical events outside it are not projected as current. This is full-window replacement, not an incremental sync engine. Interrupted/partial imports cannot advance the saved cursor. Retry requires an explicit action; a browser never automatically repeats mutations.

**Mark offline** / **Mark fetch failed** retain the last good window. A newly captured complete window is required to recover availability. A capture older than 24 hours is visibly stale; missing full-day coverage is unknown, even when no events match. A synthetic upload is evidence of a local import, never a claim of recent live-account polling.

Limits are 10 source identities per creator including forgotten tombstones, 100 revisions per source before changes pause, 25 cards per keyset page and five history revisions per page. Forget remains available at the history cap and may create revision 101. These explicit bounds need a later reviewed retention/compaction design before long-running provider polling. They are not a production capacity claim.

## Daily briefing

Choose a date and IANA display zone. Local midnight boundaries handle 23/25-hour days; nonexistent whole dates refuse. The read-only briefing combines one scope's first 25 visible sources, up to 100 known non-cancelled occurrences overlapping that day, 25 open tasks due before the day ends (including overdue), and 10 confirmed/unexpired memory titles/source references. Sections disclose truncation. Undated tasks and other scopes are excluded, not inferred absent. Memory references are unranked context; no household need or recommendation is inferred. Possible timed overlaps are flagged without choosing a winner; all-day entries do not generate time-conflict flags. This does not resolve availability, travel or scheduling conflicts.

Every item retains source IDs/revisions; current grants, user/session, source/task/memory rows and metadata audit are checked transactionally before release, including expiry after row waits. Calendar status and freshness remain attached to last-known events. No model is called. Browser results expire within 60 seconds (briefing also respects session expiry), clear on scope/view/session navigation and remain outside browser storage/cache/history. Source text renders inertly.

## History, privacy and recovery

Owner history/export preserves source revisions, normalized windows, UIDs/recurrence identity, cursor, timestamps and uncertainty/status. Explicit download acknowledgement creates an unmanaged local JSON copy; five revisions per page, current authority rechecked. Forget scrubs the current payload and every historical payload, retains only minimal local identity/ownership/scope/revision/timestamps and blocks resurrection through that source. Disconnecting is not forgetting; older downloads/backups and provider originals cannot be recalled. No older-backup suppression claim is introduced.

Audit retains local source IDs/revisions, operation/result and referenced task/memory revision manifests, not labels, event text, UIDs/cursors or briefing content. API errors are sanitized. No data leaves the installation automatically; local download is explicit. No network client, credentials, model, external storage or new backup key is added.

Migration `0026_calendar_snapshots` adds `calendar_sources` and `calendar_revisions`; apply through the existing migration role, then idempotent restricted-role setup. Identity/revision/history SQL guards and least-privilege grants remain active. Downgrade destroys the new tables: protect/verify a backup and review rollback before any adoption; do not downgrade populated installations casually. The existing logical dump/restore drill now verifies active offline snapshots, recurrence/timezone provenance and terminal forgotten history. Independent clean-host, private deployment/adoption and whole-MVP recovery remain separate gates.

API paths under `/api/v1/calendars`: create; `/query`; `/briefing`; `/{id}/read`, `/import`, `/unavailable`, `/forget`, `/history`, `/export`. Protected POST requests require current session, CSRF, exact HTTPS host/origin and chosen scope. Export additionally requires explicit copy-limit acknowledgement. No public/provisioning endpoint is added.
