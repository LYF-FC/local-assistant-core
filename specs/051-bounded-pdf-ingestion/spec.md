# Bounded local PDF ingestion — spec 051

## Specify and clarify

Extend the existing scoped library with exact-original PDF upload, bounded local text extraction, explicit failure/no-text states, review, retry, version history, page/line citations, search, archive and forgetting. Synthetic development/test only; no model, OCR, mail, NAS or production activation. Originals, extracted text and audit stay local. The only transfer is original bytes to an explicitly selected isolated local parser over a private Unix socket, followed by a bounded result.

Keep the current 128 KiB original, 32,000-character extracted text, 64 active/128 lifetime records, 50 versions and 8 MiB original-plus-text history limits. Text/Markdown behavior and exact bytes remain unchanged. PDFs have at most 12 pages. No silent truncation; malformed, encrypted, no-text, resource-limited and unavailable states remain visible, unreviewed and non-retrievable as cited evidence. Mixed blank/text pages carry an explicit completeness notice; extraction is not independent verification.

Store raw PDF bytes/hash separately from derived text/hash and versioned extraction metadata. Preserve page-to-derived-line spans and the extractor version. Owner review is required before cited retrieval. A replacement or explicit re-extraction creates a version and resets review. Failed extraction still retains the bounded original for download and retry. PDF creation requires an owner-scoped random idempotency key bound to the exact request; replay cannot create a second document or change payload. Forget clears request hashes, originals, text and extraction metadata; only random operation identity may remain with the ordinary tombstone.

Parse only after transport/session/CSRF/scope/owner checks. Recheck authority after extraction before releasing output. The optional parser is a separate non-root, read-only, capability-dropped container with no network, no database credentials, no archive mount and no original files on disk. Each parser child has a default-deny syscall policy, read-only opens, no sockets/process creation, CPU/address-space/output/file-descriptor limits and a wall timeout. The parent serves serial bounded Unix-socket requests, is non-dumpable and never logs input/output. Missing confinement fails closed. No Docker socket is exposed to the API or worker.

## Acceptance

Prove exact PDF originals through replacement/history/download/archive/restore/forget; text legacy compatibility; Unicode byte quotas; successful text and multiple-page citations; encrypted/scanned/invalid/oversize/mixed/timeout/output-bomb states; explicit review/reset; idempotent request conflicts/replay/tombstones; cross-user/private/admin/revoked/expired/CSRF/Origin denial; audit rollback and real DB seals/locks/migrations. Test actual Linux syscall/network/filesystem/process denial and absence of worker credentials. Exercise optional-disabled and enabled browser flows with stale-response suppression. Run required full local/hosted checks, logical restoration and privacy/dependency review before readiness.

Downgrade refuses retained PDF snapshots and immutable extraction operation evidence, including content-free forgotten history. Forgetting is content erasure, not permission to erase operation history.

OCR remains a subsequent separately bounded worker capability; these states and source/provenance records preserve its dependency rather than reducing scope.
