# Synthetic invoice filing execution — spec 069

An invoice [filing plan](INVOICE_FILING_PLANS.md) you approved can be carried out against a **synthetic destination**. This is development/test engineering that proves the safety rules before any real folder or NAS exists. Nothing is written to a disk, share or network. Approving a plan never starts anything: it still says `execution_authorized: false`. You start a filing with a separate request that names the exact document, source version and approved plan version.

## What you can rely on

- **One claim at a time.** Two workers cannot both start the same filing.
- **No blind repeat.** The attempt is recorded before the write. If the process stops, the write times out or the claim goes stale, the filing becomes `unknown` and is settled by looking the filing up at the destination. Found means filed; absent allows one bounded retry; if the destination cannot be asked, it stays `unknown`.
- **Conditional.** This holds for a destination that accepts the filing key and can be asked about it. If a real destination cannot, the honest result is "at most once, with a visible unknown", not "exactly once". The in-process destination used by the unit tests forgets everything when the worker restarts; process-restart evidence uses a separate durable synthetic destination (see below).
- **Late results are discarded.** Every attempt, and every lookup of an unknown filing, owns the record revision its own claim produced. Its result is applied only if the record still carries exactly that revision; the comparison is part of the locking database read. A worker or reconciler that stalled, was reaped, reconciled, replaced by a newer attempt or cancelled finds a different revision and is skipped without changing the record or appending history. Its result is thrown away even if truthful: the newer attempt, or the next lookup, settles the filing. This is what stops a stalled worker returning late from marking a newer attempt filed, retried, unknown or failed (including a false `failed` after the third attempt while the file already exists).
- **Outcomes follow a claim.** The database refuses to mark a filing `filed`, `failed` or `unknown` unless an attempt was actually claimed first, so a never-started filing cannot be recorded as done.
- **Crash recovery is not restart recovery.** Job state lives in PostgreSQL and is the same from any fresh connection. The destination effect is a different thing: it lives in the destination. The tests stop a worker before the effect, during it, and after it but before the outcome is recorded, then recover from new database connections by lookup. They keep the same in-process destination object alive, which models a worker that died while the destination survived. Those tests alone do not prove restart recovery: after a real application restart an in-memory destination starts empty and a lookup would say "absent". The restore test proves only that the filing records and their history survive a dump and restore.
- **Process-restart evidence (synthetic destination only).** `integration/test_filing_restart_postgres.py` runs the real `filing_worker.process` in separate operating-system processes (harness: `tests/restart_support.py`, `tests/restart_worker.py`) against PostgreSQL and a directory-backed synthetic destination that survives the processes. A worker is killed with SIGKILL at a controlled point (before the effect, or after the effect but before the outcome is recorded) and a distinct fresh process recovers from the same rows and destination: before the effect it is reaped to `unknown`, a conclusive "absent" lookup allows one retry, and the effect is applied once; after the effect it is reconciled from the destination without a second write. An inconclusive lookup stays `unknown` with no retry and no false failure until a later lookup resolves it. Two competing or simultaneous workers produce one effect, a stalled worker that resumes after recovery is discarded by the revision fence, an existing destination object is never overwritten after a restart, and a cancelled request has no effect in any process. This proves recovery of the worker and its durable state against a synthetic destination. It does not prove a real destination, a live inbox, real authorization or cross-store reconciliation, and it is not verification or acceptance of MVP-03.
- **Never overwrites.** An existing file is a refusal (`collision`), including a path that differs only by letter case, repeated slashes, a trailing slash or Unicode composition.
- **Your request is used once.** It is tied to your account, the scope, the exact plan version and source version. It is consumed by the first attempt. A changed, re-reviewed or withdrawn plan cancels it (`plan_changed`); the new plan needs a new request. Repeating a request returns the existing one.

## States

`pending` (waiting or in progress) · `unknown` (outcome not known; looked up, never repeated) · `filed` · `failed` (collision, rejected after three attempts) · `cancelled` (you cancelled before it started, the plan or source changed, owner inactive or scope removed). `filed`, `failed` and `cancelled` are final. You can cancel only a filing that has not started.

## Destination names

Two destinations are the same if they match after: Unicode normalisation (NFC), collapsing repeated `/`, dropping a trailing `/` and ignoring letter case. Absolute paths, backslashes, colons, control characters and `.`/`..` are refused. The stored key is a hash of the scope and that canonical name, used to prevent two active filings reserving the same place; it is **not** a security control. Only one active (`pending`, `unknown` or `filed`) filing may hold a destination in a scope.

## Forgetting

Forgetting a document cancels its unfinished filings, removes the destination key, clears the stored history snapshots (an explicit `scrubbed` entry remains, so the history is still append-only) and stops the API from reporting the document or plan version. It is safe to repeat and safe while a worker is running. A write that already happened at the destination before you forgot cannot be taken back; only the records are removed. A reference to the forgotten document's tombstone remains inside the database row for integrity and is never returned.

## Schema rollback — migration 0034 is destructive

Downgrading `0034_invoice_filing_execution` permanently deletes `filing_executions`, `filing_execution_events` and both seal functions, with every filing record and its sealed history. That includes the evidence that a request was consumed and the record of what was filed. The `filing.*` metadata entries in the audit log remain. Nothing is undone at the destination: a file already written stays there.

After a downgrade and re-upgrade the same approved plan revision can be requested again and starts as a new, unconsumed request. Only the destination's own no-overwrite rule then prevents a second write; the filing would fail with `collision` because the existing file belongs to the earlier filing. This is deliberate: the migration does not refuse a downgrade when rows exist. Schema downgrades are test tooling, not a production rollback strategy. Take a protected backup first, stop the worker, and prefer rolling forward with a repair migration. A restored older backup does not recreate consumed-request evidence newer than the backup.

## Using it

`POST /api/v1/filing/request` (document, expected document and review revisions, two explicit acknowledgements), `/cancel`, `/query` (state filter, cursor, 25 per page) and `/history`. Owner-only, audited, metadata only: no path, file name or invoice field appears in any response, history or audit. No web screen is added.

## Running the worker (development/test only)

`python -m app.filing_worker --once` (or `--loop`) with restricted runtime credentials, in development or a disposable test database. Bounded to 100 per pass, synthetic destination only, not started by default. Keep it stopped across schema updates and after restoring an older backup until pending requests are reviewed.

## Known limits

See the [spec](../specs/069-invoice-filing-execution/spec.md). Limits: effect survival across a process restart is evidenced only for the synthetic directory-backed destination, not for a real one; there is no real adapter; the original bytes are not copied (the destination entry records only the source checksum and size, and the email lineage resolves through the filing's document, not through the destination); there is no screen; non-ASCII case folding follows the database locale; a poison row is retried each pass; a lookup that answers "absent" just before a stalled write lands is inherent to any destination, so a real adapter needs a hard write timeout below the five-minute in-flight deadline.

## Evidence in tests

Synthetic only. `test_mvp03_journey_postgres.py` forwards one offline email twice (one document, one envelope), extracts, reviews, plans, approves, requests and runs the worker to a filed destination entry whose checksum and size are those of the email attachment, and shows the lineage email, document, filing and destination entry; it also covers a crash before the effect, during it, and after it before recording, an unknown outcome kept visible while lookup is unavailable, and a collision. `test_filing_fence_postgres.py` covers late workers and reconcilers. `test_filing_downgrade_postgres.py` covers the rollback above. These do not complete MVP-03 (see [acceptance](MVP_ACCEPTANCE.md)).
