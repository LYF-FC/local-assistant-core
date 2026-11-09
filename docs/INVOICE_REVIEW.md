# Invoice field review and duplicate hints

[Spec 056](../specs/056-invoice-review/spec.md) extends the reviewed document library with bounded local candidates and explicit human decisions. Use synthetic sources during development. No data leaves the installation; no model, mailbox, filing destination, ledger or payment integration is added.

## Review from an original

Open a current reviewed document with ready text/PDF/OCR extraction and prepare invoice fields. Fixed English/French/Spanish labels suggest issuer, invoice number, issue date, due date, total and currency. Inspect the original, exact source line, page references and OCR warning. Suggestions never establish truth. Explicitly confirm or leave **each field unknown**, then attest that the original was checked. A confirmed value needs a current source line or a manual original-check note; corrections remain human assertions. Unknown is neither zero nor an absent/paid/unpaid claim.

The scan considers at most 1,000 logical lines, complete evidence lines of 256 Unicode characters/1 KiB, and three candidates per field. Missing, conflicting, unsupported and truncated extraction is disclosed. Dates accept ISO dates; amounts accept signed decimal strings with two fractional digits and no grouping, up to 999,999,999.99 in magnitude. A decimal comma can normalize to a dot. Explicit currencies are EUR/USD/GBP/CHF/CAD; symbols do not imply a currency. A confirmed due date cannot precede a confirmed issue date. There is no tax, currency-conversion or total arithmetic.

## Authority, drift and duplicates

The document creator alone prepares, changes, exports, reads history or forgets its invoice resource. Current shared readers can inspect eligible reviews and duplicate hints; private content still requires the creator and current scope grant. Administration grants no content access. Every receipt pins source revision and hashes. Any document revision, extraction replacement or review withdrawal withholds old fields from current reads and key matching; reprepare explicitly resets attestation. Creator history retains past provenance until forgetting.

Read-only duplicate pages contain at most 25 currently visible documents from one chosen scope, matched by exact original bytes or human-confirmed issuer/invoice number normalized only for case/whitespace. Stale/unreviewed field reviews cannot supply matching keys. Hidden records/counts remain hidden. Equal keys with different originals are possible conflicts: inspect both sources. Hints never merge, delete, suppress intake, approve filing or identify a legal business. This bounded intake aid does not deliver DOC-04 file inventory, cleanup or rollback manifests.

## History, retention and recovery

One invoice resource belongs to each document UUID, with at most 100 active revisions and an additional terminal forget. Creator history/export is paginated five revisions at a time. Invoice-only forgetting scrubs candidates, decisions, keys and all invoice snapshots while retaining the document original; it is terminal for that resource. Forgetting the document scrubs both document and derived invoice content/history atomically. Already downloaded exports and older protected backups cannot be recalled.

Current user/session/grant, document and invoice authority remain locked through metadata-only audit commit. Expected revisions reject conflicts without automatic retry. Invoice values, source quotes and match-key hashes stay out of audit/logs. The document-detail client keeps drafts only in memory and clears them on source/revision/scope/view/session changes.

Migration `0028_invoice_review` follows `0027_recurring_routines`; existing migration/runtime-role setup supplies protected current/history tables and restricted grants. Back up and stop writers before any separately authorized adoption. Downgrade removes invoice tables and derived history; use a reviewed protected backup/rollback rather than claiming it preserves those records. The full logical restore test checks reviewed evidence, unknowns, provenance, keys and forgotten snapshots. These disposable tests do not certify independent clean-host recovery or private deployment readiness.

Restricted mail intake, email provenance, proposed names/destinations, retry/crash-safe exactly-once filing, live Synology access and full MVP-03 acceptance remain dependencies. See [scope reconciliation](SCOPE_RECONCILIATION.md) and [MVP gates](MVP_ACCEPTANCE.md).
