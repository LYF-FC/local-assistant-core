# Scoped document library — spec 048

## Specify
Deliver one usable local development capability: manual UTF-8 text/Markdown uploads, original-byte download, scoped listing/literal search, explicitly reviewed text retrieval with stable line citations, owner corrections/replacement/history, acknowledged JSON export and atomic forgetting. Files and metadata stay local; only explicit browser downloads leave managed storage. No model, network fetch, PDF/OCR/parser, NAS/mail integration, production activation or external action.

## Clarify
- Scopes: household_shared, member_a_private, member_b_private. Current shared documents are readable by current members; all mutations/history are creator-only. Private records remain owner-only even with a matching grant. Technical administrators gain no content access.
- Accept only .txt/.md strict UTF-8, nonempty, at most 128 KiB original and 32,000 Unicode characters. Preserve BOM/CRLF bytes; reject NUL and invalid UTF-8. Treat all text, including Markdown and prompt injection, as inert data. Only POST upload/replacement proxy requests receive a 192 KB body bound for base64 overhead; other paths retain 64 KB.
- Default unreviewed; explicit review is an owner attestation, never independent verification. Every replacement resets review. Corrections can change title, source reference and review; the exact decoded original is the only searchable content.
- Up to 64 active/128 total documents per owner, 50 versions/document, 8 MiB logical original+UTF-8 text retained bytes per owner across versions. Serialize writes on owner identity. Forget remains possible at all limits and scrubs hashes, metadata, text and original bytes in all managed versions.
- Search defaults to reviewed current documents. Library can explicitly include unreviewed. Bounded 25-row UUID pages, no search in URLs/audit. Exact current revision required for originals, edits and excerpts. Excerpts return 1–50 requested logical lines, maximum 16 KiB UTF-8, with stable ID/revision/hash/source/line provenance; no generated answer.
- Metadata/history export requires an explicit unmanaged-copy acknowledgement. Historical originals are owner-only. Forget is terminal; retained IDs/owner/scope/revision/timestamps are minimal tombstones. Earlier backups and exported files need separately reviewed reconciliation; no physical secure-erasure claim.

## Acceptance
Prove owner/shared/private/revoked/session/CSRF/transport boundaries, optimistic conflicts, byte fidelity/hash/provenance, replacement review reset, search literals/pages, historical originals, terminal full-copy redaction, bounds/quotas, atomic audit failure, database seals and minimal runtime grants. Exercise migrations, actual logical restore, interface races/errors and real trusted HTTPS synthetic workflows. All four final exact-head CI jobs remain required. Merged delivery and actual owner-host acceptance remain distinct.
