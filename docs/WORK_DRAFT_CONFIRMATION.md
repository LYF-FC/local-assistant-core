# Optional synthetic note confirmation

prior implementation review delivers preview/review only. Spec 021 adds an explicit confirmation request and manual local application. All data stays local; only synthetic notes are accepted. Standard HTTPS POC remains disabled and needs no new configuration.

| Step | Result | Authority |
|---|---|---|
| Preview exact note | Current revision and hash | Current session, CSRF, work grant and scoped adapter |
| Review with approve | Five-minute prepared receipt | Exact revision/hash; identity audit must commit |
| Request confirm_note | 202 pending, opaque request UUID | Same actor/session/workspace/record/revision/receipt |
| Local executor | Applied once or denied | Committed intent evidence and fresh locked authorization/content |
| Status | Historical metadata | Current original session and explicit workspace grant |

No queue response is proof of application. No confirmation approves execution or proves physical attention. A later correction/forget does not erase the historical applied result, and status never returns note content.

## Explicit local synthetic procedure

First follow WORK_SYNTHETIC_ADAPTER.md and WORK_DRAFT_REVIEW.md for the existing synthetic workspace, grants, protected file and review. Never recreate existing users, CA, configuration or volumes. Use a current signed-in HTTPS session and CSRF token; there is no new capture UI.

For this optional experiment, layer infra/core/work-draft-confirmation.override.yml after the base, work-synthetic and work-draft-review overlays when starting API. It sets only BUTLER_WORK_DRAFT_CONFIRMATION_ENABLED=true; adapter/review remain separate prerequisites. Keep real employer sources absent.

POST `/api/v1/work/workspaces/{workspace}/drafts/{record}/confirm` with only:

```json
{
  "review_preparation_id": "UUID-from-the-current-review",
  "expected_revision": 1,
  "request_id": "new-client-UUID",
  "decision": "confirm_note"
}
```

Use real UUIDs from your current synthetic session. The returned confirmation_request_id is metadata, not a capability. Within the receipt lifetime, deliberately execute that request from the trusted local migration container, with the existing environment and Compose setup:

```sh
docker compose -f infra/core/compose.yml run --rm -T migrate \
  python -m app.work_confirmation_worker --environment development \
  --request REQUEST_UUID
```

This uses the migration connection only in a short-lived local process. Do not copy its credentials into the API. No worker daemon or retry loop is installed. On failure, everything rolls back; inspect metadata and deliberately reconcile before retrying.

POST `/api/v1/work/workspaces/{workspace}/confirmations/{confirmation_request_id}/status` with `{}`, the same current session and CSRF. Pending returns 202; terminal applied/denied returns 200. An identical confirm retry returns the original request; mismatched revision/record/receipt fails. A different session cannot use old handles. Stale/revoked/expired requests are denied by executor; prepare a new current review when appropriate.

## Transaction and recovery limits

API uses identity credentials plus existing restricted work read lease. The private receipt check records a prepared-read audit before its separate work commit; this does not claim queue delivery if identity commit later fails. It cannot mutate note state, queue outcome or consumption. Public queue has UUID/revision/actor/session/time/outcome metadata, no content/hash/source list. The executor requires clean actual work storage owner, explicit dev/test transaction and same PostgreSQL database. It locks registry, user, session, request, draft, receipt, sources; validates committed review/enqueue audit and fresh state. Confirmation revision/history/private audit/consumption/public outcome/identity outcome audit share one transaction. Unique receipt consumption prevents a second application.

Current-user review preparation and queue creation remain separate commits. Orphan work preparations cannot authorize application because the executor checks committed identity evidence. Metadata status is historical and scoped; a restored pending request is never automatically run. Trust in the host/storage owner and existing independent backup/key/secret suppression acceptance remains unchanged.

Forget scrubs all note histories and review hashes atomically; minimal consumption and public identity/outcome metadata remain. Back up/restore public identity and private work together. CI covers copied database-role denial, immutable consumption, applied/remaining-pending metadata and forgotten hash/history redaction. This is logical synthetic recovery evidence, not independent M2/full-host recovery acceptance.

To disable, remove confirmation overlay and recreate API; stop any deliberate executor invocation. Existing metadata remains for reconciliation. Before downgrade, disable requests, stop executor, take and verify a backup. Migration downgrade removes queue/consumption metadata; never use it as a retry/erasure shortcut. Reprovision runtime after migration changes as normal; work provisioning does not enable confirmation or add lifecycle grants.

Next: authenticated synthetic capture, parties and selected work context; then remaining isolation/keys/derived-copy/recovery gates before a real debrief pilot. No model/provider, external transfer or real execution is introduced here.
