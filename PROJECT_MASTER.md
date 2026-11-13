# Butler — project master

**Project status snapshot reconciled against `main` revision `5096134687fd1c03805977a1681b415395a046f0` (merge of [PR #31](https://github.com/LYF-FC/local-assistant-core/pull/31), 13 November 2026).** Reconciliation means the documents were checked against what is merged at that revision. It is not independent verification: no gate is verified at this or any exact `main` revision (see sections 3, 4 and 6).

This is the authoritative document for Butler's product scope, the Everyday MVP definition, stage/gate progress, what is delivered, what is outstanding, implementation order and current priorities. It points to — and does not copy — the detailed contracts. **Precedence**, highest first: (1) the [constitution](.specify/memory/constitution.md): foundational principles and constraints; (2) explicit owner-approved decisions (recorded in [DECISIONS.md](DECISIONS.md) and the approving PRs): authorized changes to scope or direction, which must be reflected in this file and prevail over it until they are; (3) this file: consolidated current scope, MVP definition, gates, status, priorities and sequencing; (4) the [register](docs/FEATURE_REGISTER.md): requirement identifiers, retained requirement text and evidence pointers; (5) [docs/MVP_ACCEPTANCE.md](docs/MVP_ACCEPTANCE.md): acceptance criteria and procedures; (6) specs and feature contracts: detailed technical requirements and behavior. Architecture ([ARCHITECTURE.md](ARCHITECTURE.md)) and operational procedures keep authority over their own subjects. Where a lower-ranked document disagrees on a subject owned here, correct it.

It is a status and navigation document. It adds no scope and no acceptance criteria: gates are defined by [docs/MVP_ACCEPTANCE.md](docs/MVP_ACCEPTANCE.md), requirements by the [register](docs/FEATURE_REGISTER.md).

## 1. What we are building

Butler (Local Assistant Core) is a local-first assistant for private and shared household and professional records. It remembers confirmed context, coordinates routines, retrieves evidence and proposes or executes only bounded, authorized actions. Structured records stay authoritative; model output never grants authority. Full product scope: [docs/SCOPE.md](docs/SCOPE.md) (155 register references: the 149-reference baseline plus six approved deferred review bundles REV-01–06). Later stages (household/food through measured scale) remain retained in the [roadmap](ROADMAP.md); they are not part of the Everyday MVP.

## 2. What the Everyday MVP requires

The Everyday MVP is the set of **eleven end-to-end gates** in [docs/MVP_ACCEPTANCE.md](docs/MVP_ACCEPTANCE.md), plus the [reusable-installation adoption gate](docs/MVP_ACCEPTANCE.md#reusable-installation-adoption-gate) before any reusable release or private-data adoption. Register IDs MVP-01…05 name five of those outcomes (MVP-01 is the whole-journey composite); the table in section 5 maps every gate to its register IDs. Gates are accepted on their own actual evidence: batch completion is not MVP acceptance, and distant later-stage expansion is not an implicit blocker. Candidate additions and reordering remain owner decisions.

Delivery strategy (agreed 10 November 2026): finish the MVP with synthetic data and synthetic adapters first; then run short, separately approved connector spikes with sandbox accounts and invented content; real private data last, behind separate authorization.

## 3. Status model

Five separate facts. None implies another, and "complete" is never derived from them automatically.

| Dimension | Values | Evidence that supports it |
|---|---|---|
| Implementation | Planned / Implemented | Code at the stated scope and a limits statement (what is synthetic, in-process or real) |
| Integration | Not merged / Merged (PR) / Imported baseline | PR number and merge commit on `main`; the imported baseline has no PR (see below) |
| Testing | Not tested / Tested | Named automated tests covering the contract's positive and negative paths; CI result on the PR head |
| Verification | Not verified / Verified / Regressed | Independent re-check at an exact `main` revision with full (not scope-reduced) coverage; reviewer sign-off; for restart and recovery items an executed procedure record |
| Acceptance | Not accepted / Accepted (environment, scope) | **Owner decision** against the gate's repeatable scenario, recording date, revision, environment and result |

Rules:

- **Imported baseline.** The repository began as a clean source snapshot. Capabilities from it have no PR or merge commit here, so they are never labelled Merged. Their provenance is "Imported baseline", with its evidence and limits in [docs/VALIDATION.md](docs/VALIDATION.md) (CI at `501d92b`, 8 November 2026; historical, bounded to synthetic engineering).
- A merged PR does not mean the complete feature is implemented. Implemented does not mean tested; tested does not mean verified; verified does not mean accepted.
- Acceptance names its environment and scope: "Accepted (synthetic)" is not acceptance against a real integration.
- A synthetic implementation is never presented as a real integration. In-process tests are not process-level restart durability. Persistent job state is not persistence of an external effect. Tested is not proven in production. A design proposal is not an implemented feature.
- A stage or gate is complete only when its own acceptance scenario is accepted by the owner. Counting merged PRs never completes one.
- Unknown evidence stays **unknown** in this document. Nothing is promoted without evidence; a lost status is recorded as Regressed, not silently overwritten.
- The register's free-text status column (for example "partial; full contract remains open") is a per-reference label, not a status in this model: "partial" there means a bounded subset is implemented and merged, and nothing about testing beyond what its evidence column states, verification or acceptance.

**Authoritative homes** (full precedence in the introduction and section 8). Gate and stage status: this file. Requirement text and evidence pointers: the register. Acceptance procedure: `docs/MVP_ACCEPTANCE.md`. Behavior and limits: specs and feature contracts. Counts and dashboards: generated (section 8).

## 4. Where things stand (summary)

State on `main` `5096134`: **0 of 11 gates accepted; 0 verified at an exact `main` revision.** Every gate has a bounded subset delivered, either merged through the PRs listed in section 5 or present in the imported baseline. External-provider integrations are synthetic (notification channel, calendar provider, filing destination) or absent; several capabilities are operated manually by a person (tasks, memory review, finance capture). One real local-filesystem capability exists and is optional and opt-in: the spec 050 original archive on a private local directory. There is no real NAS/Synology destination, live mailbox, real calendar or notification provider, device push or activated real local model. 155 register references: 0 accepted, 40 with a partial bounded subset, 115 planned (generated figures: [overview](docs/FEATURE_OVERVIEW.md)).

| # | Gate | Register IDs | Implementation | Integration | Testing | Verification | Acceptance | Stage state |
|---|---|---|---|---|---|---|---|---|
| 1 | Identity, memory, portability | CORE-02/03/04/05 | Subset | Imported baseline (no PR) | Tested (test files, see §5) | Not verified (imported baseline CI at `501d92b` is historical) | Not accepted | Partially done |
| 2 | Private desktop/mobile entry | CORE-08/09, UI-01 | Subset | Merged: #17, #22 (UI foundations from imported baseline) | Tested | Not verified | Not accepted | Partially done |
| 3 | Local conversation and cited answers | CORE-06/10 | Subset (lexical, exact quotation) | Merged: #7 | Tested | Not verified | Not accepted | Partially done |
| 4 | Calendar and briefing (MVP-02) | ORG-01/02, MVP-02 | Subset (synthetic) | Merged: #8, #28 | Tested | Not verified | Not accepted | Partially done |
| 5 | Tasks, recurrence, delivery | ORG-03, CORE-11/13, REM-01 | Subset (synthetic channel) | Merged: #9, #24, #25, #31 (manual tasks and reminders from imported baseline) | Tested (process-restart evidence, synthetic channel only: #31) | Not verified | Not accepted | Partially done |
| 6 | Originals, PDF/OCR, retrieval | DOC-X01/02, DOC-02, CORE-03/10 | Subset | Merged: #2, #3, #4, #11 (text/Markdown library from imported baseline) | Tested | Not verified | Not accepted | Partially done |
| 7 | Forwarded invoice (MVP-03) | DOC-01/02/03, MVP-03 | Subset (synthetic destination, in-process) | Merged: #11, #12, #13, #26, #29, #31 | Tested (in-process; process-restart, synthetic destination) | Not verified | Not accepted | Partially done; real-destination and live-inbox evidence missing |
| 8 | Offline and model failure (MVP-04) | MVP-04 | Local deterministic subsets | Imported baseline (no PR) | Subsets only | Not verified | Not accepted | Partially done; whole scenario not run |
| 9 | Basic financial capture | FIN-06 | Subset (manual, restricted) | Merged: #19, #20 (implementation); #18 was design-only and is not implementation integration | Tested | Not verified | Not accepted | Partially done |
| 10 | Operations and restart | OPS-09/10, RND-01, PLATFORM-01/02 | Subset (observations only) | Merged: #21 (jobs foundation from imported baseline) | Tested | Not verified | Not accepted | Partially done; OPS-10 not started |
| 11 | Clean-host recovery (MVP-05) | MVP-05, PLATFORM-03 | Synthetic logical restore only | Imported baseline (no PR) | Tested (synthetic) | Not verified | Not accepted | Barely started |
| — | Whole-journey composite (MVP-01) | MVP-01 | Not implemented | — | Not tested | Not verified | Not accepted | **Not started** |
| — | Installation adoption gate (INSTALL-01–12) | INSTALL-01/02/03/06/08 | Foundations only | Merged: #15 | Tested | Not verified | Not accepted | Partially done |

"Tested" means test files for the merged work exist in `backend/tests` or `frontend` and CI passed on each PR head per that PR's metadata; this document did not re-run them, and PR CI results are not recorded in the repository (see §6, evidence gaps).

## 5. Stage and gate progress

For each gate: capabilities delivered, merged PRs, test evidence, verification, acceptance, what is outstanding, blockers, and what must happen next. Detailed acceptance wording and procedures are in `docs/MVP_ACCEPTANCE.md`; do not restate them here. Verification is **Not verified** and Acceptance is **Not accepted** for every gate unless stated; the "Testing evidence" lines name test files that exist and do not claim a current run.

PR index: #1 scope reconciliation (docs); #2 spec 050; #3 spec 051; #4 spec 052; #7 spec 053; #8 spec 054; #9 spec 055; #11 spec 056; #12 spec 057; #13 spec 058; #14 spec 059; #15 spec 060 (and the PR #16 spec 061 programme reconciliation); #17 spec 062; #18 spec 063 (design); #19 spec 064; #20 spec 065; #21 spec 066; #22 spec 067; #24 spec 068; #25 spec 068 corrections; #26 spec 069; #27 Batch 3 **design proposal only**; #28 spec 070 (Batch 3 implementation); #29 spec 069 follow-up; #30 project master and documentation governance (docs); #31 Batch 4 process-restart evidence for specs 068/069 (synthetic only, migration 0036). PRs #5, #6, #10 and #23 are documentation-only.

### Gate 1 — Identity, memory and portability (CORE-02/03/04/05)
- **Delivered (subset):** local accounts/sessions, current grants, HTTPS/Host/Origin/CSRF, restricted DB role, protected audit, memory with history, bounded export. Specs 001, 003, 006–009 and related.
- **Testing evidence:** `test_identity.py`, `test_memory.py`, `test_approvals.py`, `test_boundary.py` and `integration/test_identity_postgres.py`, `test_memory_postgres.py`, `test_approval_postgres.py`.
- **Outstanding:** domain profiles, whole-MVP leakage tests (IDs, counts, search, answers, citations, exports, history), complete original/history portability.
- **Blockers:** none beyond the whole-MVP test suite itself. **Next:** include in the whole-MVP acceptance suite (priority 5).

### Gate 2 — Private desktop/mobile entry (CORE-08/09, UI-01)
- **Delivered (subset):** responsive UI over local HTTPS; scoped daily overview ([PR #17](https://github.com/LYF-FC/local-assistant-core/pull/17)); scoped task/document search ([PR #22](https://github.com/LYF-FC/local-assistant-core/pull/22)).
- **Testing evidence:** frontend tests (`frontend`), `test_context_preview.py`. Browser scenarios run in CI.
- **Branch engineering (spec 071 implementation, open PR #34, not merged):** an explicit Inbox view composes tasks, reminders, documents needing review, filing failures and notification failures with evidence-only pending approvals (new read-only audited `approvals/query`) for one granted scope; see [ATTENTION_INBOX.md](docs/ATTENTION_INBOX.md). Merged delivery is recorded only after merge.
- **Outstanding:** private remote/mobile host acceptance; the Gate 2 criterion ("Dashboard exposes agenda, pending approvals, reminders, failures and authorized search.") is not accepted by the owner and stays open; remaining search gaps (all-library/semantic); an approvals screen and infrastructure status.
- **Blockers:** host acceptance needs an actual private host (separate authorization). **Next (priority 2):** the spec 071 documentation is merged ([PR #33](https://github.com/LYF-FC/local-assistant-core/pull/33)); the implementation is in open [PR #34](https://github.com/LYF-FC/local-assistant-core/pull/34), not merged. Record-level navigation for filing and notification cards is implemented on the branch as the owner approved (see [convergence](specs/071-unified-attention-inbox/convergence.md)). Outstanding: hosted CI including the real-stack inbox browser spec (unverified until it runs), and owner review and merge of PR #34.

### Gate 3 — Local conversation and cited answers (CORE-06/10)
- **Delivered (subset):** reviewed lexical evidence retrieval, exact-quotation answers, strict citations, default-disabled local selector (spec 053, [PR #7](https://github.com/LYF-FC/local-assistant-core/pull/7)).
- **Testing evidence:** `test_document_answers.py`, `test_answer_adapter.py`, `integration/test_document_answers_postgres.py`.
- **Outstanding:** real-model FR/ES/EN quality and activation, semantic retrieval, free-form conversation/synthesis, no-egress evidence for a real model.
- **Blockers:** needs an approved local model and its licensing/resource review (RND-04/05 research is open). **Next:** after the synthetic MVP gates; time-boxed local-model spike (see §7).

### Gate 4 — Calendar and briefing (MVP-02)
- **Delivered (subset, synthetic):** bounded normalized snapshot reconciliation and day briefing (spec 054, [PR #8](https://github.com/LYF-FC/local-assistant-core/pull/8)); recurrence expansion, a synthetic cursor-based provider-mode sync and a 1–7 day briefing (spec 070, [PR #28](https://github.com/LYF-FC/local-assistant-core/pull/28), merge `b0a5a67`).
- **Testing evidence:** `test_calendar_*.py`, `test_calendars.py`, `test_calendar_briefing_v2.py`, `integration/test_calendars_postgres.py`, `test_calendar_sync_postgres.py`, `test_calendar_provider_schema_postgres.py`.
- **Outstanding:** a real sandbox provider (live read adapter) and provider acceptance; writes need authority, ownership, conflict and ambiguous-write tests first; unified briefing dashboard.
- **Blockers:** real provider requires a separately approved sandbox account and data-flow declaration. **Next:** calendar connector spike (first spike, see §7).

### Gate 5 — Tasks, recurrence and delivery (ORG-03, CORE-11/13, REM-01)
- **Delivered (subset):** manual tasks and private in-app reminders (specs 046/047); finite daily/weekly routines (spec 055, [PR #9](https://github.com/LYF-FC/local-assistant-core/pull/9)); synthetic-channel notification path with delivery states, quiet hours, day budgets, deduplication, bounded retry and unknown-outcome reconciliation (spec 068, [PR #24](https://github.com/LYF-FC/local-assistant-core/pull/24), corrections [PR #25](https://github.com/LYF-FC/local-assistant-core/pull/25)). **Synthetic channel only — not a real provider.**
- **Testing evidence:** `test_manual_tasks.py`, `test_task_reminders.py`, `test_routines.py`, `test_notifications.py` and their `integration/*_postgres.py` counterparts. **Process-restart (Batch 4, synthetic channel only):** `integration/test_notification_restart_postgres.py` runs the real notification worker in separate processes, killed with SIGKILL, against PostgreSQL and a durable synthetic delivery ledger; also adds a revision fence to the notification worker and migration `0036_notification_recheck` (an inconclusive lookup could not be recorded on PostgreSQL before). See [docs/NOTIFICATIONS.md](docs/NOTIFICATIONS.md). This is Testing evidence only; Verification and Acceptance are unchanged.
- **Outstanding:** one authorized real external channel with recipient identity; evidence of restart behaviour against a real provider (the process-restart evidence uses a synthetic ledger only); full recurrence/calendar coupling; revocation-prevents-delivery on a real channel.
- **Blockers:** real channel requires separate activation authority. **Next:** notification connector spike (priority 4, proposed).

### Gate 6 — Originals, PDF/OCR and retrieval (DOC-X01/02, DOC-02, CORE-03/10)
- **Delivered (subset):** exact-byte originals with optional local archive (spec 050, [PR #2](https://github.com/LYF-FC/local-assistant-core/pull/2)); bounded isolated PDF text extraction (spec 051, [PR #3](https://github.com/LYF-FC/local-assistant-core/pull/3)); explicit bounded OCR (spec 052, [PR #4](https://github.com/LYF-FC/local-assistant-core/pull/4)); scoped duplicate hints and invoice fields (spec 056, [PR #11](https://github.com/LYF-FC/local-assistant-core/pull/11)).
- **Testing evidence:** `test_document_archive.py`, `test_documents.py`, `test_pdf_ingestion.py`, `test_pdf_ocr*.py` and `integration/test_document*_postgres.py`, `test_pdf_*_postgres.py`.
- **Outstanding:** live NAS/durable archive, full index/archive/key and older-backup suppression acceptance (DOC-X02), PDF/OCR acceptance on the gate's full fixture set.
- **Blockers:** real NAS access is not authorized; key/older-backup acceptance depends on Gate 11. **Next:** covered by the operations/recovery batch (priority 3).

### Gate 7 — Forwarded invoice (MVP-03) — **partially done; not complete**
- **Delivered (subset):** reviewed invoice candidates with human confirmed/unknown decisions and duplicate hints (spec 056, [PR #11](https://github.com/LYF-FC/local-assistant-core/pull/11)); reviewed logical filing plans, non-executable (spec 057, [PR #12](https://github.com/LYF-FC/local-assistant-core/pull/12)); bounded offline email and single-attachment lineage with exact replay (spec 058, [PR #13](https://github.com/LYF-FC/local-assistant-core/pull/13)); **synthetic** filing execution: separate exact single-use request, single claimant, reconcile-before-retry, no-overwrite, scrub-on-forget (spec 069, [PR #26](https://github.com/LYF-FC/local-assistant-core/pull/26)); revision-fenced attempts and reconciliations, a PostgreSQL journey from a twice-forwarded offline email to a filed synthetic destination entry, crash points modelled in-process, and migration 0034 downgrade evidence ([PR #29](https://github.com/LYF-FC/local-assistant-core/pull/29)).
- **Testing evidence:** `test_invoice_review.py`, `test_invoice_filing.py`, `test_email_intake.py`, `test_filing.py`; `integration/test_filing_postgres.py`, `test_filing_fence_postgres.py`, `test_mvp03_journey_postgres.py`, `test_filing_downgrade_postgres.py`. The evidence listed above is **in-process and synthetic**: it proves claim/reconcile semantics against an in-memory destination. **Process-restart (Batch 4, synthetic destination only):** `integration/test_filing_restart_postgres.py` runs the real filing worker in separate processes, killed with SIGKILL before and after the effect, against PostgreSQL and a durable directory-backed synthetic destination, covering fresh-process recovery, reconciliation without a repeated effect, an inconclusive lookup staying unknown, competing workers, stale-worker fencing and no overwrite (see [docs/FILING_EXECUTION.md](docs/FILING_EXECUTION.md)). This is Testing evidence of worker recovery against a synthetic destination, not durability of a real destination.
- **Outstanding:** process-restart evidence against a real destination (the Batch 4 evidence uses a synthetic destination only); live restricted inbox and source rules; destination authorization for a real root, filing adapters and cross-store reconciliation against a real destination. The guarantee is conditional on the destination, not unconditional exactly-once. [PR #29](https://github.com/LYF-FC/local-assistant-core/pull/29) does **not** complete MVP-03.
- **Blockers:** real destination/inbox need separate authorization. **Next:** live inbox, real destination authorization and cross-store reconciliation remain open; Batch 4 addresses process-restart evidence only.

### Gate 8 — Offline and model failure (MVP-04)
- **Delivered (subset):** deterministic local tasks, reminders, documents and records that do not depend on inference (specs 046–048).
- **Testing evidence:** subsets only; no whole-scenario test exists.
- **Outstanding:** internet-disconnect and inference-stopped scenarios end to end, queued external work, capacity-exhaustion behavior of filing.
- **Blockers:** depends on Gates 5 and 7 for queued external work. **Next:** whole-MVP acceptance tests (priority 5).

### Gate 9 — Basic financial capture (FIN-06)
- **Delivered (subset):** design ([PR #18](https://github.com/LYF-FC/local-assistant-core/pull/18)); typed owner-private server storage and lifecycle (spec 064, [PR #19](https://github.com/LYF-FC/local-assistant-core/pull/19)); capture/correction UI (spec 065, [PR #20](https://github.com/LYF-FC/local-assistant-core/pull/20)); export/forget and synthetic recovery.
- **Testing evidence:** `test_finance.py`, `integration/test_finance_postgres.py`, frontend tests.
- **Outstanding:** full MVP and host acceptance; no provider, import or funds movement is in scope; later modelling is a later stage.
- **Blockers:** host acceptance. **Next:** include in the whole-MVP acceptance suite.

### Gate 10 — Operations and restart (OPS-09/10, RND-01, PLATFORM-01/02)
- **Delivered (subset):** explicit API/database observations, runtime package versions, bounded own technical job status (spec 066, [PR #21](https://github.com/LYF-FC/local-assistant-core/pull/21)).
- **Testing evidence:** `test_operations.py`, `integration/test_operations_postgres.py`, `test_jobs.py`, `integration/test_jobs_postgres.py`.
- **Outstanding:** full service/worker/capacity/backup/certificate observation; OPS-10 audit/reporting (not started); host startup/unlock, resource budgets, independent alerting, restart verification of durable progress and leases on a real host.
- **Blockers:** an independent observer and a host to test on. **Next:** operations and recovery batch (priority 3).

### Gate 11 — Clean-host recovery (MVP-05)
- **Delivered (subset):** synthetic logical DB backup/restore, session and pending-intent quarantine, Work source/checkpoint/suppression procedures ([docs/BACKUP_RESTORE.md](docs/BACKUP_RESTORE.md), [docs/RECOVERY_ASSESSMENT.md](docs/RECOVERY_ASSESSMENT.md)).
- **Testing evidence:** `test_recovery_assessment.py`, `test_restore_*.py` and `integration/test_restore_*_postgres.py`.
- **Outstanding:** restore on an independent clean host including originals, configuration, keys and migration/model manifests; measured RPO/RTO; failed/missing/tampered input tests; actual-host acceptance.
- **Blockers:** an independent clean compatible host; key recovery design. **Next:** operations and recovery batch (priority 3).

### Whole-journey composite (MVP-01) and installation gate
- **MVP-01:** no whole-journey test exists (private access, agenda, authorized answer, reminder and reviewed filing surviving restart). **Not started.**
- **Installation adoption gate (INSTALL-01–12):** only INSTALL-01/02/03/06/08 have partial foundations (spec 060, [PR #15](https://github.com/LYF-FC/local-assistant-core/pull/15)); dynamic members, activation controls and rehearsed conversion remain open.

### Spec ↔ PR ↔ gate map

| Spec | PR | Gates |
|---|---|---|
| 050 / 051 / 052 | #2 / #3 / #4 | 6 |
| 053 | #7 | 3 |
| 054 / 070 | #8 / #28 (#27 was design only) | 4 |
| 055 | #9 | 5 |
| 056 / 057 / 058 | #11 / #12 / #13 | 6, 7 |
| 059 / 061 | #14 / #16 | none (review and programme documentation) |
| 060 | #15 | installation gate |
| 062 | #17 | 2 |
| 063 / 064 / 065 | #18 / #19 / #20 | 9 |
| 066 | #21 | 10 |
| 067 | #22 | 2 |
| 068 | #24, #25, #31 | 5 |
| 069 | #26, #29, #31 | 7 |

## 6. Missing acceptance evidence

1. **No gate has an acceptance record** (date, revision, environment, result). None can be marked Accepted.
2. **No gate has reviewer-signed verification.** The repository records one exact-`main` CI result (run 43493750600, a push to `main` at `5096134`; attempt 1 failed in the `postgres` job on a lock timeout in an unrelated work-adapter test and the rerun of the failed jobs succeeded, so all six jobs succeeded only after that rerun; in `docs/FEATURE_PROGRESS.json` `ci_evidence`). That is hosted CI evidence, not verification of any gate and not owner acceptance. Other PRs' CI results live in PR metadata; [docs/VALIDATION.md](docs/VALIDATION.md) covers only the imported baseline at `501d92b`.
3. **MVP-03:** live inbox and real destination (Gate 7). Process-restart evidence now exists for a synthetic destination only (Batch 4); it is not verification and does not cover a real destination.
4. **Notification worker (spec 068):** process-restart evidence now exists for a synthetic channel only (Batch 4); evidence against a real provider is absent (Gate 5).
5. **MVP-01, MVP-04, MVP-05:** whole-scenario tests and procedures do not exist.
6. **Numerical thresholds** that specs must define before implementation are not collected centrally; which remain undefined is **unknown**.
7. **Specs 068–070** have no `convergence.md`, unlike specs 050–067.

## 7. Dependencies, order and priorities

Dependencies, from the existing roadmap and gate text: restart/recovery evidence (priorities 1 and 3) precedes any claim of exactly-once or durability; connector spikes need separately approved sandbox accounts and come after the synthetic gates they inform (calendar and notification first, because their schemas are sealed and costly to change; mail intake and local model after); the unified inbox depends on the merged approvals, search and notification paths; whole-MVP acceptance tests depend on all of them.

Current priorities, in order. **Proposed — awaiting owner confirmation; not yet owner-approved.** This is a proposed delivery order derived from the roadmap's earlier proposed order and the backlog's tracked item. It does not change the established scope, gate definitions, gate statuses or acceptance criteria, which are unaffected by whether the order is confirmed:

1. **Process-level restart evidence for Gate 7 and the notification worker (Gate 5).** Addresses the outstanding process-level restart-evidence requirement for Gate 7, but does not complete MVP-03 or resolve its other outstanding requirements. *Batch 4 implemented the following method for synthetic collaborators only (Testing evidence; this does not confirm the order, which remains unapproved, and does not complete MVP-03 or Gate 5):* use a persistent synthetic destination that survives worker-process termination, and test (a) termination before the effect, (b) termination after the effect but before the outcome is recorded, (c) reconciliation by a fresh process, and (d) prevention of a duplicate effect.
2. **Unified attention inbox** (pending approvals and remaining search gaps; Gate 2).
3. **Operations and recovery** (worker/backup/capacity observation; clean-host restore including originals; Gates 10, 11, and the DOC-X02 half of Gate 6).
4. **Time-boxed connector spikes** with sandbox accounts, calendar and notification first (Gates 4, 5); mail intake and local model after (Gates 7, 3). Each needs its own approval and data-flow statement.
5. **Whole-MVP acceptance tests:** cross-user leakage, offline/model-failure and restart journeys (Gates 1, 8, MVP-01).

Priority 1 is the proposed next implementation task; the owner confirms, changes or rejects the order before it is treated as approved. No feature work is part of the governance PR that introduced this file.

## 8. Documentation map and update rules

Precedence between documents is stated in the introduction; the table gives the authoritative home of each kind of information.

| Information | Authoritative home | Other documents |
|---|---|---|
| Scope, MVP definition, gate and stage status, priorities, order | **This file** | Link here; do not restate |
| Requirement text, feature IDs, evidence pointers | [docs/FEATURE_REGISTER.md](docs/FEATURE_REGISTER.md) | Dependencies in [docs/FEATURE_DEPENDENCIES.md](docs/FEATURE_DEPENDENCIES.md) |
| Acceptance criteria and procedures | [docs/MVP_ACCEPTANCE.md](docs/MVP_ACCEPTANCE.md) | No progress narrative there |
| Behavior, requirements, limits per feature | `specs/` and `docs/<FEATURE>.md` | |
| Design decisions and architecture | [DECISIONS.md](DECISIONS.md), [ARCHITECTURE.md](ARCHITECTURE.md) | |
| Operating procedures | [OPERATIONS.md](OPERATIONS.md), [SETUP.md](SETUP.md), [docs/BACKUP_RESTORE.md](docs/BACKUP_RESTORE.md), [SECURITY.md](SECURITY.md) | |
| Sequencing view | [ROADMAP.md](ROADMAP.md) (reflects this file; no independent status) | |
| History | [CHANGELOG.md](CHANGELOG.md), [CONTEXT.md](CONTEXT.md), [docs/BACKLOG_STATUS.md](docs/BACKLOG_STATUS.md), [docs/FEATURE_REVIEW.md](docs/FEATURE_REVIEW.md), [docs/VALIDATION.md](docs/VALIDATION.md) | Dated records, not current status |
| Counts, overview, dashboard | Generated: [docs/FEATURE_OVERVIEW.md](docs/FEATURE_OVERVIEW.md), [docs/FEATURE_DASHBOARD.html](docs/FEATURE_DASHBOARD.html) | Never edit by hand |
| Snapshot input to the generator | [docs/FEATURE_PROGRESS.json](docs/FEATURE_PROGRESS.json): hand-curated, not generated; its snapshot revision must equal the revision at the top of this file; `ci_evidence` records one hosted CI run only (not verification, not acceptance) | |

**Update rule.** Update the authoritative source, then regenerate derived views (`python3 scripts/build_feature_overview.py`). Every PR that changes delivered behavior updates this file's gate entry (and the register row it affects) in the same PR, citing evidence for any status change. Mark a PR as merged only after the merge, with its number and merge commit; because a PR cannot cite its own merge, record it in a follow-up documentation update. Repository policy (`scripts/check_repository.py`) checks that the revision above equals the snapshot revision, that every gate maps to register IDs that exist, and that relative links in this file resolve.
