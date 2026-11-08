# Spec 003 — durable jobs and transactional outbox

Status: development/test increment for issue #4. No provider or workflow deployment.

## Outcomes and boundaries

An authenticated requester turns their approved validation.noop record into one durable job. Job, outbox delivery, approval consumption and audit commit together. A private deterministic worker recovers from a crash without losing work or allowing a stale lease holder to complete it. No internet access, LLM, family data or external actions are needed. Windmill remains the future deterministic workflow orchestrator; this is Butler's domain queue contract, not a replacement scheduler.

## Requirements

- FR-01: same-requester idempotency key replays return the same job; changed approval with the same key conflicts. Keys are bounded and stored hashed. Concurrent enqueue cannot create duplicate work.
- FR-02: enqueue uses current identity/scope/CSRF, requester ownership, payload/policy binding and expiry from spec 001. Previously consumed approvals cannot authorize a new job.
- FR-03: job and single outbox delivery are inserted with consumed approval and audit in one transaction. Any failure rolls all back.
- FR-04: PostgreSQL SKIP LOCKED claims are atomic, leases have random fenced tokens and expiry, attempts are bounded, and expired leases can be recovered. Every transition is audited without payload duplication.
- FR-05: only the registered validation.noop handler runs. It writes a synthetic result to local structured state in the completion transaction. No dynamic imports, arbitrary commands, provider calls or AI dependency.
- FR-06: revalidate requester/approver active membership, policy, binding and expiry before execution. Revocation or expiry dead-letters without action. Stale/expired workers cannot finish or retry a newer lease.
- FR-07: failures use fixed safe error codes, bounded exponential retry and dead-letter state. Exhausted jobs remain inspectable; requester-authorized review acknowledgement does not silently retry or renew expired approval.
- FR-08: external write outcomes are outside this handler registry. Future external adapters MUST distinguish safe retry from ambiguous write, enter reconciliation, and forbid blind redelivery. This increment does not claim provider exactly-once effects or complete issue #4.
- FR-09: authenticated read is scope-filtered and audited. Worker is one-shot, private development/test CLI using restricted credentials; no public worker endpoints or live schedule.
- FR-10: migration round-trip, restricted-role grants, distinct-worker concurrency, duplicate enqueue, crash recovery, fencing, audit/commit failure and restore must have synthetic evidence.

## Data and recovery

New durable_jobs and job_outbox tables reference the approval and requester. Payload remains in its scope-bound approval; the queue carries IDs, hashes, state, timestamps and bounded diagnostic codes. Backup includes both tables and audit. Restore leaves execution disabled until sessions revoked and pending/leased work reconciled. No data leaves the private environment.
