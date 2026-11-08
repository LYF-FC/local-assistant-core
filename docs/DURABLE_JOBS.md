# Durable jobs — development/test contract

Spec: [003](../specs/003-durable-jobs/spec.md). Issue: #4 (historical private reference omitted). Only validation.noop is supported. No providers, household actions, financial execution, model calls, recurring scheduler or live Windmill workflow are activated.

## Request path

Create and approve a bounded record through the approval API. POST /api/v1/jobs with approval_id, payload_hash, policy_version and a 16–128 character idempotency_key (letters/digits/underscore/hyphen), using the existing HTTPS session, exact Origin and CSRF header. The requester must own the approval and still hold its scope. Approval consumption, job, single outbox record and audit commit together. Failure leaves none of these partially committed.

A repeated requester/key/binding returns the original job. A key reused for a different approval or binding conflicts. The key is stored hashed. A separately consumed approval cannot enqueue work. GET /api/v1/jobs/{id} filters in SQL by current scope and audits access; private and missing IDs return identical 404. Raw payload stays in the bound approval, not the queue or audit.

## Worker and recovery

A private one-shot worker claims one due record with PostgreSQL FOR UPDATE SKIP LOCKED. Claim audit and a random hashed lease token commit before execution. A later transaction validates the lease and current approval/requester/approver authority before recording a local no-op result and audit. Approval expiry applies to execution, not just enqueue. No dynamic handlers or commands are loaded.

Default lease: 60 seconds. Maximum: three claims, including recovery after worker death. Safe transient failures schedule retries after 10 and 20 seconds. Exhaustion or invalid authority dead-letters. Expired leases are reclaimable; old tokens cannot finish or reschedule a newer lease. Worker clocks must be synchronized. This fences database transitions; it is not a guarantee about future external side effects.

POST /api/v1/jobs/{id}/review lets the current requester acknowledge a dead letter under CSRF. It audits review, without re-executing work or extending authorization. Creating fresh authority requires a new approval and key. No broad list/export, operator dashboard or automatic replay is implemented.

From an already configured synthetic development environment, a trusted operator may run one pass:

```sh
docker compose --env-file .env -f infra/core/compose.yml run --rm api python -m app.worker
```

This uses the restricted API role. No worker daemon or schedule is installed. CLI refuses production/staging and owner credentials. Database/audit failure aborts the transaction; a committed lease remains for bounded recovery. Inspect structured job state and audit through the trusted administration path; keep raw database errors out of shared logs.

## Recovery and remaining integration work

Back up jobs, outbox, approvals and audit together. Synthetic CI restores a leased delivery and verifies its state plus restored audit guards. After a real restore keep dispatch disabled, revoke sessions, synchronize clocks, inspect pending/leased/terminal records and compare external receipts before re-enabling any future adapters. Do not blindly replay restored work.

Butler owns domain state and authorization. Windmill remains the deterministic workflow orchestrator; its adapter and workflow deployment are not implemented. Future external writes need provider idempotency keys/receipts, ambiguous-write reconciliation, scoped credentials, observability and recovery acceptance. Such adapters must not use this local no-op retry path indiscriminately. Model outage has no effect on this queue, but daily reminders are not delivered by this increment.


## Selected restored no-op authority — spec 036

After isolated restore and before restarting consumers, the candidate [reviewed execution quarantine](RESTORED_EXECUTION_QUARANTINE.md) cancels selected outstanding no-op approvals and dead-letters selected queued/leased no-op jobs, clearing leases and rejecting old-token completion. Explicit target/scope/IDs, clean owner, current exact review and fail-fast table locks are required. Payloads, consumed approvals and completed/unselected history remain unchanged. No schema/grant change or automatic activation. This proves only selected coverage; full inventory, restored sessions/Work/credentials/keys, future external receipts and full-host acceptance remain separate gates.
