# Quarantine all restored platform sessions

Spec 037 adds a reviewed global sign-out step for an isolated development/test restore. An older backup can revive sessions that were revoked later. Work quarantine covers its grantees; this command also covers users with no Work grants and sessions across every scope, including expired-but-unrevoked sessions. No information leaves the private environment.

## Keep consumers stopped

Restore into a separate database and apply normal migrations. Keep API, workers and other consumers stopped. Use a clean READ COMMITTED owner of auth_sessions, users and audit, with an explicit active technical-admin UUID as the audit reference. The reference does not require a live browser session: the operator's own restored sessions may be revoked too. Test targets must be disposable `butler_test*` databases. The explicit target acknowledges the chosen database, not proof that it is actually a restore.

```sh
docker compose --env-file RESTORED_ENV -f infra/core/compose.yml run --rm -T migrate \
  python -m app.restore_sessions --environment development \
  --restored-database RESTORED_DATABASE --operator OPERATOR_UUID --limit 100
```

Review target name/OID, operator, fixed server issue time, limit and each session ID/user ID/creation/last-seen/expiry. No token/CSRF/password hashes or account labels are returned. The batch is the first current unrevoked sessions ordered by UUID, including expired sessions. Choose a limit from 1 to 100; the plan is capped at 32 KiB. `has_more=true` requires another fresh reviewed batch after this one.

```sh
docker compose --env-file RESTORED_ENV -f infra/core/compose.yml run --rm -T migrate \
  python -m app.restore_sessions --environment development \
  --restored-database RESTORED_DATABASE --operator OPERATOR_UUID --limit 100 \
  --issued-at PREVIEW_ISSUED_AT --reviewed-hash PREVIEW_HASH \
  --decision revoke_restored_sessions
```

Copy the exact time/hash and use the same limit. Apply recomputes the current batch within five minutes, checks age again before commit and rejects changed batch metadata, target, operator, limit or time. Replaying this command cannot advance to the next batch. Obtain and review a new preview for every batch until none remain. Changes outside the current batch do not invalidate its review if the batch membership/order and `has_more` remain unchanged; this is not a frozen inventory of the entire database.

## Receipt and preserved state

All listed sessions receive a revocation timestamp and commit with one `admin.restored_sessions_revoked` metadata receipt. It lists revoked session/user IDs, target/operator and reviewed plan. Already revoked rows and their timestamps are preserved. Password hashes, users, scopes, Work grants/content, Memory and approvals/jobs remain unchanged. An empty preview cannot create a completion receipt. Audit, guard or final-age failures roll back the entire batch; after uncertain commit, inspect current metadata/receipt and preview again.

`remaining_unrevoked=true` means more reviewed batches are needed. A final `session_set_clear_at_commit=true` means no unrevoked sessions existed under the transaction lock at that instant. It is **not a permanent sign-in ban or a full recovery certificate**. The receipt always reports `api_activated=false` and `recovery_complete=false`. Passwords stay valid; a deliberately restarted API may permit fresh sign-in after recovery. Do not restart it solely because this receipt is clear.

Before row locks, an EXCLUSIVE NOWAIT lock on auth_sessions conflicts with existing identity resolution (`FOR UPDATE`) and login/logout writes, including new inserts. Operator rows are also locked without waiting. Busy consumers fail fast before partial changes; stop/drain them and obtain a fresh preview. These short database-wide locks affect all scopes while held. Ordinary reads remain possible. No runtime API changes, permanent startup fence, schema migration, new grant/dependency/service or automatic restart are introduced.

## Complete the other recovery gates

This invalidates the current restored platform-session set. It does not rotate credentials/keys, terminate arbitrary database connections, cancel approval/job authority, purge content, prove latest forgetting completeness or complete actual full-host/off-site/M2 acceptance. Follow the applicable [Work quarantine](WORK_RESTORE_QUARANTINE.md), [checkpoint forgetting](WORK_MANIFEST_AUTHENTICATION.md), [pending Work cleanup](WORK_RESTORE_REQUESTS.md) and [selected no-op execution quarantine](RESTORED_EXECUTION_QUARANTINE.md), plus remaining secret/source/derived/export/host checks before exposing restored services.

Verification uses actual API sessions and private/shared non-Work users, copied-token denial, expired-session inclusion, already-revoked preservation, unchanged credentials and later deliberate sign-in, multi-batch/replay/no-op checks, target/role/operator/time negatives, audit/final-age rollback and identity concurrency in both directions. Logical restore and Linux maintenance-container drills include more than 100 sessions to require fresh batches; non-Work copied tokens survive the earlier Work checks and stop resolving after global quarantine. Passwords, grants, content and completed execution history remain unchanged.
