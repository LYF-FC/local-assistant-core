# Bounded local PDF ingestion — spec 051

The [spec 052 OCR extension](PDF_OCR.md) adds explicit two-page OCR to this lifecycle; native text extraction remains the default. Its uncertain recognition and tighter limits do not change the contracts below.

This increment extends specs 048/050 with PDF originals and local text extraction. The same permissions, archive, immutable history, audit, quota, export and forgetting contracts apply. It replaces only the text/Markdown-only intake restriction. OCR, uncertain structured fields, email intake, live NAS, generated answers and complete key/older-backup recovery remain open.

## Workflow and limits

Upload a `.pdf` original through Documents. Originals remain exact bytes in PostgreSQL and may be copied by the existing optional archive. A random owner-scoped upload key binds the exact request; retrying an uncertain response with the same draft cannot create duplicates. Changing a committed payload conflicts. Reopening a deliberate new draft creates a new identity; content-level duplicate detection remains future work.

The optional parser reports **ready**, **no text**, **encrypted**, **invalid**, **resource limit** or **unavailable**. Failures retain the original for authorized download and explicit re-extraction; none is silently truncated or eligible for review/citations. Image-only pages require future OCR. A ready extraction may omit images or reading order; mixed empty pages are identified. Compare against the original before checking the review attestation. Replacing or re-extracting creates an unreviewed version and clears the previous citation view.

Limits remain 128 KiB per original, 32,000 extracted characters, 64 active/128 lifetime documents, 50 versions each and 8 MiB retained original plus UTF-8 text per creator. PDF extraction adds 12 pages, 128 KiB native stdout, 8 KiB diagnostic output, 8 seconds per native command, 3 CPU seconds, 256 MiB address space and 32 descriptors. Extraction uses separate metadata/text commands. Requests are serial per worker; client IO is bounded by a 20-second socket timeout. The service container additionally limits memory, processes and CPU.

Raw original SHA-256, derived UTF-8 text SHA-256, engine/build version and page-to-line spans are distinct. The build version includes the Poppler upstream version and a hash of installed package versions, guard binary, worker source and Python version. Reviewed literal citations preserve document ID, revision, raw and derived hashes and intersecting page spans. These are source excerpts, not generated answers or independent verification.

## Optional synthetic setup and isolation

Base configuration leaves extraction unavailable. For a **new isolated synthetic stack**, add `infra/core/pdf-ingestion.override.yml` to the base Compose files; optionally include the archive overlay and its one-time empty-root initialization. Never apply these test overlays to an existing private installation. The API receives a read-only private socket volume at `/run/butler-pdf`; the worker owns its read/write side under UID 10001. Native extraction requires Linux seccomp/libseccomp and fails closed if confinement cannot start.

The parser container has no network, database credentials, archive mount or Docker socket. Its root filesystem is read-only and capabilities are dropped. Originals stream through pipes and are not written to disk. The parent is non-dumpable; each native child has default-deny syscall filtering, read-only opens, denied socket/process/file mutation operations, resource limits, bounded output and a wall deadline. Parser diagnostics and source text are never logged or returned as error details. The API validates bounded framed replies and rechecks current authorization after extraction before committing/releasing data. Nothing leaves the selected local environment.

## Persistence, failure and recovery

Migration `0024_pdf_ingestion` adds extraction metadata and owner-scoped request identity. PostgreSQL seals enforce raw/derived snapshot agreement, immutable request bindings and review reset. Forgetting scrubs originals, derived text, extraction metadata and payload hashes across managed history; only the ordinary tombstone and random operation identity remain. Archive-bound documents still require their correct root for cleanup. Earlier backups/downloads remain unmanaged copies.

A lost worker or rejected response produces unavailable extraction with retained source. Repair the worker and choose **Re-extract PDF text**; this consumes a version and requires review again. No automatic retry/import is authorized by file presence. Preserve the parser build/package inventory with recovery material. The synthetic logical restore checks PDF bytes, derived hashes, page provenance, immutable versions, idempotency tombstones and a separately restored archive directory. Independent clean-host/key/latest-backup acceptance remains outstanding.

Downgrade refuses while PDF content, retained PDF snapshots or extraction-operation history exists. Forgetting scrubs content but retains immutable extraction operation evidence; those databases must retain migration 0024. Only a synthetic database with no retained PDF provenance/operation evidence can downgrade. Never remove metadata/history to bypass this guard or downgrade a private installation for testing.

## Verification boundary

Synthetic unit/fault tests cover strict parser receipts, quotas, replay/conflicts, authority and audit rollback. Actual PostgreSQL tests exercise restricted-role lifecycle and raw/derived seals. Real Linux checks exercise network/filesystem/process denial and CPU/memory/output limits; trusted-HTTPS browser checks cover enabled/disabled extraction, page citations, exact downloads, review reset, retry, archive, forgetting and responsive layout. Logical restore includes PDF sentinels. Final exact-head hosted evidence is recorded in the PR; branch engineering is not production or full-MVP acceptance.
