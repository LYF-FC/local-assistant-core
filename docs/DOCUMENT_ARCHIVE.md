# Private local original archive — spec 050

This development/test increment adds an explicit local disk copy of every retained original version of a document. The existing bounded UTF-8 `.txt`/`.md` upload, replacement, review, search, citations and downloads remain unchanged. Database originals remain authoritative during the storage transition. This spec is extended by [spec 051 PDF ingestion](PDF_INGESTION.md); its storage/cleanup contract is retained. OCR, automatic ingestion/filing, moving originals out of PostgreSQL, live Synology, generated answers and production/key/older-backup acceptance remain later work.

## Owner workflow

Open a document and choose **Check archive**. Without configuration it reports that the optional local archive is disabled. With a provisioned root, choose **Archive originals** to copy every retained version. **Check archive** verifies exact bytes against database originals and reports the verified count. Copying the same revision again is idempotent; it neither creates document versions nor attests review. Metadata correction/review and replacement still create versions, so refresh the archive after those changes.

Only the creator may copy or check an archive. Current session, CSRF, HTTPS/Origin, scope, owner and expected document revision are enforced on each phase. Shared viewers can still read current shared originals through normal endpoints; technical administration adds no content privilege. No disk path, root identity, source text or filename enters archive-status responses/audit. Downloaded originals remain verified, authorized DB exports, never arbitrary archive file reads.

## Explicit isolated setup

The base configuration has no archive mount or directory setting. For an isolated synthetic development stack, the optional `infra/core/document-archive.override.yml` adds a dedicated private named volume to the API. Use a fresh reviewed project with separate ports/databases/volumes; never apply this overlay to an existing private deployment.

After building the development image, initialize its empty volume once:

```sh
docker compose -f infra/core/compose.yml -f infra/core/document-archive.override.yml run --rm -T --no-deps api python -m app.document_archive /var/lib/butler-document-archive
```

Then start the same isolated stack using both Compose files. Initialization refuses nonempty directories and never resets an archive identity. For a separately configured local process, provision an empty directory owned by the service user with exact mode 0700, initialize it with `python -m app.document_archive /absolute/private/directory`, then set `BUTLER_DOCUMENT_ARCHIVE_DIRECTORY` to that directory. Use real absolute paths without symlink components. This adapter requires local POSIX file locking, hard links and file/directory fsync; it is not a validated NAS adapter or encryption system. Host disk and backup encryption/key handling remain operator acceptance gates.

## Consistency, bounds and failure semantics

Migration `0023_document_archive` adds immutable document-to-root bindings. Runtime receives SELECT/INSERT only, with trigger seals against update/delete/truncate and binding a forgotten document. Apply privileged role setup after the migration. A copy request first commits its root binding and audit; it then rechecks all current authority/revision in a separate transaction before touching originals. A binding commits a cleanup obligation, not successful storage. Failed copies leave that obligation available for explicit retry. Removing or repointing configuration cannot bypass it.

Storage keys use document UUID and version, never user filenames. Root/objects are owner-private (0700/0600); symlink components, unknown entries, foreign objects, unsafe types/modes and unmanaged hardlinks fail closed. Descriptor-relative IO avoids path traversal. Nonblocking root locks serialize mutation and capacity checks. Each original is at most 128 KiB; a root holds at most 64 MiB of payload and 8192 entries, including temporary/control files. Existing owner/library quotas still apply. Temporary files are fsynced before atomic nonoverwriting publication and directory fsync. A crash after link publication can leave a recognized same-document temporary/object inode pair; the next authorized operation removes only that redundant temporary link. Unknown links are refused.

Status reads/compares exact bytes of all expected versions; it never trusts a filename or stale success flag. Missing versions report partial; corruption, unsafe roots, root mismatch, contention, disk errors and capacity failures produce sanitized unavailability. Corrupt objects are never overwritten automatically. Stop affected activity, retain evidence privately and repair/quarantine the bounded object through a separately reviewed operator procedure before retry. An unavailable response does not promise that no copies were written: the committed binding and idempotent retry handle partial success.

**Forget** purges all matching originals and interrupted temporary files from the correct bound root before the existing DB content/history scrub and audit commit. It remains possible at capacity. If the root is missing, disabled, mismatched or cannot delete a copy, forgetting fails and the DB record remains active for retry. If files are deleted but the SQL transaction fails, DB originals remain available to rebuild the missing copies. No success is returned before audit/state commit. Do not remove the archive setting or volume while bindings still exist; keep the correct root accessible for cleanup.

## Backup, restoration and decommission

`pg_dump` includes originals and bindings but does not include disk archive files. Stop consumers and archive mutations; capture a consistent database dump and a separate private copy of the root, including its marker and permissions. Restore into a new isolated directory preserving the marker/root identity. Quarantine restored sessions/pending intent and follow existing recovery guides before deliberate consumer restart. Check every known archive against authoritative DB versions before use. File presence alone never authorizes ingestion or disclosure.

The synthetic logical restore drill checks a real DB dump and an independently copied archive directory, root identity, all exact version bytes and the existing DB/history/tombstone seals. This does not certify independent clean-host/key/latest-source completeness. Older DB backups can predate bindings/forgetting; unknown or older archive objects are not auto-imported or auto-deleted. Latest suppression/retention reconciliation and encrypted archive/key recovery remain separate gates.

Bindings are intentionally retained as minimal cleanup metadata after forgetting. Before any real downgrade, decommission the archive with separately reviewed backups and cleanup: downgrade removes the binding table and therefore loses its cleanup obligations. Never downgrade an existing private installation to test this feature. No production activation, NAS account/share, private data migration or outbound service is enabled.

## Verification

Spec 050 covers adapter fault tests, API privacy/transactions, actual restricted PostgreSQL role/seal/row-wait tests, migrations, separate archive restoration, base-disabled and opt-in trusted-HTTPS browser workflows. Final exact-head CI evidence is recorded in the PR. A verified local copy is a point-in-time result, not whole-MVP or real-host acceptance.
