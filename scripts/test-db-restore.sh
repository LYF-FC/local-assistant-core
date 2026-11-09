#!/usr/bin/env bash
set -euo pipefail
# Runs only against the explicitly disposable CI PostgreSQL service container.
[[ "${BUTLER_ENV:-}" == test && "${BUTLER_POSTGRES_DB:-}" == butler_test ]] || exit 2
# An explicit CI container disambiguates local hosts with another PostgreSQL stack.
CONTAINER_ID=${BUTLER_CI_POSTGRES_CONTAINER:-$(docker ps --filter ancestor=postgres:17 --format '{{.ID}}')}
[[ -n "$CONTAINER_ID" && "$CONTAINER_ID" != *$'\n'* ]] || exit 2
[[ "$(docker inspect --format '{{.Config.Image}}' "$CONTAINER_ID")" == postgres:17 ]] || exit 2
DUMP=$(mktemp)
BUTLER_SUPPRESSION_DIR=$(mktemp -d)
# macOS temporary roots can use a symlink alias; pass the real private path to
# the archive adapter without weakening its no-symlink traversal contract.
BUTLER_SUPPRESSION_DIR=$(python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve(strict=True))' "$BUTLER_SUPPRESSION_DIR")
trap 'unlink "$DUMP"; rm -rf "$BUTLER_SUPPRESSION_DIR"' EXIT
# Archive files are a separate backup input; pg_dump alone does not include them.
export BUTLER_DOCUMENT_ARCHIVE_DIRECTORY="$BUTLER_SUPPRESSION_DIR/archive-source"
mkdir -m 700 "$BUTLER_DOCUMENT_ARCHIVE_DIRECTORY"
(cd backend && uv run --locked python -m app.document_archive "$BUTLER_DOCUMENT_ARCHIVE_DIRECTORY")
export BUTLER_SUPPRESSION_OLDER_FILE="$BUTLER_SUPPRESSION_DIR/older.json"
export BUTLER_SUPPRESSION_MANIFEST_FILE="$BUTLER_SUPPRESSION_DIR/manifest.json"
export BUTLER_SUPPRESSION_KEY_FILE="$BUTLER_SUPPRESSION_DIR/primary-key.json"
export BUTLER_SOURCE_KEY_FILE="$BUTLER_SUPPRESSION_DIR/source-primary-key.json"
export BUTLER_SOURCE_OLDER_FILE="$BUTLER_SUPPRESSION_DIR/source-older.json"
export BUTLER_SOURCE_MANIFEST_FILE="$BUTLER_SUPPRESSION_DIR/source-newer.json"
# Public anchor is captured from trusted generation, not adopted from the input file.
BUTLER_SUPPRESSION_KEY_FINGERPRINT=$(
  (cd backend && uv run --locked python -m app.work_suppression_auth generate --workspace a1a1a1a1-a1a1-41a1-81a1-a1a1a1a1a1a1 --output "$BUTLER_SUPPRESSION_KEY_FILE") |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["fingerprint"])'
)
export BUTLER_SUPPRESSION_KEY_FINGERPRINT
# No user data or credentials are emitted in output.
docker exec "$CONTAINER_ID" psql -U postgres -d butler_test -v ON_ERROR_STOP=1 -c "CREATE TABLE recovery_sentinel (id integer PRIMARY KEY, value text NOT NULL); INSERT INTO recovery_sentinel VALUES (1, 'synthetic-recovery-ok');"
docker exec "$CONTAINER_ID" psql -U postgres -d butler_test -v ON_ERROR_STOP=1 -c "INSERT INTO audit_events (id,occurred_at,environment,initiator_type,initiator_id,scope_key,event_type,result_status) VALUES ('11111111-1111-4111-8111-111111111111',now(),'test','system','synthetic-restore','technical_admin','recovery.sentinel','success');"
# Synthetic interrupted delivery: backup/restore must preserve the queue state.
docker exec -i "$CONTAINER_ID" psql -U postgres -d butler_test -v ON_ERROR_STOP=1 <<'SQL'
INSERT INTO users (id,slug,display_name,is_active,created_at,updated_at)
VALUES ('22222222-2222-4222-8222-222222222222','synthetic-queue-restore','Synthetic',true,now(),now());
INSERT INTO approvals (id,scope_key,action_type,status,requested_by,request_payload,payload_hash,policy_version,expires_at,requested_at)
VALUES ('33333333-3333-4333-8333-333333333333','technical_admin','validation.noop','pending','22222222-2222-4222-8222-222222222222','{}',repeat('a',64),'v0.1-record-only-1',now()+interval '15 minutes',now());
UPDATE approvals SET status='approved',approved_by='22222222-2222-4222-8222-222222222222',resolved_at=now() WHERE id='33333333-3333-4333-8333-333333333333';
UPDATE approvals SET status='consumed',consumed_at=now() WHERE id='33333333-3333-4333-8333-333333333333';
INSERT INTO durable_jobs (id,approval_id,requested_by,scope_key,action_type,payload_hash,idempotency_hash,status,created_at)
VALUES ('44444444-4444-4444-8444-444444444444','33333333-3333-4333-8333-333333333333','22222222-2222-4222-8222-222222222222','technical_admin','validation.noop',repeat('a',64),repeat('b',64),'running',now());
INSERT INTO job_outbox (id,job_id,state,attempts,available_at,lease_hash,lease_until)
VALUES ('55555555-5555-4555-8555-555555555555','44444444-4444-4444-8444-444444444444','leased',1,now(),repeat('c',64),now()+interval '1 minute');
SQL
# A forgotten synthetic memory must remain scrubbed across a restore.
docker exec -i "$CONTAINER_ID" psql -U postgres -d butler_test -v ON_ERROR_STOP=1 <<'SQL'
INSERT INTO memory_records (id,owner_id,scope_key,kind,state,revision,title,content,source_type,source_reference,assessment,created_at,updated_at)
VALUES ('66666666-6666-4666-8666-666666666666','22222222-2222-4222-8222-222222222222','household_shared','preference','active',1,'Synthetic memory','{"value":"synthetic-restore-only"}','manual','synthetic-restore','confirmed',now(),now());
INSERT INTO memory_revisions (id,memory_id,revision,actor_id,snapshot,created_at)
VALUES ('77777777-7777-4777-8777-777777777777','66666666-6666-4666-8666-666666666666',1,'22222222-2222-4222-8222-222222222222','{"content":{"value":"synthetic-restore-only"}}',now());
UPDATE memory_records SET state='forgotten',revision=2,title=NULL,content=NULL,source_type=NULL,source_reference=NULL,assessment=NULL,expires_at=NULL,updated_at=now() WHERE id='66666666-6666-4666-8666-666666666666';
UPDATE memory_revisions SET snapshot=NULL WHERE memory_id='66666666-6666-4666-8666-666666666666';
SQL
# Synthetic identity registry only, not a work-content recovery claim.
docker exec -i "$CONTAINER_ID" psql -U postgres -d butler_test -v ON_ERROR_STOP=1 <<'SQL'
INSERT INTO work_workspaces (id,slug,is_active,created_at)
VALUES ('88888888-8888-4888-8888-888888888888','synthetic-work-restore',true,now());
INSERT INTO work_access_grants (user_id,workspace_id,capability,created_at)
VALUES ('22222222-2222-4222-8222-222222222222','88888888-8888-4888-8888-888888888888','work_private',now());
SQL
# Explicit trusted provisioning creates only a NOLOGIN role for synthetic validation.
(cd backend && uv run --locked python -m app.work_storage --environment test --workspace synthetic-work-restore)
BUTLER_CI_WORK_SOURCE_ROLE=$(docker exec "$CONTAINER_ID" psql -U postgres -d butler_test -Atc "SELECT 'butler_work_' || oid::text || '_88888888888848888888888888888888' FROM pg_database WHERE datname=current_database()")
[[ "$BUTLER_CI_WORK_SOURCE_ROLE" =~ ^butler_work_[0-9]+_88888888888848888888888888888888$ ]]
docker exec -i "$CONTAINER_ID" psql -U postgres -d butler_test -v ON_ERROR_STOP=1 -v storage_role="$BUTLER_CI_WORK_SOURCE_ROLE" <<'SQL'
BEGIN;
SET LOCAL ROLE :"storage_role";
INSERT INTO work.validation_records (workspace_id,id,marker)
VALUES ('88888888-8888-4888-8888-888888888888','99999999-9999-4999-8999-999999999999','synthetic:restore-marker');
INSERT INTO work.read_attempts (workspace_id,requested_by,session_id,event_type,record_count,record_ids)
VALUES ('88888888-8888-4888-8888-888888888888','22222222-2222-4222-8222-222222222222','aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','validation.read_prepared',1,'["99999999-9999-4999-8999-999999999999"]');
COMMIT;
SQL
(cd backend && uv run --locked python ../scripts/discovery-restore-fixtures.py seed)
(cd backend && uv run --locked python ../scripts/task-restore-fixtures.py seed)
(cd backend && uv run --locked python ../scripts/calendar-restore-fixtures.py seed)
(cd backend && uv run --locked python ../scripts/routine-restore-fixtures.py seed)
(cd backend && uv run --locked python ../scripts/invoice-restore-fixtures.py seed)
(cd backend && uv run --locked python ../scripts/email-intake-restore-fixtures.py seed)
(cd backend && uv run --locked python ../scripts/reminder-restore-fixtures.py seed)
(cd backend && uv run --locked python ../scripts/document-restore-fixtures.py seed)
(cd backend && uv run --locked python ../scripts/document-archive-restore-fixtures.py seed)
(cd backend && uv run --locked python ../scripts/pdf-restore-fixtures.py seed)
(cd backend && BUTLER_DRAFT_RESTORE_PHASE=seed uv run --locked python ../scripts/work-draft-restore.py)
(cd backend && uv run --locked python ../scripts/work-retention-fixtures.py seed)
(cd backend && uv run --locked python ../scripts/work-restore-fixtures.py seed)
(cd backend && uv run --locked python ../scripts/work-suppression-fixtures.py seed)
(cd backend && uv run --locked python ../scripts/work-restored-requests-fixtures.py seed)
(cd backend && uv run --locked python ../scripts/restored-execution-fixtures.py seed)
(cd backend && uv run --locked python ../scripts/restored-session-fixtures.py seed)
(cd backend && uv run --locked python ../scripts/work-source-withdrawal-fixtures.py seed)
(cd backend && uv run --locked python ../scripts/recovery-assessment-fixtures.py source)
docker exec "$CONTAINER_ID" pg_dump -U postgres -d butler_test --format=custom > "$DUMP"
python3 - <<'PYARCHIVE'
import os, shutil
from pathlib import Path
source = Path(os.environ["BUTLER_DOCUMENT_ARCHIVE_DIRECTORY"])
shutil.copytree(source, source.parent / "archive-restored")
PYARCHIVE
BUTLER_SUPPRESSION_EXPECTED_HASH=$(
  (cd backend && uv run --locked python ../scripts/work-suppression-fixtures.py export) |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["checkpoint"]["manifest_hash"])'
)
export BUTLER_SUPPRESSION_EXPECTED_HASH
# Withdraw on the newer source only after the older dump, then retain source-generated public pins.
(cd backend && uv run --locked python ../scripts/work-source-withdrawal-fixtures.py check)
BUTLER_SOURCE_PUBLIC_REFERENCE=$(cd backend && uv run --locked python ../scripts/work-source-checkpoint-fixtures.py export)
BUTLER_SOURCE_KEY_FINGERPRINT=$(printf '%s' "$BUTLER_SOURCE_PUBLIC_REFERENCE" | python3 -c 'import json,sys; print(json.load(sys.stdin)["key_fingerprint"])')
BUTLER_SOURCE_EXPECTED_HASH=$(printf '%s' "$BUTLER_SOURCE_PUBLIC_REFERENCE" | python3 -c 'import json,sys; print(json.load(sys.stdin)["manifest_hash"])')
export BUTLER_SOURCE_KEY_FINGERPRINT BUTLER_SOURCE_EXPECTED_HASH
cp "$BUTLER_SOURCE_KEY_FILE" "$BUTLER_SUPPRESSION_DIR/source-recovered-key.json"
chmod 600 "$BUTLER_SUPPRESSION_DIR/source-recovered-key.json"
unlink "$BUTLER_SOURCE_KEY_FILE"
export BUTLER_SOURCE_KEY_FILE="$BUTLER_SUPPRESSION_DIR/source-recovered-key.json"
printf '%s\n' 'Two real same-key source exports retained; independent newer checkpoint captured before restore'
# Recover a separate test key copy after removing the primary; no key is in pg_dump.
cp "$BUTLER_SUPPRESSION_KEY_FILE" "$BUTLER_SUPPRESSION_DIR/recovered-key.json"
chmod 600 "$BUTLER_SUPPRESSION_DIR/recovered-key.json"
unlink "$BUTLER_SUPPRESSION_KEY_FILE"
export BUTLER_SUPPRESSION_KEY_FILE="$BUTLER_SUPPRESSION_DIR/recovered-key.json"
docker exec "$CONTAINER_ID" createdb -U postgres butler_test_restore
docker exec -i "$CONTAINER_ID" pg_restore -U postgres -d butler_test_restore --exit-on-error < "$DUMP"
RESULT=$(docker exec "$CONTAINER_ID" psql -U postgres -d butler_test_restore -Atc "SELECT value FROM recovery_sentinel WHERE id=1")
[[ "$RESULT" == synthetic-recovery-ok ]]
[[ "$(docker exec "$CONTAINER_ID" psql -U postgres -d butler_test_restore -Atc "SELECT version_num FROM alembic_version")" == 0029_email_intake ]]
[[ "$(docker exec "$CONTAINER_ID" psql -U postgres -d butler_test_restore -Atc "SELECT result_status FROM audit_events WHERE event_type='recovery.sentinel'")" == success ]]
if docker exec "$CONTAINER_ID" psql -U postgres -d butler_test_restore -v ON_ERROR_STOP=1 -c "UPDATE audit_events SET result_status='tampered' WHERE event_type='recovery.sentinel'" >/dev/null 2>&1; then
  echo "Restored audit guard did not reject mutation" >&2
  exit 1
fi
[[ "$(docker exec "$CONTAINER_ID" psql -U postgres -d butler_test_restore -Atc "SELECT state || ':' || attempts FROM job_outbox WHERE id='55555555-5555-4555-8555-555555555555'")" == leased:1 ]]
[[ "$(docker exec "$CONTAINER_ID" psql -U postgres -d butler_test_restore -Atc "SELECT status FROM durable_jobs WHERE id='44444444-4444-4444-8444-444444444444'")" == running ]]
[[ "$(docker exec "$CONTAINER_ID" psql -U postgres -d butler_test_restore -Atc "SELECT state FROM memory_records WHERE id='66666666-6666-4666-8666-666666666666' AND content IS NULL AND title IS NULL AND source_reference IS NULL")" == forgotten ]]
[[ "$(docker exec "$CONTAINER_ID" psql -U postgres -d butler_test_restore -Atc "SELECT count(*) FROM memory_revisions WHERE memory_id='66666666-6666-4666-8666-666666666666' AND snapshot IS NOT NULL")" == 0 ]]
[[ "$(docker exec "$CONTAINER_ID" psql -U postgres -d butler_test_restore -Atc "SELECT capability FROM work_access_grants WHERE user_id='22222222-2222-4222-8222-222222222222' AND workspace_id='88888888-8888-4888-8888-888888888888'")" == work_private ]]
for table in work_workspaces work_access_grants; do
  [[ "$(docker exec "$CONTAINER_ID" psql -U postgres -d butler_test_restore -Atc "SELECT has_table_privilege('butler_runtime', '$table', 'SELECT')")" == t ]]
  [[ "$(docker exec "$CONTAINER_ID" psql -U postgres -d butler_test_restore -Atc "SELECT has_table_privilege('butler_runtime', '$table', 'INSERT,UPDATE,DELETE,TRUNCATE')")" == f ]]
done
(cd backend && BUTLER_POSTGRES_DB=butler_test_restore uv run --locked python ../scripts/discovery-restore-fixtures.py check)
(cd backend && BUTLER_POSTGRES_DB=butler_test_restore uv run --locked python ../scripts/task-restore-fixtures.py check)
(cd backend && BUTLER_POSTGRES_DB=butler_test_restore uv run --locked python ../scripts/calendar-restore-fixtures.py check)
(cd backend && BUTLER_POSTGRES_DB=butler_test_restore uv run --locked python ../scripts/routine-restore-fixtures.py check)
(cd backend && BUTLER_POSTGRES_DB=butler_test_restore uv run --locked python ../scripts/invoice-restore-fixtures.py check)
(cd backend && BUTLER_POSTGRES_DB=butler_test_restore uv run --locked python ../scripts/email-intake-restore-fixtures.py check)
(cd backend && BUTLER_POSTGRES_DB=butler_test_restore uv run --locked python ../scripts/reminder-restore-fixtures.py check)
(cd backend && BUTLER_POSTGRES_DB=butler_test_restore uv run --locked python ../scripts/document-restore-fixtures.py check)
(cd backend && BUTLER_DOCUMENT_ARCHIVE_DIRECTORY="$BUTLER_SUPPRESSION_DIR/archive-restored" BUTLER_POSTGRES_DB=butler_test_restore uv run --locked python ../scripts/document-archive-restore-fixtures.py check)
(cd backend && BUTLER_DOCUMENT_ARCHIVE_DIRECTORY="$BUTLER_SUPPRESSION_DIR/archive-restored" BUTLER_POSTGRES_DB=butler_test_restore uv run --locked python ../scripts/pdf-restore-fixtures.py check)
echo "Synthetic restore, interrupted outbox, forgotten memory, work identity registry and audit guard verified"

# Copied ACLs do not let the source database role read the restored namespace.
BUTLER_CI_WORK_COPIED_COUNT=$(docker exec -i "$CONTAINER_ID" psql -U postgres -d butler_test_restore -At -v ON_ERROR_STOP=1 -v storage_role="$BUTLER_CI_WORK_SOURCE_ROLE" <<'SQL'
BEGIN;
SET LOCAL ROLE :"storage_role";
SELECT count(*) FROM work.validation_records;
SELECT count(*) FROM work.read_attempts;
ROLLBACK;
SQL
)
[[ "$BUTLER_CI_WORK_COPIED_COUNT" == $'BEGIN\nSET\n0\n0\nROLLBACK' ]]
# createdb has its own default PUBLIC TEMP permission; DB-level ACL is not table ACL.
# Reapply the reviewed platform baseline before work role provisioning. Synthetic CI only.
(cd backend && BUTLER_POSTGRES_DB=butler_test_restore BUTLER_RUNTIME_PASSWORD=synthetic-runtime-password-only-0123456789 uv run --locked python -m app.runtime_role)
(cd backend && BUTLER_POSTGRES_DB=butler_test_restore uv run --locked python -m app.work_storage --environment test --workspace synthetic-work-restore)
BUTLER_CI_WORK_RESTORE_ROLE=$(docker exec "$CONTAINER_ID" psql -U postgres -d butler_test_restore -Atc "SELECT 'butler_work_' || oid::text || '_88888888888848888888888888888888' FROM pg_database WHERE datname=current_database()")
[[ "$BUTLER_CI_WORK_RESTORE_ROLE" =~ ^butler_work_[0-9]+_88888888888848888888888888888888$ && "$BUTLER_CI_WORK_SOURCE_ROLE" != "$BUTLER_CI_WORK_RESTORE_ROLE" ]]
BUTLER_CI_WORK_RESTORED=$(docker exec -i "$CONTAINER_ID" psql -U postgres -d butler_test_restore -At -v ON_ERROR_STOP=1 -v storage_role="$BUTLER_CI_WORK_RESTORE_ROLE" <<'SQL'
BEGIN;
SET LOCAL ROLE :"storage_role";
SELECT count(*) FROM work.validation_records WHERE id='99999999-9999-4999-8999-999999999999' AND marker='synthetic:restore-marker';
SELECT count(*) FROM work.validation_audit WHERE record_id='99999999-9999-4999-8999-999999999999' AND event_type='validation.created';
SELECT count(*) FROM work.read_attempts WHERE requested_by='22222222-2222-4222-8222-222222222222' AND event_type='validation.read_prepared';
ROLLBACK;
SQL
)
[[ "$BUTLER_CI_WORK_RESTORED" == $'BEGIN\nSET\n1\n1\n1\nROLLBACK' ]]
[[ "$(docker exec "$CONTAINER_ID" psql -U postgres -d butler_test_restore -Atc "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='work' AND c.relname IN ('validation_records','validation_audit','read_attempts') AND c.relrowsecurity AND c.relforcerowsecurity")" == 3 ]]
[[ "$(docker exec "$CONTAINER_ID" psql -U postgres -d butler_test_restore -Atc "SELECT has_schema_privilege('butler_runtime','work','USAGE')")" == f ]]
if docker exec "$CONTAINER_ID" psql -U postgres -d butler_test_restore -v ON_ERROR_STOP=1 -c "UPDATE work.validation_audit SET event_type=event_type" >/dev/null 2>&1; then
  echo "Restored work audit guard did not reject mutation" >&2; exit 1
fi
echo "Work namespace logical restore, forced RLS, copied-role denial and scoped role reprovision verified"

[[ "$(docker exec "$CONTAINER_ID" psql -U postgres -d butler_test_restore -Atc "SELECT count(*) FROM pg_trigger WHERE tgname='work_registry_barrier' AND tgenabled='O' AND NOT tgisinternal")" == 2 ]]
if docker exec "$CONTAINER_ID" psql -U postgres -d butler_test_restore -v ON_ERROR_STOP=1 -c "TRUNCATE work_access_grants" >/dev/null 2>&1; then
  echo "Restored work registry truncate guard failed" >&2; exit 1
fi
echo "Work registry transaction barriers and truncate denial preserved across restore"

if docker exec "$CONTAINER_ID" psql -U postgres -d butler_test_restore -v ON_ERROR_STOP=1 -c "UPDATE work.read_attempts SET event_type=event_type" >/dev/null 2>&1; then
  echo "Restored work read audit guard failed" >&2; exit 1
fi
echo "Scoped work read-attempt audit, source-role denial and immutable restore verified"

BUTLER_CI_DRAFT_SOURCE_OID=$(docker exec "$CONTAINER_ID" psql -U postgres -d butler_test -Atc "SELECT oid FROM pg_database WHERE datname=current_database()")
(cd backend && BUTLER_POSTGRES_DB=butler_test_restore BUTLER_DRAFT_RESTORE_PHASE=check BUTLER_DRAFT_SOURCE_OID="$BUTLER_CI_DRAFT_SOURCE_OID" uv run --locked python ../scripts/work-draft-restore.py)
if docker exec "$CONTAINER_ID" psql -U postgres -d butler_test_restore -v ON_ERROR_STOP=1 -c "UPDATE work.draft_tombstones SET revision=revision" >/dev/null 2>&1; then
  echo "Restored draft tombstone guard failed" >&2; exit 1
fi

(cd backend && BUTLER_POSTGRES_DB=butler_test_restore uv run --locked python ../scripts/work-retention-fixtures.py check)

# Quarantine after scoped-role inspection; never activate this restored database.
(cd backend && BUTLER_POSTGRES_DB=butler_test_restore uv run --locked python ../scripts/recovery-assessment-fixtures.py before)
(cd backend && BUTLER_POSTGRES_DB=butler_test_restore uv run --locked python ../scripts/work-restore-fixtures.py check)

# The manifest was exported from newer real terminal rows after this dump was taken.
(cd backend && BUTLER_POSTGRES_DB=butler_test_restore uv run --locked python ../scripts/work-suppression-fixtures.py reconcile)
(cd backend && BUTLER_POSTGRES_DB=butler_test_restore uv run --locked python ../scripts/recovery-assessment-fixtures.py after_work)

# Separately discard restored unbound/bound pending Work input, preserving live notes.
(cd backend && BUTLER_POSTGRES_DB=butler_test_restore uv run --locked python ../scripts/work-restored-requests-fixtures.py check)

# Explicit selected global no-op approval/job authority, separate from Work queues.
(cd backend && BUTLER_POSTGRES_DB=butler_test_restore uv run --locked python ../scripts/restored-execution-fixtures.py check)
(cd backend && BUTLER_POSTGRES_DB=butler_test_restore uv run --locked python ../scripts/recovery-assessment-fixtures.py after_execution)

# Revoke all remaining restored sessions, including non-Work users, in reviewed batches.
(cd backend && BUTLER_POSTGRES_DB=butler_test_restore uv run --locked python ../scripts/restored-session-fixtures.py check)

(cd backend && BUTLER_POSTGRES_DB=butler_test_restore uv run --locked python ../scripts/recovery-assessment-fixtures.py after_sessions)

(cd backend && BUTLER_POSTGRES_DB=butler_test_restore uv run --locked python ../scripts/restored-credential-fixtures.py)

# Withdraw selected sources on the older target, then prove the new redacted state survives another dump.
(cd backend && BUTLER_POSTGRES_DB=butler_test_restore uv run --locked python ../scripts/work-source-checkpoint-fixtures.py recover)
docker exec "$CONTAINER_ID" pg_dump -U postgres -d butler_test_restore -Fc > "$DUMP"
docker exec "$CONTAINER_ID" createdb -U postgres butler_test_source_preserved
docker exec -i "$CONTAINER_ID" pg_restore -U postgres -d butler_test_source_preserved --exit-on-error < "$DUMP"
(cd backend && BUTLER_POSTGRES_DB=butler_test_source_preserved uv run --locked python ../scripts/work-source-withdrawal-fixtures.py preserved)
