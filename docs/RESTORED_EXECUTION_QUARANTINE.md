# Quarantine restored no-op execution authority

Spec 036 adds a manual, reviewed step for selected approvals and jobs restored into an isolated development/test database. An old backup can revive an unconsumed approval or a queued/leased job. This command cancels selected outstanding `validation.noop` approvals and dead-letters selected unfinished no-op jobs, clearing their outbox leases. It never executes or retries a job. No information leaves the private environment.

## Stop consumers and choose the selection

Keep API, workers and dispatch stopped. Restore into a separate database, apply normal migrations and perform the applicable session/Work recovery steps. Test targets must be disposable `butler_test*` databases. Use the clean READ COMMITTED owner of approvals, jobs, outbox, users and audit, with an explicit active technical-admin UUID as the audit reference. This reference is not HTTP human-attention proof or proof the named database is really a restore.

Use a trusted local inventory to choose **explicit approval and job UUIDs in one known scope**. Up to 25 combined IDs are supported. Repeat the relevant flag for each ID; the CLI sorts without silently deduplicating. Missing, duplicate, foreign-scope, unsupported-handler or inconsistent job/outbox selections fail together. The command does not enumerate or certify all outstanding work. Repeat deliberate reviewed selections as needed; unknown external/ambiguous writes require a separately reviewed provider reconciliation path.

```sh
docker compose --env-file RESTORED_ENV -f infra/core/compose.yml run --rm -T migrate \
  python -m app.restore_execution --environment development \
  --restored-database RESTORED_DATABASE --operator OPERATOR_UUID --scope household_shared \
  --approval APPROVAL_UUID --job JOB_UUID
```

Review target name/OID, scope/operator, every selected state, approval decision metadata, job/outbox IDs, attempts, availability and lease deadline/presence, and the fixed server issue time. The plan contains no payload, payload/idempotency/lease hash or lease token value. It is capped at 32 KiB. Selected terminal records can be inspected alongside outstanding ones but will be preserved.

```sh
docker compose --env-file RESTORED_ENV -f infra/core/compose.yml run --rm -T migrate \
  python -m app.restore_execution --environment development \
  --restored-database RESTORED_DATABASE --operator OPERATOR_UUID --scope household_shared \
  --approval APPROVAL_UUID --job JOB_UUID \
  --issued-at PREVIEW_ISSUED_AT --reviewed-hash PREVIEW_HASH \
  --decision quarantine_restored_execution
```

Use exactly the same selection and preview time/hash. Apply recomputes the plan within five minutes and checks age again before commit. Changed state, selection, decision metadata, lease metadata, target, scope or operator rejects. Replayed plans reject; a fresh all-terminal selection cannot create a completion receipt.

## Effects and transaction fencing

| Selected record | Quarantine effect |
|---|---|
| Pending approval | Cancel; record resolution time without inventing an approver |
| Approved approval | Cancel; preserve original approver and decision time |
| Queued/running job | Dead-letter with `restore_quarantined`, retain attempts and clear outbox lease |
| Consumed approval or completed job | Preserve sealed context and completed outcome |

Approval payloads remain sealed and retained. This is authority invalidation, not payload erasure. No consumed approval becomes reusable; new authority requires a new request and review. Old lease finish/retry is rejected, and quarantined jobs are no longer claimable. Unselected IDs, other scopes, completed job/outbox state and immutable audit remain unchanged.

Before row locks, the command takes short **EXCLUSIVE NOWAIT table locks** on approvals, durable jobs and outbox. These conflict with existing row-locking/mutating API and worker transactions, including new inserts, so no changes can slip into the reviewed transaction. Busy tables or operator rows fail fast without partial cleanup; stop/drain consumers and obtain a fresh preview. These database-wide locks briefly affect other scopes too. Ordinary reads remain possible. There is no new persistent startup fence: restarting consumers after commit can create fresh authority, so keep them stopped until all recovery gates pass.

All state changes, per-item metadata audit and `admin.restored_execution_quarantined` receipt commit together. The receipt identifies target/scope/operator, reviewed plan and selected outcomes, with `dispatch_activated=false` and `recovery_complete=false`. Audit or guard failures roll back. After uncertain commit, inspect current metadata/receipt and preview again. Public audit is observational, not bearer authority or proof all queues are safe.

No schema change, dependency, grant, API, UI, service, worker daemon or automatic activation is added. Existing cancellation, job-context and outbox invariants remain in force. No schema rollback is needed for these existing terminal states.

## Remaining recovery and verification

Selected coverage does not replace global inventory, revoked restored sessions, [Work quarantine](WORK_RESTORE_QUARANTINE.md), [known forgetting checkpoint](WORK_MANIFEST_AUTHENTICATION.md), [pending Work cleanup](WORK_RESTORE_REQUESTS.md), independent credentials/keys, external receipts, sources/derived/unmanaged exports or full-host/off-site/actual M2 acceptance.

Tests use API-created approvals/jobs, actual worker claims and no-op completion, negative target/operator/role/time/scope/handler/linkage cases, exact review, audit/final-age rollback, busy-writer refusal and worker fencing in both directions. Logical restore and Linux maintenance-container drills verify pending/approved/consumed/queued/leased/completed states, cancellation/dead-lettering, old-token denial, receipt/replay behavior and unchanged terminal/unselected/foreign controls. No external action is performed.
