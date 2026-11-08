# Manual synthetic Work retention cleanup

Spec 030 adds a trusted local preview/review/apply procedure for expired synthetic Work data. Nothing leaves the private environment. No scheduler, API endpoint, UI, new credential, grant or external service is added. Standard update runs migration 0016; cleanup needs a deliberate operator action.

## Disable, preview, review, apply

Use the existing development/test configuration and short-lived migration container. Keep users, CA, secrets and volumes. The configured environment must match the argument; test databases must be explicitly disposable `butler_test*` targets. Never give the API the migration connection. First disable the chosen synthetic workspace using the existing trusted `app.work_manage disable` procedure in [Work access](WORK_ACCESS_FOUNDATION.md).

Select an existing active user with `technical_admin` as the operator audit reference. This local selection records responsibility; it does not prove an HTTP human session or grant that user new Work access. Only a clean storage/audit table-owner login in a READ COMMITTED transaction can operate the tool. Assumed/scoped/runtime roles fail closed, even with a forged maintenance setting. Workspace and operator eligibility are locked for the transaction.

```sh
docker compose -f infra/core/compose.yml run --rm -T migrate \
  python -m app.work_retention --environment development \
  --workspace WORKSPACE_UUID --operator OPERATOR_UUID --limit 25
```

Replace placeholders with current synthetic IDs. Preview returns metadata JSON: fixed server cutoff, workspace/operator, candidate IDs/revisions/states/expiry, linked request/review IDs, limit, `has_more` and `reviewed_hash`. It contains no note text, party labels, sources, session credentials or content-derived hashes. Its digest covers metadata only. Review the complete batch, including linked effects, locally.

```sh
docker compose -f infra/core/compose.yml run --rm -T migrate \
  python -m app.work_retention --environment development \
  --workspace WORKSPACE_UUID --operator OPERATOR_UUID --limit 25 \
  --cutoff PREVIEW_CUTOFF --reviewed-hash PREVIEW_HASH \
  --decision apply_expired_cleanup
```

Copy cutoff/hash/limit from that exact preview. Cutoff must be timezone-aware, not future and at most five minutes old, including at the end of apply. Apply recomputes the complete plan under an exclusive registry transaction barrier before any row lock. Changed candidate/dependency metadata or operator/workspace eligibility rejects the transaction. New expirations after the fixed cutoff are left for another preview. A previously applied plan fails instead of silently taking the next batch. Empty apply fails without a completion receipt.

Each batch selects at most 25 expired notes, parties, pending capture/change/confirmation requests and review preparations, deterministically ordered by kind/UUID. Note forgetting also affects its linked pending corrections, pending confirmations and all retained review hashes; those collateral effects appear in the reviewed plan. More than 100 linked records or a plan over 32 KiB fails before writing. Reconcile excessive linked preparations separately before selecting that note. This tool does not extend retention or reload historical payloads.

## What changes atomically

- Expired notes follow existing terminal forgetting: current payload and every revision are redacted, review hashes cleared, pending bound corrections denied/redacted, and immutable metadata audit/tombstone retained. Linked pending confirmations are denied.
- Expired parties lose their label through the existing forgetting lifecycle. Independently retained notes keep their historical owner UUID; the label is not copied into them.
- Expired pending capture/change requests become denied with payload/hash cleared; expired confirmations become denied. Orphan/other-session preparations do not need an active session to be erased. They are never executed as business actions.
- Expired review hashes on otherwise retained notes become null, with a private `draft.review_expired` audit entry. An unrelated unexpired hash remains intact.

All mutations, private audit and the metadata-only `admin.work_retention_applied` completion receipt commit together. Any guard/audit/commit failure rolls back. Output is emitted only after commit. The receipt records selected operator, plan digest, cutoff, IDs/outcomes and a receipt UUID; it is audit evidence, not bearer permission. It contains no content hash. The workspace remains disabled; no successful cleanup or receipt enables it.

After a timeout or uncertain commit, inspect current metadata and the completion receipt with a trusted local operator. Generate and review a fresh preview before another apply. A successful repeat preview can be empty; that is distinct from assuming the previous command failed. Do not restore payload or replay an old plan to retry. `has_more` requires another explicitly reviewed batch.

## Migration and recovery limits

Migration 0016 narrowly permits owner-only, disabled synthetic workspace, expired maintenance forgetting and expired review-hash redaction. Normal lifecycle guards, forced RLS, immutable history/audit and API privileges remain in place. It acquires the existing exclusive registry barrier before schema changes. Downgrade refuses existing retention completion/private-expiry evidence; use reviewed recovery rather than erasing it. Host/database owners can change guards, as with the existing trust model.

CI validates CLI preview/apply/replay denial in an actual migration container and backs up/restores a disabled synthetic workspace with erased note/history/party/request/hash data, its live control note and completion receipt. The normal role/RLS/copied-role and TLS/browser checks remain required. This is a same-cluster logical recovery check, not full-host acceptance.

An older backup predating cleanup can still resurrect content. Independent newer suppression-ledger reconciliation, stale restored grants/sessions, document keys, derived stores, original sources, downloaded exports, encrypted off-site copies and timed clean-host recovery remain open. Keep restored Work quarantined until those applicable gates are separately verified. This tool does not certify real employer data or complete spec 005/issue #5.

prior implementation review delivers this cleanup procedure. Spec 031 adds a separate manual restored-workspace access/session quarantine prerequisite; see [WORK_RESTORE_QUARANTINE](WORK_RESTORE_QUARANTINE.md). It does not implement older-backup suppression.

Spec 032 adds reviewed reconciliation of supplied terminal decisions into older quarantined synthetic snapshots using a protected independent metadata file. It does not prove latest complete coverage or full-host recovery. See [WORK_BACKUP_SUPPRESSION](WORK_BACKUP_SUPPRESSION.md).
