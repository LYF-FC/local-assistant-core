# 069 — Invoice filing execution against a synthetic destination

Second item of the agreed synthetic-MVP order (invoice filing and job recovery). An approved logical filing plan ([spec 057](../057-invoice-filing-plans/spec.md)) can be **executed** against a **synthetic destination** only after a separate, exact owner request. The destination is an in-process double: no filesystem, folder, share, network, mailbox, calendar or connector is touched. It proves the claim / effect / reconcile semantics a real local or Synology adapter spike must later confirm. Plan approval keeps `execution_authorized:false`; this spec never changes that field.

## Guarantees (what is and is not promised)

Stated precisely, because "exactly once" is not achievable unconditionally:

1. **One claimant at a time.** The claim is a committed transition made under the owner, source, review and filing-row locks. Two workers cannot both hold a claim; the loser observes the committed claim and skips.
2. **No blind re-application.** The claim commits *before* the effect. If the process dies, the effect times out or raises, or a claim is older than five minutes, the filing becomes `unknown` and is resolved only by lookup keyed by the filing ID. Found → `filed` (event `reconciled`). Absent → one bounded retry. Lookup unavailable → stays `unknown`, polling slowly. A retry therefore never follows an unresolved outcome.
3. **Conditional on the destination.** (2) holds only for a destination that honours the key on write and answers lookup by key. A destination that cannot is documented as *at-most-once with a visible unknown state*, never exactly-once. The in-process double is not durable: across a real worker restart its ledger is empty, so a lookup would answer "absent". Restart behaviour is therefore **not** proven by this spec.
4. **No overwrite.** A path already owned by another key is a refusal (`collision`, terminal `failed`), never a replacement. Collision is decided on the canonical path (below), so case or Unicode variants collide.
5. **An effect applied before forgetting cannot be recalled.** Only the records about it are scrubbed.
6. **Late results never touch a newer revision.** An attempt, and a lookup of an unknown filing, each own the revision their own claim produced and apply their result only to that exact revision (a locking read `WHERE revision = fence`; every transition increments the revision and the seal trigger enforces `revision + 1`). A stale worker or reconciler is skipped with no change to the row or history, and its truthful result is discarded in favour of the newer attempt or the next lookup. This holds regardless of destination idempotency and removes the false `failed` that a stalled first worker could otherwise cause after attempt three.

## Authorization

The owner's filing request is the separate, exact-action authorization that plan approval never grants.

- **Bound** to one owner, one scope, one document, one source revision and one approved plan revision (`UNIQUE(document_id, plan_revision)`). Checked in the API, by the insert trigger, and again under lock at every claim.
- **Cannot authorize a newer revision.** Re-reviewing, re-planning or withdrawing changes the revision; the old authorization cancels itself with `plan_changed` and never files the new plan. The new plan needs its own request, which is a new row.
- **Single use / not replayable.** There is one execution per (document, plan revision). A repeated request returns the existing record with `replayed:true` and creates nothing; a cancelled authorization stays cancelled.
- **Atomically consumed at claiming.** `authorization_consumed_at` is set by the *same update* that records the first attempt (`attempts` 0→1), enforced by a table check and the seal trigger; it can then be neither cleared nor moved. A request cancelled before any claim stays unconsumed. Later recovery attempts of the same execution run under that already-consumed authorization, and only after lookup has shown the earlier one absent.
- `filing_plan.execution_authorized` stays `false` on the plan throughout.

## Destination identity (`destination-v1`)

`destination_key = SHA-256("<scope>:<canonical path>")`, hex, never the readable path.

Canonicalization, in order: NFC Unicode normalization; reject absolute paths, `\`, `:` (drive or stream), control characters, `.`/`..` segments, empty or over 384 characters; collapse duplicate `/`; drop trailing `/`; compare **case-insensitively** (lower-cased), the safe assumption for a shared or removable volume. Spec 057 already restricts plan paths to lower-case ASCII; the policy is the second, defensive layer and the single place that defines when two paths collide. PostgreSQL recomputes the key with `lower(rtrim(regexp_replace(normalize(path,NFC),'/+','/','g'),'/'))`; a mismatch fails closed (the insert is refused). For non-ASCII paths `lower()` follows the database locale, a documented gap.

The key is a **uniqueness and reconciliation handle, not a security boundary.** Authority comes only from owner, scope and the exact plan revision. A partial unique index `(scope, destination_key)` over `pending|unknown|filed` stops two active filings from reserving one destination; `failed` and `cancelled` release it. A concurrent loser is refused by that index and receives 409.

## Forgetting is a lifecycle operation

Forgetting a document runs `scrub_for_document` in the same transaction:

- unfinished (`pending`/`unknown`) filings are cancelled (`source_changed`); every filing gets an explicit `scrubbed` event and a one-time `scrubbed_at` marker;
- `destination_key` is removed from the current record;
- every historical snapshot of the execution is set to SQL NULL (the same pattern as invoice revisions); the `scrubbed` event itself carries no snapshot;
- the API no longer reports `document_id`, plan or source revision for a scrubbed filing (`scrubbed:true`).

History stays append-only: no row is deleted or rewritten, except that the trigger permits exactly one change to an event, snapshot → NULL, only while the source is forgotten, and the runtime role holds `UPDATE (snapshot)` only. Scrubbing is idempotent (a scrubbed execution is never touched again, no new event). Lock order is owner → source → review → filing row in the worker, in forgetting and in the claim, so scrubbing cannot deadlock a claiming worker; a worker holding an in-flight claim finds the row terminal and records nothing. After forgetting, no request is accepted (the source is no longer active) and no worker path can recreate a key, snapshot or link.

The `document_id` foreign key remains on the current row, pointing at the document tombstone, for referential integrity and replay protection. It is not exposed by the API.

## Other rules

- States `pending`, `filed`, `failed`, `unknown`, `cancelled`; terminal states cannot be revived. Only work that has not started can be cancelled by the owner.
- Bounded retry reused from spec 068: three attempts, backoff 1/5/15 minutes, reconcile interval one minute.
- Sealed metadata history and a system audit event per change; no invoice field, filename, path or source text enters history or audit. Owner-only `POST /api/v1/filing/request|cancel|query|history`.
- Restricted worker `python -m app.filing_worker --once|--loop`: development/test with restricted runtime credentials, bounded passes of at most 100, synthetic destination only, not started by default.
- Migration 0034 (after 0033, spec 068 corrections). **Its downgrade is destructive by design:** it drops both filing tables and both seal functions, deleting every execution and its sealed history, including the consumed-request evidence; `audit_events` metadata remains and nothing is recalled from a destination. After a re-upgrade the same approved plan revision can be requested again, and only the destination's no-overwrite rule then stands against a second write. It does not refuse a downgrade when rows exist (a separate design decision, not authorized). Back up first, stop the worker and roll forward; downgrade is not a production rollback strategy.

## Out of scope

A real filesystem or Synology adapter, copying original bytes, email intake, any connector, durable synthetic ledger across restarts, a web screen for filing, standing auto-filing rules. DOC-03 and MVP-03 stay partial.
