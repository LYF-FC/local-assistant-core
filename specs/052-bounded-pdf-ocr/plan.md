# Plan / dependency analysis

1. Prove Tesseract and bounded grayscale rendering under the existing guard before extending the application. Fix language selection and disable OpenMP concurrency without weakening syscall denial. Include exact package/model build provenance.
2. Extend the existing extraction request with an explicit text/OCR mode. Preserve the default text wire format and add one fixed OCR discriminator; strictly bind response engine to requested mode. Reuse extracted versions, immutable originals, review reset and audit.
3. Add migration 0025 extending the existing metadata validator for one OCR engine and its stricter page bound. Refuse downgrade with retained OCR provenance; leave old migration files unchanged.
4. Add explicit owner OCR control, visible recognition uncertainty in current/history/citations, strict client metadata parsing and source downloads. No new library/store or intake flow.
5. Add deterministic synthetic image fixtures, focused parser/API/PostgreSQL/client checks and one OCR lifecycle browser scenario within the existing enabled PDF phase. Extend existing restore sentinels rather than duplicate whole recovery harnesses.
6. Reconcile canonical docs/register and mark PR #3 merged only with verified public reference. Final full required checks once; no repeated host stack provisioning while unit behavior is still changing. Use CI metadata for final exact-head evidence.

Primary interfaces: https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html and https://manpages.debian.org/trixie/poppler-utils/pdftoppm.1.en.html . OCR/model packages stay in the optional network-free container; no external service or new host dependency. Structured field candidates/uncertainty, duplicate detection and reviewed filing remain retained later work.
