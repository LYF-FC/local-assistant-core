# Work transaction authority — development/test metadata

Spec 014, merged through #36, closes concurrent revocation races in the existing Work Companion workspace list/status. It continues merged #34/#35 without adding a work storage credential, connection, content endpoint, model or debrief capture. The storage/schema probes remain quarantined; all five work-content gates stay pending.

## Current authority and lock ordering

A request derives the user only from the current hashed cookie session. It acquires a shared PostgreSQL **transaction** advisory registry barrier, read-locks the current active user using existing user-row lock privileges, then locks/revalidates the current session. The work path explicitly refreshes a locked session even if its ORM object was loaded before a wait, so a cached pre-wait session cannot hide committed revocation. Existing family identity callers retain their current default behavior. Active workspace and explicit current work_private grant filtering remains in SQL.

The barrier protects both workspace identity and grants through the content-free identity audit and commit. Migration 0008 adds exclusive BEFORE STATEMENT triggers for INSERT/UPDATE/DELETE on both registry tables, including direct privileged SQL writes. TRUNCATE is rejected outright to avoid lock-order inversion after PostgreSQL's table-wide lock. The trigger function uses fixed pg_catalog search_path and has no PUBLIC EXECUTE grant. API registry permissions remain SELECT-only; no work schema/role grant is added.

Supported ordering:

1. Work request: shared registry barrier → user read lock → session lock → registry SELECT → post-SQL clock check → minimal audit/commit → response.
2. Trusted work administration: exclusive registry barrier before any workspace/user/session row locks or mutation. The existing work CLI now does this explicitly; statement triggers defend direct registry DML too.
3. Existing identity disable/password/revoke administration locks user before session and does not acquire a work registry lock. No normal identity path is changed.

Reader-first: revocation waits until that bounded metadata transaction's audit commits. Writer-first: a new reader waits, then sees committed revocation/disablement and releases no workspace metadata. The shared barrier allows parallel readers; rare metadata writes serialize. It is deliberately one small registry boundary, not a lock for long work jobs.

Mixed privileged transactions must take the registry barrier before user/session row locks. Arbitrary owner SQL combining other lock orders can deadlock and must retry; a timeout/abort never releases a protected response. Host/database owners remain privileged and can alter DDL.

## Clock, isolation and failure handling

Current session absolute/idle expiry is checked again after SQL waits, before session touch and audit. User/session disablement or revocation is observed under current locks. PostgreSQL READ COMMITTED isolation is required and checked: an old repeatable-read snapshot cannot survive the registry wait and then authorize from stale grants.

Registry helpers set transaction-local 2-second lock and 5-second statement wait budgets; local settings reset when the transaction ends. SQLite unit tests skip only PostgreSQL lock primitives; actual role/concurrency behavior is verified in hosted PG tests. Lock/unavailability, audit or commit failure rolls back and returns a sanitized 503 with no workspace payload. Audit persistence is required for successful/ordinary denied reads; infrastructure failures cannot guarantee an audit write and fail closed.

## Snapshot contract and UI

List/status results include `authority_mode: transaction_snapshot` and ISO `checked_at`, never a reusable permission or storage token. The work view displays the latest check time and offers **Recheck current access**. Recheck/refresh/denial/view change/sign-out clear or discard previous status and abort stale requests.

An internal WorkAuthority handle is valid only in its originating active transaction. It cannot be reused after commit/rollback, serialized as a client capability, stored in a job/cache or treated as permission for later work content. A response is an authorized committed snapshot; a later revocation can commit after this transaction ends. There is no retroactive erasure of already-observed metadata.

## Evidence and operational scope

Separate-connection restricted-role PostgreSQL tests cover raw-SQL and trusted-helper revocation with reader-first and writer-first ordering, observed advisory lock waits, expiry/disabled user/revoked session during waits, bounded HTTP timeout/unavailability and repeatable-read rejection. Existing registry write-denial, family/work isolation, user/session, audit failure, storage RLS and actual browser cancellation checks remain. Migration round trip/restore verifies both active barrier triggers and rejected registry truncation, alongside private work role/restore guards.

After merge/green main, use the existing [HTTPS main update/rebuild](WORK_ACCESS_FOUNDATION.md#update-an-existing-m2-checkout-over-https). Migration 0008 adds triggers only; existing users/volumes/.env and NOLOGIN storage roles are preserved. Work Companion gains a timestamp/recheck control; no new user provisioning, role grant or credential is needed. Keep a migration-bearing preview branch until main contains that migration.

## Remaining before work content

A separate credential/connection broker must bind the authorized actor/workspace to a correctly scoped storage connection, independently validate the current state for each bounded content transaction and provide work-scoped read/deny audit. This increment adds no such connection or general work-content audit. Domain lifecycle, retention/forget/export/keys, retrieval/context/cache/jobs and isolated full-host recovery still precede a synthetic debrief pilot and any real employer access. Never hold the authority transaction/barrier across models, external I/O, tools or a long job; later execution must re-authorize.

Technical references: [PostgreSQL 17 explicit locking](https://www.postgresql.org/docs/17/explicit-locking.html), [transaction advisory functions](https://www.postgresql.org/docs/17/functions-admin.html#FUNCTIONS-ADVISORY-LOCKS).

## Next scoped connection boundary

Spec 015 candidate validates current authority against a fixed synthetic storage read adapter and private prepared/denied audit. No normal-runtime mapping or login is configured. See [WORK_READ_BROKER](WORK_READ_BROKER.md) for target/role checks and independent work/identity commit semantics.
