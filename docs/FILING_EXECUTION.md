# Synthetic invoice filing execution — spec 069 candidate

An invoice [filing plan](INVOICE_FILING_PLANS.md) you approved can be carried out against a **synthetic destination**. This is development/test engineering that proves the safety rules before any real folder or NAS exists. Nothing is written to a disk, share or network. Approving a plan never starts anything: it still says `execution_authorized: false`. You start a filing with a separate request that names the exact document, source version and approved plan version.

## What you can rely on

- **One claim at a time.** Two workers cannot both start the same filing.
- **No blind repeat.** The attempt is recorded before the write. If the process stops, the write times out or the claim goes stale, the filing becomes `unknown` and is settled by looking the filing up at the destination. Found means filed; absent allows one bounded retry; if the destination cannot be asked, it stays `unknown`.
- **Conditional.** This holds for a destination that accepts the filing key and can be asked about it. If a real destination cannot, the honest result is "at most once, with a visible unknown", not "exactly once". The in-process destination used here forgets everything when the worker restarts, so restarts are not yet proven.
- **Never overwrites.** An existing file is a refusal (`collision`), including a path that differs only by letter case, repeated slashes, a trailing slash or Unicode composition.
- **Your request is used once.** It is tied to your account, the scope, the exact plan version and source version. It is consumed by the first attempt. A changed, re-reviewed or withdrawn plan cancels it (`plan_changed`); the new plan needs a new request. Repeating a request returns the existing one.

## States

`pending` (waiting or in progress) · `unknown` (outcome not known; looked up, never repeated) · `filed` · `failed` (collision, rejected after three attempts) · `cancelled` (you cancelled before it started, the plan or source changed, owner inactive or scope removed). `filed`, `failed` and `cancelled` are final. You can cancel only a filing that has not started.

## Destination names

Two destinations are the same if they match after: Unicode normalisation (NFC), collapsing repeated `/`, dropping a trailing `/` and ignoring letter case. Absolute paths, backslashes, colons, control characters and `.`/`..` are refused. The stored key is a hash of the scope and that canonical name, used to prevent two active filings reserving the same place; it is **not** a security control. Only one active (`pending`, `unknown` or `filed`) filing may hold a destination in a scope.

## Forgetting

Forgetting a document cancels its unfinished filings, removes the destination key, clears the stored history snapshots (an explicit `scrubbed` entry remains, so the history is still append-only) and stops the API from reporting the document or plan version. It is safe to repeat and safe while a worker is running. A write that already happened at the destination before you forgot cannot be taken back; only the records are removed. A reference to the forgotten document's tombstone remains inside the database row for integrity and is never returned.

## Using it

`POST /api/v1/filing/request` (document, expected document and review revisions, two explicit acknowledgements), `/cancel`, `/query` (state filter, cursor, 25 per page) and `/history`. Owner-only, audited, metadata only: no path, file name or invoice field appears in any response, history or audit. No web screen is added.

## Running the worker (development/test only)

`python -m app.filing_worker --once` (or `--loop`) with restricted runtime credentials, in development or a disposable test database. Bounded to 100 per pass, synthetic destination only, not started by default. Keep it stopped across schema updates and after restoring an older backup until pending requests are reviewed.

## Known limits

See the limitations checklist on the delivering pull request and the [spec](../specs/069-invoice-filing-execution/spec.md): non-durable synthetic destination, no real adapter, no original-byte copy, no screen, non-ASCII case folding follows the database locale, and a poison row is retried each pass.
