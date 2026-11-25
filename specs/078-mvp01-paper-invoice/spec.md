# Spec 078 — MVP-01 "the paper invoice" (Mac-local rehearsal, synthetic)

## Authority, scope and outcome

On 24 November 2026 the owner approved this journey (decisions D1–D9, recorded in [DECISIONS.md](../../DECISIONS.md)). Authorization is not evidence of implementation, integration, testing, verification or acceptance; [PROJECT_MASTER.md](../../PROJECT_MASTER.md) owns status. This contract owns the behaviour and limits of the extension.

Outcome: on the accepted single rehearsal stack (`local-assistant-core-mvp01-owner`, rebuild with data preserved), one synthetic adult forwards invoices as a **text PDF** and a **scanned (image-only) PDF**; Butler reads them locally with the **real** Poppler text extraction and Tesseract OCR engines on **synthetic bytes**; the owner sees what was found and what is uncertain, views the original in the browser, corrects or leaves fields Unknown, and the invoice is filed once through the existing path to the **simulated metadata ledger**; a SIGKILL restart (now including the PDF worker) keeps everything; with the PDF worker stopped the original is kept and the unavailable state is explained.

## Decisions and exclusions

D1 journey; D2 the optional PDF worker joins the rehearsal stack and two generated PDF fixtures; D3 an Unknown total may be filed and the journey says so ("Unknown is not zero"); D4 the original is viewable in the browser; D5 honesty wording, list badge, owner stop/start commands for the PDF worker, PDF worker in the SIGKILL list; D6 restart evidence = container restart and SIGKILL only; D7 backend behaviour unchanged (every failed or unavailable attempt adds a version and resets review; a UI-only guard is allowed); D8 the first base-image pull is acceptable; D9 same project, rebuild, data preserved.

**Unconfirmed engineering choice (A-4, not an owner decision):** the original view (D4) is rendered client-side to canvases with the third-party `pdfjs-dist`. The owner has not decided this mechanism or the new dependency; it is an **unresolved A-4 awaiting the owner** (not approved by anyone with owner authority), and a server-side render or no browser view remain open alternatives if the owner or a reviewer rejects it.

Recommendations not individually confirmed by the owner and applied here as engineering choices: A-1 a dropped OCR line is signalled by wording only (no detector, no confidence); A-2 tests assert states, never OCR text; A-3 extra spec 052 PDF states are covered by unit/PostgreSQL tests only. If the owner decides otherwise, the affected tests and wording change (see [analysis](analysis.md)).

Excluded: a real destination, NAS or folder; a live mailbox; handwriting and photos; multi-attachment and HTML mail; model-assisted extraction; payments; more than two OCR pages; any claim about OCR accuracy; real invoices or letterhead; archive-to-disk; migrations, new filing states, backend or `pdf_worker` changes, security-control changes; promotion of any gate.

## Requirements

| ID | Requirement |
|---|---|
| R1 | **Stack.** `compose()` in `scripts/mvp01-owner.sh` (and `reset`'s teardown) includes `infra/core/pdf-ingestion.override.yml`; `pdf_worker` is in the container-restart and the SIGKILL lists; `status` reports the worker and states the seccomp wording ("default Docker seccomp plus an in-process guard, not verified confinement"). |
| R2 | **Owner commands.** `pdf-worker stop|start`: stop sets a flag file and stops the worker (rolled back if it fails); the flag keeps it stopped across `start`, `rebuild` and `restart` and `status` says so; `start` removes the flag only after the worker is healthy; both refuse without a running stack and with other input. |
| R3 | **Fixtures.** `invoice-pdf.eml` (P1), `invoice-scan.eml` (P2: image-only, ≤2 pages, the Total line deliberately blurred) and `invoice-pdf-offline.eml` (P3), generated deterministically by `paper_fixtures.py` (no timestamps, no host fonts), originals ≤128 KiB, distinct invoice numbers and unique Message-IDs, SHA-256 published in the script and checked before copying. The scan raster is a committed artefact derived once from Poppler's rendering of the P2 lines in the repository's PDF worker image. |
| R4 | **Honest extraction wording** (`frontend/src/pdf-extraction.ts`): *no text* suggests OCR and says the original is kept; *unavailable* says the reader is offline, the original is kept and what to do; OCR says a line can be missing and that Unknown is allowed; no accuracy claim; an unavailable or empty state is never called failed. |
| R5 | **List badge** per extraction state (text extracted, OCR text (uncertain), no text found, extraction unavailable, encrypted, unreadable, too large). |
| R6 | **Original in the browser** (D4): "View original pages" draws the original as page images on `<canvas>` with a pinned `pdfjs-dist`; no `<iframe>`, `<embed>`, `<object>`, blob navigation, text/annotation/link/form layer or scripting; eval, XFA and range/stream fetching off; at most **3** pages, a 4-million-pixel budget and side/aspect limits per canvas, a 20-second render limit, and an abort (Hide, another document, unmount) that cancels the render, destroys the loading task and terminates the pdf.js worker; a damaged, encrypted or oversized PDF ends in a visible "The original could not be shown here" state, never a blank or a crash; the button is disabled until the **same copy-limits acknowledgement as the download** is ticked and only the existing read permissions apply; nothing is saved. **Reading a hostile PDF in the browser is a larger attack surface than showing server-rendered images and is "not verified confinement"; it is not claimed to be safe.** `pdfjs-dist` is pinned exactly at 4.10.38 (≥ 4.2.67, the fix for CVE-2024-4367, checked on the registry), license Apache-2.0, lockfile integrity `sha512-/Y3fcFrXEAsMjJXeL9J8+ZG9U01LbuWaYypvDW2ycW1jL269L3js3DVBjDJ0Up9Np1uqDXsDrRihHANhZOlwdQ==`, `npm audit`: 0 vulnerabilities (24 November 2026); the CSP is untouched and the worker is a same-origin script. Backend and `pdf_worker` unchanged: the bytes come from the existing `original` operation. |
| R7 | **Unknown is not zero** on the invoice review form (existing), the filing plan, the synthetic filing view and the guide. |
| R8 | **UI guard** (D7): while extraction is unavailable the Re-extract and OCR buttons stay disabled until the owner ticks that the worker is back; the wording says each attempt adds a version (quota 50) and needs a new review; the state stays visible. |
| R9 | **Checker.** `scripts/mvp01-owner-check.py` gains `paper-journey`, `paper-verify`, `paper-worker-down`, `paper-repaired`, `paper-peer`, `paper-hostile-import` (states, not OCR text). |
| R10 | **Rehearsal safety unchanged** (spec 076 R6–R8): fixed subnet, public CA only, guarded `reset`, ≤3 owner sign-ins, the Mac awake. |

## Characterised behaviour (no change)

- A blurred line can vanish from the OCR text while the status stays `ready` (observed once, one scan, one setup); the wording tells the owner, nothing detects it.
- Every failed or unavailable extraction attempt adds a document version and resets review (D7); proven by a PostgreSQL test so a silent change is caught.
- The plan and filing accept an invoice whose total is Unknown (D3); the ledger holds metadata only.

## Validation mapping (A5 plan S1–S21)

| Scenario | Evidence |
|---|---|
| S1 composition, S8 restart (SIGKILL incl. `pdf_worker`) | script tests (overlay in every compose call, kill list), live: kill event `signal=9`, exit 137 for `pdf_worker`; `paper-verify` |
| S2–S7 import, badge, OCR, review, plan, filing, replay | `pdf-extraction.test.ts`, live `paper-journey`, `mvp01-paper.spec.ts` (paper-ui) |
| S9 original view | `mvp01-paper.spec.ts` (canvas drawn, no embedded PDF, 390 px), hostile-PDF test (N4) |
| S10–S13 worker down, guard, repair, persistence | script tests (flag across restart), live `paper-worker-down` / `paper-repaired`, `mvp01-paper.spec.ts` (paper-down) |
| S15 peer / non-owner | live `paper-peer`; PostgreSQL `test_mvp01_paper_invoice_postgres.py` |
| S16 duplicate hints, S14 worker killed mid-request, S18 confinement probe, S19 076/077 regression, S20 reset, S21 egress | not run or partly run: see [convergence](convergence.md) |
| S17 wrong value | PostgreSQL test with injected OCR result (never live OCR text) |

## Limits

Real engines on synthetic bytes; OCR output varies by platform and no accuracy is claimed. Seccomp is Docker's default profile plus an in-process libseccomp guard: not verified confinement. The filing destination is the simulated metadata ledger. pdf.js (Apache-2.0) is a new third-party dependency that parses the original in the browser; it is drawn-only and was exercised with a hostile test PDF, which is not a security proof. The browser tests run on a disposable copy, not on the owner's stack.

## Acceptance

None claimed. Human verification and owner acceptance are pending; see [plan](plan.md), [tasks](tasks.md), [checklist](checklist.md), [analysis](analysis.md), [convergence](convergence.md).
