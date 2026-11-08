# Discard restored pending Work input

Spec 035 adds a separate reviewed cleanup step for synthetic development/test recovery. An old dump may preserve unsaved captures, pending corrections/forget requests, confirmation requests and cached review hashes, including input unrelated to a supplied forgetting manifest. This command discards that pending input; it never executes it or removes retained notes, parties or sources. No information leaves the private environment.

Keep applications and workers stopped. Restore into an isolated database, apply migration 0018 using the short-lived maintenance owner, then follow [restore quarantine](WORK_RESTORE_QUARANTINE.md). The selected workspace must be synthetic, disabled and have no grants. Reconcile any applicable [known-checkpoint forgetting manifest](WORK_MANIFEST_AUTHENTICATION.md), then discard remaining pending input. Other workspaces require separate handling. Test targets must be disposable `butler_test*` databases.

## Preview and apply

Use the configured restored database and an active technical-admin UUID as the audit reference. It is not HTTP human-attention proof. Do not put owner credentials in the API.

```sh
docker compose --env-file RESTORED_ENV -f infra/core/compose.yml run --rm -T migrate \
  python -m app.work_restore_requests --environment development \
  --restored-database RESTORED_DATABASE --workspace WORKSPACE_UUID --operator OPERATOR_UUID
```

Review the target name/OID, workspace/operator, fixed server issue time and every listed effect. Pending captures include both unbound new notes and bound corrections/forget requests, regardless of their actor's current grant/session. Every non-null cached review hash is included, including expired or previously consumed preparations. The plan contains IDs, intent, target/revision and expiry metadata; no payload, label, token or content hash value.

```sh
docker compose --env-file RESTORED_ENV -f infra/core/compose.yml run --rm -T migrate \
  python -m app.work_restore_requests --environment development \
  --restored-database RESTORED_DATABASE --workspace WORKSPACE_UUID --operator OPERATOR_UUID \
  --issued-at PREVIEW_ISSUED_AT --reviewed-hash PREVIEW_HASH \
  --decision discard_restored_requests
```

Copy the exact preview time and hash. Apply recomputes the complete plan within five minutes and rejects changed queues, reviews, target, operator, access or time. At most 100 combined rows and 32 KiB of plan metadata are allowed; requests and associated cached reviews each count separately. Exceeding a bound rejects the entire operation. Do not truncate or bypass caps; use a separately reviewed larger recovery procedure.

Pending capture/change payloads and their hashes are erased and requests become `denied` with reason `stale`. Pending confirmations receive the same terminal denial. Existing request-finished and private capture-audit mechanisms remain in use. Cached review hashes become null; immutable preparation metadata and completed request outcomes survive. Notes/current history, parties, sources, unrelated workspaces and original files remain unchanged.

All effects and `admin.work_restore_requests_discarded` metadata receipt commit together. The receipt binds the reviewed plan and lists outcome IDs, without payload/hash values. It always reports disabled Work, zero grants and `recovery_complete=false`. Errors roll back. After uncertain commit, inspect current metadata/receipt and obtain a new preview; do not replay a prior plan. A fresh empty preview cannot produce a completion receipt.

## Guard and recovery limits

Migration 0018 allows only the clean review-table owner in READ COMMITTED isolation, explicit reviewed cleanup mode and a disabled/no-grant synthetic workspace to clear an unexpired live-note review hash. An exclusive registry barrier precedes row locks; normal runtime/assumed roles, missing mode, unsafe isolation, active/granted targets and other review-field mutations fail closed. Existing forgotten/expiry redaction and insertion rules remain. No new grant, dependency, service, API or UI is added. Downgrade restores the previous guards and refuses existing cleanup receipts; use reviewed recovery instead of deleting audit evidence.

This is deliberate loss of pending unsaved input, not a complete recovery certificate or an automatic startup mechanism. Re-enabling Work requires separate review. Global approvals/outbox/external effects, credentials, keys, latest forgetting completeness, original/derived/downloaded copies, full-host/off-site and actual M2/real-content acceptance remain separate gates.

Verification includes negative role/mode/time/target/grant tests, mixed pending/expired inputs, unchanged completed outcomes/live controls, exact-plan replay, concurrent cleanup, caps, audit/expiry rollback, migration round-trip/refusal, actual maintenance CLI and a real dump containing pending input that is discarded only after isolated restore.
