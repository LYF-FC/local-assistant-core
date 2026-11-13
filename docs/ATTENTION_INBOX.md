# Unified attention inbox — spec 071 (first slice)

Status: implemented on the branch `codex/impl-071-attention-inbox` and **not yet merged**. Merged delivery is recorded only after the PR is merged with a verified number and merge commit. Implementation, local testing, verification and owner acceptance are separate facts; see [convergence](../specs/071-unified-attention-inbox/convergence.md).

Choose **Attention inbox** in the records workspace, pick one granted scope and select **Refresh inbox**. Nothing is read until you do. The inbox is read-and-link only: it cannot approve, reject, cancel, consume, retry, acknowledge, file, send, complete or change any record.

## Sections (first page of each, one granted scope)

| Section | Source (existing protected read) | Selection |
|---|---|---|
| Pending approvals | `POST /api/v1/approvals/query` (new, read-only) | pending, unexpired, payload-hash and policy bound |
| Overdue open tasks | task query | open and overdue |
| Delivered reminders | reminder query | delivered |
| Documents needing review | document query | text not reviewed or extraction not ready |
| Filing failures | filing query | failed and unknown (two reads) |
| Notification failures | notification query | failed and unknown (two reads) |

Each source is read separately. The sections are not one consistent snapshot, and each shows its own read time. First pages are read, and the view never shows a total count. When more records exist the message is specific to the section: pending approvals can be paged inside the inbox with **Load more approvals** (explicit, one page per click, same cursor contract, one audit event per page, never extending the 60-second view lifetime); filing and notification sections say that no screen in this release lists those records, so the rest cannot be viewed; documents, reminders and tasks name the existing view that lists them. "More records exist" is never presented as "more records can be opened".

## Pending approvals are evidence only

The list returns only: id, scope, action type, status, requested and expiry time, and a `requested_by_you` flag. It never returns the sealed payload, payload hash, policy version, requester or approver identity. `requested_by_you` is a label; it implies no self-approval restriction. There is no approvals detail screen and no Open control. The inbox sends no request to approval GET, decide, cancel or consume.

Each list request (every page) writes one metadata-only audit event `approval.query` carrying the returned count. The audit schema has no event-name restriction; a test pins the name. If the audit write fails, the page is withheld (503, no payload) and the client shows the approvals source as unavailable, not empty. The list writes no approval row and applies no lazy expiry.

## Refresh, failure and empty states

- A failed or malformed source is shown as unavailable with a per-source retry; it is never shown as empty. The "nothing needs attention" sentence appears only when every source loaded and none had items.
- Failure rows use uncertainty wording: an unknown filing or notification outcome is not reported as failed or as delivered.
- The view clears after 60 seconds, earlier at the soonest approval expiry, on hidden tab, scope change, grant change, session change or any 401/403/404/410. Late responses are discarded. No polling.
- Duplicate references render once; separate record kinds are not merged.

## Navigation and privacy

Task, reminder and document cards open the existing destination with minimal coordinates; the destination rereads under current authorization and keeps its own confirmation boundaries. A **filing failure** opens its related document (**Open related document**): the target is only the document id, owner, scope and a minimum revision from the filing record, and the Documents destination rereads the document and accepts it only if id, owner and scope match and its current revision is at least that minimum (a newer revision is fine). A **notification failure** opens its related reminder (**Open related reminder**): the notification response carries the related `task_id`, released only after the server verifies that the reminder's owner and scope match; the Reminders destination rereads the task and shows it in the existing selected-reminder view. Nothing is fetched per card; the read happens only after you open a card, and a missing, revoked or mismatched record shows the destination's normal unavailable state. A scrubbed filing request or a notification without a verified task shows a note and no Open control. Routine origin is not shown: the existing task response does not provide it, and no field was added.

Shared records stay read-only for non-owners; private records must belong to the actor. Parsers are strict allow-lists: an unexpected key, scope, owner or state makes that whole source unavailable. Content and identifiers stay in memory only: no browser storage, URL, telemetry or service-worker cache.

## Boundaries

In-app records only. No live provider, external delivery or infrastructure health is checked. The only API change is the read-only `task_id` field on the notification query response. No new grant, migration, worker or approvals screen was added, and no search was broadened (the existing scoped search remains the search entry). Gate 2's criterion is unchanged; Gate 2 stays open, CORE-08 and UI-01 stay partial, and no status counts changed. Private-host and mobile-device acceptance, real providers and owner acceptance remain separate and unperformed.
