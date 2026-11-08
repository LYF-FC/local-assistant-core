# Optional authenticated synthetic draft capture

Spec 024 adds explicit synthetic capture preparation and a manual local save. Preparing a request does not save or confirm a note. A saved draft uses the existing separate preview/review/confirmation flow. No capture UI, real work text, extraction, connector, model, scheduled executor or execution authority is added. All data stays local.

Standard M2 update needs no special activation. For this optional synthetic dev/test experiment, keep existing users, CA, secrets and volumes. First follow WORK_SYNTHETIC_ADAPTER.md for the protected credential file and active synthetic workspace, plus WORK_SYNTHETIC_PARTIES.md for optional owner IDs. Use an existing explicit retention policy and active synthetic source IDs; there is no automatic source/party creation.

## Deliberate provisioning and preparation

From the existing trusted migration container with its current environment/Compose configuration, explicitly provision preparation privileges:

```sh
docker compose -f infra/core/compose.yml run --rm -T migrate \
  python -m app.work_capture_storage --environment development --workspace SYNTHETIC_SLUG
```

This reestablishes review privileges and adds policy/party SELECT plus narrow private intent/audit preparation privileges to that workspace role. It grants no note INSERT/UPDATE, party mutation, public data access or owner credentials. Generic work/review provisioning resets these extra grants; deliberately reprovision capture if still desired. No user/session/work grant is created by this command.

Layer `infra/core/work-synthetic-capture.override.yml` after the base and synthetic adapter overlays when explicitly starting API for this test. Review/confirmation/context flags are independent; enable their existing overlays only when testing those later steps. Standard configuration stays disabled.

Using the current signed-in HTTPS session, exact Origin and CSRF token, POST `/api/v1/work/workspaces/{workspace}/captures`:

```json
{
  "request_id": "NEW_CLIENT_UUID",
  "decision": "capture_draft",
  "policy_id": "EXISTING_POLICY_UUID",
  "draft": {
    "kind": "action",
    "marker": "synthetic:example-note",
    "source_ids": ["EXISTING_SOURCE_UUID"],
    "owner_id": null,
    "due_at": null,
    "retain_until": "AWARE_FUTURE_ISO_TIMESTAMP"
  }
}
```

Replace placeholders with actual current synthetic values. Marker is limited to 11–256 synthetic ASCII characters. Choose 1–10 distinct active source UUIDs. Retention is future and within the explicit workspace policy. Owner is an explicit active/unexpired party in this workspace or null; actor always comes from the current session. Unknown owner/date stays unknown. Extra actor/session/state/workspace/revision fields are rejected. No real colleague or employer content is authorized.

A successful response is 202 pending with an opaque `capture_preparation_id`, expiry and flags, never note content/hash/source/owner/policy. Lifetime is at most five minutes, bounded by session expiry and requested note retention. Exact current-session pending nonce/payload replay returns the same handle; changed bindings, expired or terminal nonce reuse returns 409. Use status for terminal history instead of reusing the nonce. Permission/configuration/secret failures return no private payload.

## Manual application and status

Within the request lifetime, explicitly execute its UUID from the trusted local migration container:

```sh
docker compose -f infra/core/compose.yml run --rm -T migrate \
  python -m app.work_capture_worker --environment development --request CAPTURE_UUID
```

The one-shot process rechecks committed authenticated intent evidence, current user/session/grant/workspace, source eligibility, policy, selected party and expiry under locks. It saves a draft exactly once, without confirming it. Duplicate local execution returns the historical result. No daemon or retry loop is installed. An infrastructure/audit/commit error rolls everything back; deliberately reconcile before retrying.

POST `/api/v1/work/workspaces/{workspace}/captures/{capture_preparation_id}/status` with `{}`, the original current session and CSRF. Pending is 202; applied/denied is 200. Applied returns the saved record UUID and initial revision 1. Status is historical metadata, even if that note is later corrected, confirmed or forgotten; it does not authorize current content. Preview the draft with the separately opted-in existing review route. Confirmation still requires a new exact review/confirmation request.

## Retention, transaction and recovery limits

The API uses only its restricted identity connection and the existing scoped protected-file adapter. Pending content lives solely in the private capture table with a trigger-maintained hash and prepared audit. Identity audit contains only intent/session UUIDs. Private preparation commits before identity evidence; an orphan preparation cannot authorize saving. A deliberate successful retry can commit current identity intent for the same still-pending exact payload.

Saving uses one clean actual owner connection and one same-database READ COMMITTED transaction. Draft/current/history/private audits, capture outcome, public operator outcome audit and intent payload/hash redaction commit together. Stale/revoked/expired/orphan captures are denied and redacted. Neither preparation nor save grants confirmation, real ingestion, model dispatch or execution authority.

Pending payload is an additional private copy. Expiry ends eligibility, not physical retention. There is no automatic purge: deliberately run the expired intent to obtain denied/redacted status. Do not leave pending experiments unreconciled. Applied/denied intents retain only minimal UUID/outcome/time metadata, with no payload/hash. Forgetting a saved note scrubs its existing current/history payload; terminal capture metadata contains no independent content copy. Private audit records phases only and cannot claim applied while the intent is pending.

Back up public identity and private work together. Logical restore checks pending/applied/denied state, terminal redaction, immutable audit and copied-role denial; restored pending never runs automatically. Independent older-backup/key/derived/full-host recovery and actual M2/real-content acceptance remain open. Before downgrade, disable the capture overlay, stop executors and take a verified backup. Migration 0014 drops capture intent/audit metadata, never saved notes. Do not use downgrade to erase evidence or make a failed request retryable. Normal note/party forgetting and migration 0013 owner-reference guards remain in force.

Next: current-human correction/forget and capture interface, then remaining isolation/recovery gates before a real debrief pilot.

Spec 030 adds an explicit bounded expired-data cleanup path while a synthetic workspace is disabled; see [WORK_RETENTION](WORK_RETENTION.md). There is still no automatic deletion schedule or independent older-backup suppression.
