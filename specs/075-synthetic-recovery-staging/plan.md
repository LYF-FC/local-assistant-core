# Spec 075 first-slice plan

## Constitution and dependency review

The bounded synthetic-only slice preserves local data control, explicit test scope, deterministic verification, audit-safe outcomes and portable PostgreSQL. No migration/permission/configuration change is planned. Its database writes are confined to disposable restore targets already selected by the existing drill guards. Spec 074 remains the immutable verification contract; do not add a restore mode or output fields to its CLI for this slice. Existing Work reconciliation does not satisfy DOC-X02 for other domains.

## Implementation sequence

1. Specify/clarify: [spec.md](spec.md) records exact staged-byte and restored singleton binding requirements, scope exclusions and non-Work release refusal.
2. Plan/checklist/tasks/analyze: review the unchanged verifier, protected path helpers, current drill and installation singleton schema; resolve stream interface with implementation owner before wiring restore.
3. Implement a bounded internal staging/snapshot/binding helper. Copy and verify a dump-only private stage (16 MiB maximum), digest-check the bounded protected read into immutable bytes, then clean the private stage before returning. `StagingExpectations` requires environment `disposable-synthetic`, installation/schema, key path/fingerprint and expected manifest hash; `VerifiedDump.consume(callback)` passes precisely the verified immutable bytes. No general operations CLI or secret generator.
4. Add unit negative/positive cases, then disposable PostgreSQL mismatch fixtures. A dedicated dump-only subdrill supplies the callback bytes directly to `pg_restore` standard input; the original full-archive drill retains its previous scope and gap unless separately changed. Binding helper `inspect_restored_binding(connection, *, installation_id, schema_head)` checks actual singleton rows, with quarantine/ineligibility fixed on every outcome.
5. Validate with locked dependencies, repository checks and actual disposable PostgreSQL/drill evidence. Record actual revision/results in convergence; missing infrastructure or failures remain explicit.
6. Converge the agreed synthetic engineering slice only. Reconcile authoritative narrative/register pointers without changing acceptance/task/gate statuses or generated counts. Root integration owns commits/PR/CI coordination; no automatic merge.

## Interface decisions

- Internal Python callable/helpers plus existing test drill; function names and safe reason codes follow actual reviewed implementation and are recorded in analysis/convergence after integration.
- Expected manifest hash is explicit for this slice. It establishes equality to a synthetic fixture anchor, never freshness governance.
- Digest/count validation of an immutable snapshot plus exact callback-byte delivery is required; a path-only immediate reverify is insufficient. A failed restore leaves a quarantined target, never a bound success. Consumer code is reviewed/tested to supply exactly the callback bytes; the helper is not a sandbox against arbitrary callbacks.
- Exactly one row in `public.installation_config` with `id=1`; exactly one head in `public.alembic_version`; no mutation/restamping to force success.
- All result paths retain an explicit release/use refusal until future non-Work forgetting reconciliation. This is a hold, not its implementation or acceptance.

## Verification strategy and limits

Map tests to R1–R10 and A1–A7. Unit tests establish helper control flow and failure states; actual isolated PostgreSQL tests establish what restored DB queries and `pg_restore` do. Existing full drill exercises synthetic application fixtures, not clean-host recovery. Run focused tests before full repository checks; report exact commands/results only after observation. No C4 tier, timing campaign, production/NAS/real-key access or manual ceremony is part of validation.
