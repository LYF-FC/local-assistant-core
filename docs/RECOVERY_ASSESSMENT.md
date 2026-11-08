# Assess an isolated restore and choose the next recovery steps

Spec 038 brings the existing recovery tools together through a bounded metadata inventory, optional independently pinned checkpoint assessment, and this operator sequence. It changes no business records and appends one `admin.recovery_assessed` inspection event. It does not run cleanup, enable services or certify full recovery. No information leaves the private environment.

## Prepare the isolated target

Use synthetic development/test data and the existing reviewed maintenance configuration for the isolated restored database. Keep API, workers and consumers stopped. Preserve users, CA, secrets and volumes. Upgrade the normal schema first; no new migration or dependency is introduced here. Tests require disposable `butler_test*` targets.

Use the clean READ COMMITTED owner of recovery tables and audit, an active technical-admin UUID as the audit reference, one **synthetic workspace UUID** and one known execution scope. The operator reference is independent of any browser session, so it still works after global sign-out. Explicit target/configured/actual database matching identifies the chosen database, not proof that it is actually a restore.

```sh
docker compose --env-file RESTORED_ENV -f infra/core/compose.yml run --rm --no-deps -T migrate \
  python -m app.recovery_assessment --environment development \
  --restored-database RESTORED_DATABASE --operator OPERATOR_UUID \
  --workspace WORKSPACE_UUID --scope household_shared
```

This first command can run without a key or manifest. It must then report the checkpoint as **not supplied/unverified** and request independent evidence. It never discovers trust from files, database receipts or a previous report.

## Supply a known recovery checkpoint

Recover the separately protected workspace key and the independently retained public fingerprint and source export hash. Follow [manifest authentication](WORK_MANIFEST_AUTHENTICATION.md). Mount the key and manifest directories read-only and supply all four evidence arguments together:

```sh
docker compose --env-file RESTORED_ENV -f infra/core/compose.yml run --rm --no-deps -T \
  -v "$BUTLER_SUPPRESSION_DIR:/recovery:ro" \
  -v "$BUTLER_RECOVERY_KEY_DIR:/recovery-keys:ro" migrate \
  python -m app.recovery_assessment --environment development \
  --restored-database RESTORED_DATABASE --operator OPERATOR_UUID \
  --workspace WORKSPACE_UUID --scope household_shared \
  --recovery-key /recovery-keys/recovery-key.json \
  --expected-key-fingerprint TRUSTED_FINGERPRINT \
  --manifest /recovery/manifest.json --expected-manifest-hash TRUSTED_MANIFEST_HASH
```

The normal CLI verifies file protections, key namespace/pin, HMAC and known checkpoint **before opening the database**. Partial arguments or invalid/substituted evidence reject without a report. Do not extract expected values from candidate files to make verification pass. Existing trusted prior implementation review/56 export hashes remain compatible. If independent evidence is missing, keep it unverified and obtain a verified source export or separately reviewed exceptional recovery.

Once the workspace is disabled/no-grant, assessment reuses the existing suppression preview to report supplied decision and linked-effect counts. It does not apply those decisions or return an action review hash. A known checkpoint identity is not proof no newer decisions were lost. Internal Python evidence defaults to `trusted_owner_input`; only the normal verified CLI path is labelled HMAC-verified. Neither boundary resists the host/database owner.

## Read the report accurately

| Report section | Meaning and limit |
|---|---|
| Global sessions | Exact current unrevoked count across scopes, including non-Work and expired sessions |
| Chosen execution scope | Exact outstanding approval/job counts and at most 25 combined candidate references; `has_more` explicitly means the list is incomplete |
| Candidate flags | Known no-op handler and expected binding/linkage metadata checks; not payload/source authentication or permission to execute |
| Other execution scopes | Outstanding counts outside the selected scope; reassess each relevant known scope separately |
| Selected Work | Enabled/grant state, pending captures/confirmations/review-cache counts, expired live note/party counts and other-workspace count |
| Credentials | Public current-database-OID role/login presence, login capability and connection count only; no passwords/verifiers or complete role-profile/secret-recovery proof |
| Checkpoint | Missing evidence, required workspace quarantine, or observed supplied forgetting changes after quarantine |
| Required actions | Existing-tool steps suggested by the observed state, not automatically executed |
| Unverified gates | Independent latest coverage, key/credential/copied-role recovery, other workspaces, sources/derived/unmanaged exports, external effects and full-host/off-site/owner acceptance |

The report always returns `activation_authorized=false` and `recovery_complete=false`. Zero counts or a verified supplied checkpoint cannot turn it green for activation. Unsupported handlers and inconsistent job/outbox linkage are explicitly flagged; do not silently omit them or apply a no-op procedure to external effects. UUID metadata and real reports remain local; shared CI uses synthetic fixtures only.

Role and connection catalog observations can change independently of the business-table locks; recheck them through the credential procedure. The report ID/hash binds the observed metadata to its inspection audit. It is **not** a cleanup approval, bearer permission, source signature or a permanently current inventory. The report has no apply mode. Obtain each existing tool's own full current preview and exact reviewed plan before writing anything.

## Follow the relevant existing tools, then reassess

| Required action | Existing reviewed procedure |
|---|---|
| `revoke_global_sessions` | [Global restored-session batches](RESTORED_SESSION_QUARANTINE.md); fresh review per batch until clear at commit |
| `quarantine_selected_workspace` | [Work quarantine](WORK_RESTORE_QUARANTINE.md); disable, remove grants and sign out affected grantees |
| `review_selected_scope_execution` | [Selected no-op execution quarantine](RESTORED_EXECUTION_QUARANTINE.md); use explicit supported/intact IDs, at most 25 combined, and refresh the inventory after cleanup |
| Unsupported/inconsistent execution | Separately reviewed reconciliation; future external/ambiguous writes require provider evidence |
| `assess_other_execution_scopes` | Repeat assessment with the other relevant known scope; chosen-scope cleanup is not global coverage |
| `discard_pending_work_input` | [Pending Work cleanup](WORK_RESTORE_REQUESTS.md); all-or-nothing bounded requests/cache redaction |
| `reconcile_expired_work_records` | [Work retention](WORK_RETENTION.md); review current expired batches and linked effects |
| Missing checkpoint / assessment after quarantine / supplied forgetting | [Authenticated checkpoint recovery](WORK_MANIFEST_AUTHENTICATION.md) and [older-backup reconciliation](WORK_BACKUP_SUPPRESSION.md) |
| `review_managed_login_and_drain` | [Restored credential inventory/revocation](RESTORED_WORK_CREDENTIALS.md), [credential lifecycle](WORK_CREDENTIAL_LIFECYCLE.md) and [adapter recovery](WORK_SYNTHETIC_ADAPTER.md); current-OID observations do not cover copied cluster roles or independent secrets |

Keep services stopped throughout. Quarantine must precede applicable Work cleanup; a supplied forgetting manifest may already remove some linked pending input. After each approved operation, refresh assessment and review what remains. Do not edit or truncate evidence to bypass bounds. Repeat for other relevant scopes/workspaces and retain separate acceptance of independent recovery gates.

## Locking, audit and failure behavior

Assessment takes the Work registry try-lock before short fail-fast EXCLUSIVE locks on session/approval/job/Work tables and protected operator rows. This follows existing Work lock ordering and excludes current identity/worker writes and row-locking consumers. Busy contexts fail before a partial report; stop/drain consumers and retry. These short database-wide locks affect other scopes too; ordinary reads remain possible. Statement/lock budgets apply to counts as well. There is no permanent startup fence.

One metadata inspection audit commits with a successful report. No payloads, names, raw content hashes, credential/lease/token material or full candidate list are copied to audit. Audit or evidence errors produce no success report. After an uncertain commit, inspect metadata; a new assessment appends a new observation and grants no write authority.

## Retain actual host acceptance separately

Use issue #5 (historical private reference omitted) and [POC acceptance](POC_ACCEPTANCE.md) to retain the installed commit, actual target OS/architecture, Docker/Compose/browser versions, chosen RPO/RTO, encrypted/versioned independent copies and key recovery, and a timed isolated full-host restore. Initial reported M2 success is distinct from retained Context/Work and full-host recovery evidence. Execution-host or CI versions are not substitutes for the intended installed host.

The staged synthetic drill observes the source, older restored snapshot before Work quarantine, after forgetting reconciliation, after selected execution quarantine and after global sign-out. It compares business tables before/after every assessment. Final session clearance removes that action, while a deliberately retained unselected queued control and independent unknown gates remain visible. Linux maintenance-container checks repeat checkpoint assessment before/after global sign-out. These tests demonstrate the report is useful without becoming a false completion certificate.

Always inspect selected-workspace current/copied credentials through [the separate credential procedure](RESTORED_WORK_CREDENTIALS.md), even when the assessment's current-OID login observation is absent. This assessment deliberately does not enumerate copied roles. Revocation receipts and fresh inspections still do not authorize activation or establish independent secret recovery.

For explicit selected source withdrawal, use [the reviewed source/derived-note procedure](WORK_SOURCE_WITHDRAWAL.md). It includes historical-only dependencies and pending new captures. It neither deletes immutable validation fixtures/original files nor proves independent latest source withdrawal; older backups can restore active source flags. Assessment's original/source/derived unknowns remain intentionally unverified.

For independently retained selected source decisions, follow [source checkpoint export/offline verification/reapplication](WORK_SOURCE_CHECKPOINTS.md). It binds supplied source receipt evidence to the actual cleanup receipt; the assessment's latest/complete/source/original/host unknowns remain intentionally unverified.
