# Current-session synthetic draft preview and review preparation

Spec 020 adds two protected POST routes for a single synthetic draft: `/api/v1/work/workspaces/{workspace}/drafts/{record}/preview` and `/review`. This is current-user preview and an explicit revision/content-bound review acknowledgement, **not a lifecycle confirmation writer, capture UI, execution approval or proof of physical human attention**. The returned flags remain confirmation_applied/execution_allowed/model_invoked/ingestion_allowed=false. Existing five Work content gates stay pending.

## Default and permission boundary

Standard POC stays disabled. Review needs the independent `BUTLER_WORK_DRAFT_REVIEW_ENABLED=true`, existing synthetic adapter opt-in/private file, explicit local scoped review provisioning and current active user/session/workspace grant. HTTPS/exact Host/Origin/CSRF/current membership are checked before any credential read or work connection. Unknown/unassigned workspaces share 404; invalid CSRF is 403; absent adapter is static 503. Invalid bodies are sanitized 422.

Reuse the existing same-target/driver/OID checks and clean restricted login with exactly one SET-only NOLOGIN workspace membership, no owner/elevated/family privileges. Every normal file lease constructs and disposes its own bounded engine. The API never receives a database-owner credential. Normal storage provisioning still grants no new draft-domain access.

`app.work_review_storage` is a separate trusted local development/test provisioner. It acquires the registry exclusive barrier before workspace row locks, reuses/reset-validates base storage role privileges, then grants SELECT on drafts/source registry/review preparations, explicit INSERT columns on preparations/private audit and UPDATE(id) on drafts for FOR SHARE row locking. **No draft payload/state/revision update is granted.** Existing identity/revision guards reject every actual id or noop mutation; restricted-role tests prove this. Standard install/startup never runs this provisioner. Later ordinary storage reprovision resets these additional grants; review access must be explicitly provisioned again.

## Preview and explicit review body

Preview accepts only `{}`. Server selects a live draft through workspace RLS, locks it FOR SHARE, checks session clock and expiry, records a minimal private read-prepared event and commits the work transaction. A successful identity audit/commit is required before HTTP release. Return a schema-versioned current snapshot, revision, server-checked timestamp and SHA-256 of the stored PostgreSQL JSONB representation. Client must echo the supplied hash, not re-serialize normalized JSON and invent a hash.

Review accepts only:

```json
{"expected_revision":1,"reviewed_hash":"<64 lower-case hexadecimal characters>","request_id":"<client UUID>","decision":"approve"}
```

There is no body actor/session/workspace/content/SQL/role/intent override. The server resolves actor/session and fixed intent confirm_note, reselects and locks the current live draft, compares exact revision/hash, and requires selected active same-workspace sources. Non-null parties and lifecycle writes remain unsupported. Source RLS is current for both draft payload and review-hash visibility; stale revisions/revoked sources cannot expose an older preparation hash through scoped SQL. Forgotten preparations retain metadata with a null hash.

The response acknowledges a prepared review only. It does not set the draft state to confirmed, assign an owner, invoke a model, send anything or authorize a future delayed action. UI review/capture and workspace-party assignment are not implemented in this PR. Sources are still explicit synthetic catalog references, not imported employer documents.

## Idempotency, expiry and separate commits

Migration 0011 stores private review preparations with server UUID/time/five-minute validity, workspace/record/revision, server actor/session, client request UUID and content hash. Unique `(workspace,actor,session,request)` binds replay to the current session. Same request revalidates current authority, source/record/revision/hash and receipt expiry before returning the existing ID; conflicting or expired reuse returns 409. A new session gets a distinct preparation, not the previous session's receipt. Concurrent same-session requests serialize through current session authority and produce one preparation/private review event.

Private audit records metadata only. Work preparation commits before the outer identity audit. If identity commit fails, a prepared work row may remain with no response receipt; it is not proof of committed identity review/delivery. A later retry may recover it only after all current checks and a successful identity audit/commit. Session/record/receipt expiry is checked after work commit and lease cleanup before response release. Receipt validity is not a background deletion schedule; hash storage ends on draft forgetting, with future retention jobs independently specified.

Registry/source/grant revocation is fenced through both work and identity commits. Current-draft row locks end at work commit: a local owner may correct a note afterwards, so a returned snapshot can become stale and is not a transferable permission token. **Future confirmation must require matching committed identity evidence, fresh current user/session/grant/source/record revision/hash/expiry checks and atomic one-time consumption. No consumption endpoint or confirmation writer exists here.** No distributed transaction or blind automatic mutation retry is claimed. Identity success metadata explicitly includes the preparation UUID and authenticated session UUID for future evidence matching.

## Forgetting and restore

A review hash is content-derived private data, not immutable audit metadata. The draft-forget transaction clears hashes of all associated preparations. A review guard permits only that exact hash-to-null change after parent forgetting; other updates/delete/truncate are denied. A hash-redaction failure rolls back the entire draft/history/audit/tombstone forget transaction. Original source objects, old client responses and older backups remain separate retention/recovery concerns.

The logical restore sentinel includes a live preparation/hash and a forgotten preparation with null hash, alongside existing current/history/tombstone/RLS/copy-role checks. This proves an after-forget dump preserves hash erasure. It does not provide independent newer suppression-ledger, key or full-host recovery (#5).

## Optional local synthetic validation

Normal update/rebuild after merge applies migration 0011 with no new credentials or owner setup. These optional commands require the existing synthetic workspace/grants/managed login/protected file from the prior runbooks, updated images and no real content:

```sh
review_compose() {
  docker compose --env-file .env -f infra/core/compose.yml -f infra/core/work-synthetic.override.yml -f infra/core/work-draft-review.override.yml "$@"
}
review_compose run --rm migrate python -m app.work_review_storage --environment development --workspace synthetic-poc
review_compose up -d --no-deps --build --wait api
```

Provisioning requires an active synthetic workspace and creates no note, source, retention policy or credential. Tests create those fixtures through trusted administration; there is no end-user capture command in this increment. Keep the protected volume local and out of general archives as before. To deactivate, use the existing explicit workspace-disable fence and recreate API without review overlay. Config/file changes alone do not recall an in-flight authorized snapshot.

Downgrade preserves metadata-only review audit and does not automatically reset explicitly granted role ACLs. Disable the workspace/adapter first and deliberately reapply the matching base provisioner to reset review grants before reusing an older schema. Do not treat destructive downgrade as rollback for future live work data.

## Evidence and next step

Tests cover default-disabled/strict/TLS API boundaries, no unauthorized credential reads, actual restricted preview/review/replay, changed revision/hash/source/grant/session/expiry, audit and outer identity failure, atomic hash redaction, concurrent replay, row-lock waits and grant waits through both commits. CI runs unchanged default browser acceptance, then explicit private-volume/verified TLS preview/review/replay and file-removal refusal. There is no new UI layout or owner-host acceptance.

Next is one-time review consumption and current-human confirmation writes with explicit response/idempotency semantics, then synthetic capture/workspace-party/context flows and independent retention/key/recovery acceptance before employer data.

Continuation: prior implementation review/spec020 is merged. prior implementation review/spec021 adds independently opted-in metadata request/status and a manual local one-time confirmation executor; see [confirmation procedure](WORK_DRAFT_CONFIRMATION.md). A prepared review remains insufficient without committed identity evidence and fresh authorization/content checks. Capture UI and real-content gates remain separate.

Spec 030 adds an explicit bounded expired-data cleanup path while a synthetic workspace is disabled; see [WORK_RETENTION](WORK_RETENTION.md). There is still no automatic deletion schedule or independent older-backup suppression.
