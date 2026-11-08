# Optional synthetic note correction and forgetting

Spec 025 delivers correction and forgetting as one lifecycle increment. A current authenticated workspace user prepares an explicit revision-bound request; a deliberately invoked local executor applies it once. Correction returns a draft and never confirms or executes it. Forgetting removes the live note/history payload, review hashes and bound pending correction copies. This remains synthetic development/test only, without a UI, real employer sources, model, connector or daemon.

Standard M2 update needs no special activation. Keep existing users, CA, secrets and volumes. The optional experiment reuses the protected synthetic adapter and capture intent infrastructure. From the trusted migration container with its existing configuration, explicitly provision:

```sh
docker compose -f infra/core/compose.yml run --rm -T migrate \
  python -m app.work_notes_storage --environment development --workspace SYNTHETIC_SLUG
```

This reestablishes capture/review preparation grants, adds narrow action/target/revision intent INSERT and a metadata-only scoped view. It grants no note write, intent outcome mutation or table-owner credentials to API. Generic work/review/capture provisioning resets these additional grants; deliberately reprovision only if still wanted. No user grant/session is created.

Layer `infra/core/work-note-changes.override.yml` after the base and synthetic adapter overlays for API. Capture, review, confirmation and context flags remain independent; enable their existing overlays only when separately testing those functions.

## Explicit current-human requests

With the current HTTPS session, exact Origin and CSRF, POST `/api/v1/work/workspaces/{workspace}/drafts/{record}/correct`:

```json
{
  "request_id": "NEW_CLIENT_UUID",
  "decision": "correct_note",
  "expected_revision": 1,
  "draft": {
    "kind": "decision",
    "marker": "synthetic:corrected-note",
    "source_ids": ["ACTIVE_SOURCE_UUID"],
    "owner_id": null,
    "due_at": null,
    "retain_until": "AWARE_FUTURE_ISO_TIMESTAMP"
  }
}
```

Use actual current synthetic record/source values and the current revision. Kind and policy are preserved; retention cannot be extended. Select 1–10 distinct active sources and an explicit active same-workspace party or null. Owner/date remain unknown when null. A correction to a confirmed note creates a new draft revision; it requires a fresh separate review/confirmation before becoming confirmed again. No actor/session/policy/state override is accepted.

POST `/api/v1/work/workspaces/{workspace}/drafts/{record}/forget` with only:

```json
{
  "request_id": "NEW_CLIENT_UUID",
  "decision": "forget_note",
  "expected_revision": 1
}
```

Forget never accepts replacement content. It uses a metadata-only, workspace-filtered view of id/revision/state/retention, so expired or source-ineligible notes can be forgotten without revealing their content. Ordinary content RLS remains unchanged. A current workspace grant is still required. Missing, stale and already forgotten targets fail; no silent revision override.

202 pending returns an opaque `change_request_id`, operation, expiry and flags, not content/source/owner/hash. Server lifetime is at most five minutes and bounded by current session expiry; correction is also bounded by proposed note retention. Exact current-session pending nonce/action/target/revision/content replay returns the same handle. Conflicts, expiry or terminal nonce reuse return 409. Use status for historical results.

## Deliberate local application

Within the request lifetime, run the returned UUID from the trusted migration container:

```sh
docker compose -f infra/core/compose.yml run --rm -T migrate \
  python -m app.work_notes_worker --environment development --request CHANGE_UUID
```

The owner-only one-shot executor requires committed identity intent and fresh user/session/grant/workspace/revision. Correction also revalidates original/proposed sources, proposed owner, policy and retention. Forget intentionally works after content expiry/source withdrawal. Duplicate execution returns historical metadata without another revision. No automatic retry, recurring worker or execution approval.

POST `/api/v1/work/workspaces/{workspace}/note-changes/{change_request_id}/status` with `{}`, original current session and CSRF. Applied returns the resulting revision and record UUID; denied/pending carries no content. Status remains historical after later edits/forgetting and never grants current content access. Capture handles are rejected by change handlers and change handles are rejected by capture handlers.

## Privacy, atomicity and recovery

Private preparation commits before metadata-only identity audit. Orphan preparations do not authorize application; a matching committed current-human identity event is required. The exclusive registry barrier is acquired before all worker row locks, deliberately serializing this synthetic pilot with existing work reads/writes and avoiding lock inversion during pending-copy cleanup. A long operator transaction can temporarily make work requests time out; keep one-shot operations short.

Note/revisions/private audit, applied/denied outcome, terminal intent payload/hash redaction and public outcome audit share one database transaction. Forget additionally denies/redacts all pending correct_note intents targeting that note, including other sessions and orphan preparations, with private denial audit. Failure in history, redaction, private/public audit or deferred commit rolls everything back. Inspect metadata and deliberately reconcile pending requests before retrying.

Terminal capture/change intents already contain no independent content. Pending corrections are extra private copies; forgetting their target scrubs them atomically. Unrelated pending new captures remain independent explicit records. Expiry ends eligibility, not physical deletion: deliberately reconcile expired requests to deny/redact them. Old backups, physical database pages, future derived stores and independent key/full-host recovery remain separate acceptance gates.

Back up identity and private work together. Logical restore checks action/result revisions, pending/applied/denied state, terminal redaction and copied-role denial of the metadata view; restored pending never auto-runs. Migration 0015 downgrade refuses while any note-change intent exists, preserving revision/outcome evidence. Disable flags/workers and use verified backup plus separately reviewed recovery/reconciliation before any destructive rollback. Existing note/party downgrade rules remain.

The optional complete synthetic capture/review screen is the spec 026 candidate; see WORK_NOTES_INTERFACE.md. Next after that: debrief handling and the remaining isolation/recovery acceptance. Real employer data and production remain gated.
