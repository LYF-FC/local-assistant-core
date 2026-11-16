# Decisions

> Decision log: design and scope decisions. Explicit owner-approved decisions recorded here rank above [PROJECT_MASTER.md](PROJECT_MASTER.md) until reflected in it, and must be reflected in it. Delivery status of what was decided is owned by the master, not recorded here. Historical decisions are not rewritten.

Local structured authority, explicit current permissions, transactional minimal audit, restricted roles and deterministic workflows are foundational. Production and external integrations remain gated. Small document BYTEA staging is temporary; durable archive remains separate. See [architecture](ARCHITECTURE.md), [security](SECURITY.md) and [CI](docs/CI_COMPUTE.md).

## Scope and delivery reconciliation

The complete generic [register](docs/FEATURE_REGISTER.md), [MVP acceptance](docs/MVP_ACCEPTANCE.md) and [explicit reconciliation](docs/SCOPE_RECONCILIATION.md) supersede abbreviated source-snapshot planning as an exhaustive scope description. Short views must retain parent mappings and may not remove long-term requirements. Overlaps remain explicit; private configuration and historical evidence stay outside Git.

Development proceeds in substantial dependency-aware batches after owner review/merge of the planning PR. Finish local verification before one completed batch push where practical; required CI failures and review fixes justify additional runs. There is no commit cap or fixed PR countdown. No auto-merge. Synthetic engineering, merged delivery, host/provider acceptance and release certification are distinct.

FastAPI/PostgreSQL/React, Windmill/Home Assistant and separate NOMAD boundaries remain. Local storage/test adapters can unblock development without real NAS/provider access. Calendar writes, alternate orchestrators/frameworks, external AI, production and private namespace conversion remain separately reviewed choices, not incidental authority from this scope.

## Local archive transition — spec 050

Keep original bytes in PostgreSQL while introducing explicitly provisioned local disk copies. A pre-copy committed immutable root binding makes cleanup obligations durable; status re-verifies bytes rather than persisting a stale success flag. This deliberately separates storage failure/recovery acceptance from PDF/OCR parser changes. It does not replace Synology as the intended durable archive layer or activate a live share. No configuration change can silently discharge a bound document's managed-copy cleanup obligation.

## PDF derivation — spec 051

Extend the existing document lifecycle rather than create a second ingestion store. Preserve exact originals on extraction failure, expose bounded failure states, and require explicit owner review before citation. A separate local worker confines native parsing; upload idempotency is owner-scoped and payload-bound. Re-extraction creates an unreviewed version with build provenance. OCR and structured field extraction remain separate dependencies; this supersedes no original storage or deletion contract.

## Explicit bounded OCR — spec 052

OCR is an explicit owner derivation, never an automatic fallback or accuracy assertion. Preserve the exact source and previous derivations; expose uncertainty and require fresh review before citations. Keep the existing text mode as default and use an additive validator migration. Structured fields/uncertainty and filing remain separate retained outcomes.

## Reusable household installations — approved 8 November 2026

Retain the original 135 requirements and add INSTALL-01–12, bringing the register to 147. Develop one shared core with independent private installations, configurable members, safe templates, optional feature lifecycle and tested upgrades. Stable software keys are distinct from local identities. Enabling a feature grants no content permission; disabling is not deletion. Finish this milestone before legacy private-data adoption or a reusable-installation release; independent document work can proceed. [Detailed contract](docs/CONFIGURABLE_INSTALLATIONS.md). No runtime/schema change, account provisioning, deployment or migration is authorized by this documentation update.

## Task/model specialization investigation — approved 8 November 2026

Add RND-04/05 to the prior 147 requirements (149 total), retaining all existing scope. Compare one general local model with task specialists, and dense with sparse MoE, using current primary sources and reproducible task/hardware measurements. No architecture is preferred in advance; keep negative findings and adopt/defer/reject rationale. Multi-model routing implementation, weight downloads/experiments and production promotion remain separate steps. [Contract](docs/LLM_RESEARCH.md).

## Scoped source answers — spec 053

Begin local document answering with exact source quotations rather than unvalidated generated assertions. Model-disabled source search remains useful offline. Keep the local selector behind a default-disabled explicit model/digest configuration, current grants, two-phase audit and strict citation validation. This chooses an adapter protocol, not model weights, dense/MoE architecture, task-routing strategy or production activation. Free-form synthesis/conversation and real FR/ES/EN quality remain retained requirements.

## Calendar and briefing — spec 054

Implement the normalized complete-window boundary and deterministic briefing before activating calendar accounts. Full snapshots are bounded and all-or-nothing; omissions only imply removal in overlapping coverage. Preserve recurrence identity and original zone, reject contradictory sequence/cursor/fetch data and retain last good content on offline/failure. Do not infer cross-calendar duplicates or choose between overlaps. Live provider semantics, writes/mirroring and installation onboarding remain separate.

## Recurring routines — spec 055

Begin recurrence with explicit finite plans, earlier-fold/skip-gap rules and latest-only bounded downtime catch-up. Correct/resume affects future creation; stable routine/local-date identities cannot replay a materialized date. Pause/correction cancels linked active reminders; aggregate forgetting scrubs generated task copies/history. Use existing in-app reminder policies and keep external send/activation separate. No monthly/exception/calendar or production claim follows.

## Invoice field review — spec 056

Extend source review with deterministic bounded candidates and explicitly attested confirmed/unknown fields before mailbox/filing work. Human review is not model confidence or payment authority. Duplicate hints preserve conflicting originals and never approve deletion/filing; DOC-04 cleanup remains distinct. Derived-only forgetting is terminal and retains the original; aggregate document forgetting scrubs derived copies in the same transaction. See [contract](docs/INVOICE_REVIEW.md).

## Reviewed invoice filing plans — spec 057

Deliver reviewed logical naming/destination proposals before an apply adapter. Reuse source-bound invoice history and forgetting; avoid duplicate original/approval stores. A plan approval cannot become a ticket for future autonomous execution. Unknown fields need explicit manual paths; destination inventory/authorization/collision/containment and exactly-once effects remain separate. [Limits](docs/INVOICE_FILING_PLANS.md).

## Offline email intake — spec 058

Preserve original email before live mailbox integration using a strict offline single-attachment boundary. Raw email can contain incidental private context, so shared document access does not grant envelope access. Exact raw-message replay is distinct from semantic forwarded-copy/business dedup. Terminal forgetting retains only a disclosed private message-checksum tombstone; scrub raw content, initial filename and attachment checksum. Do not treat sender headers or plan approval as authority. [Rationale/limits](docs/OFFLINE_EMAIL_INTAKE.md).

## Feature overview and scope review — spec 059

Publish individually reviewed requirements without deleting/merging canonical IDs or approving candidate additions. Distinguish engineering slices, accepted MVP user journeys and full retained feature contracts. A shared primitive can satisfy multiple requirements while permissions and acceptance remain separate. Existing milestone labels stay; v1.2 remains unallocated. This decision records review/measurement discipline, not acceptance of every recommendation or new runtime architecture. [Method and recommendations](docs/FEATURE_REVIEW.md).


### Spec060 (merged PR #15): explicit installation initialization and reviewed templates

[Contract](docs/INSTALLATION_SETUP.md): migration/read do not mint installation identity; first confirmed initialization does. Defaults are bounded setup state, not global rewrites of existing timezone/language records. Shareable allowlisted templates carry only languages/timezone; independent initialization creates fresh identity, private recovery preserves identity. Readiness is an informational dependency catalogue with no activation controls or health claims. Existing trusted provisioning remains required; onboarding, dynamic grants, lifecycle compaction and feature controls remain open.


### 9 November 2026 — approve the deferred review programme

Owner approved all individual/whole-product review recommendations, generalization/consolidation/validation/challenge work, the shared implementation map and former candidates A–F. [Contract](docs/DEFERRED_REVIEW_PROGRAMME.md). Schedule after the entire pre-review 149-reference implementation scope and later stages; this supersedes earlier pending-approval labels and proposed priority shifts, without delaying existing safety duties or earlier MVP acceptance. Preserve all baseline outcomes/IDs and original 99 counts; add REV-01–06 as planned supporting bundles with parent mapping, not six independent product features. Existing behavior can satisfy an improvement without needless rewriting. No production/provider/private-data authorization is conferred. Spec060 merged PR15 provides partial installation foundations, not complete installation acceptance.


### Spec062 (merged PR #17) — compose baseline attention without another queue

Use [an explicit daily overview](docs/DAILY_OVERVIEW.md) over existing scoped APIs, retaining separate owner/domain authority and honest first-page/freshness limits. Keep sign-in landing behavior and require manual refresh; do not add ambient all-scope queries, a global approval claim or a new mutation surface. Destination context is in memory and server-reread, never an authority token. Full review/refactoring directions remain deferred; existing MVP usability/privacy obligations continue now.


### Spec063 design — financial input is not a forecast or action authority

[The capture contract](docs/FINANCIAL_CAPTURE.md) separates owner-recorded confirmed inputs, assumptions, forecasts and unknowns; accepted plans require payload-bound record-only acknowledgement and reset on material correction. Store typed financial records with server validation, not arbitrary Memory profiles labelled as finance. Existing finance scope remains owner-private with explicit current grants. This is a future implementation boundary, not permission to calculate, connect providers, transfer funds or adopt private data.


### Spec064 (merged PR #19) — deliver the finance server boundary independently

Implement [typed storage/API](docs/FINANCIAL_REGISTER_API.md) and its PostgreSQL/recovery evidence before the financial UI. Unknown versus zero/forecast, current owner/grant and record-only plan acknowledgement are server-enforced. Corrections reset acceptance; generic approvals/Memory do not confer financial authority. This is a bounded foundation, not reduced FIN-06 scope. UI/freshness/whole-MVP and later finance remain required.


### Spec065 (merged PR #20) — finish the financial owner workflow

Use [explicit typed forms and separate acknowledgements](docs/FINANCIAL_UI.md) for plan-record acceptance, private-copy export and managed forgetting. Unknown amounts stay null; zero and forecasts keep explicit labels. Kind/owner/scope cannot change through correction, and accepted plans grant no execution authority. Reuse reviewed APIs; no backend/schema changes or new finance calculation. Dashboard promotes only verified merged PR19 server evidence, preserving the original 99 cohort and later/deferred scope.


### Spec066 (merged PR #21) — observations must retain uncertainty

Use [explicit observed/configured/disabled/unknown states](docs/OPERATIONS_OVERVIEW.md), not a global green health badge. Installed versions do not establish approval/support/license/advisory status. Preserve INSERT-only runtime audit access: audit review stays unavailable until a narrow separately reviewed projection exists; OPS-10 is retained. Sample only current actor technical-admin jobs, without payloads/global counts/overdue inference.


### Spec067 (merged PR #22) — bounded search before complete unified inbox

Prove delivery semantics against a [synthetic channel](docs/NOTIFICATIONS.md) before any real connector: commit the attempt claim before sending, treat timeouts as unknown and reconcile by lookup instead of resending, and keep one delivery per reminder cycle. Real providers need a separate spike and authorization.

Execute approved invoice plans only through a [separate, exact, single-use owner request](docs/FILING_EXECUTION.md) that is consumed atomically by the first claim and bound to one owner, scope and plan revision; plan approval stays non-executable. Define destination identity by an explicit canonical-path policy and treat its hash as a uniqueness handle, not a security boundary. Describe the guarantee as single claimant plus reconcile-before-retry, conditional on a destination that honours a key and answers lookup; never as unconditional exactly-once. Forgetting is a first-class operation that scrubs keys and history snapshots idempotently while keeping history append-only.

Use [one explicit scope and two existing libraries](docs/SCOPED_RECORD_SEARCH.md), with honest page/unavailable/review labels. Do not call first pages complete global search or generate rankings/advice. Keep pending approvals, Memory/finance/Work and semantic search requirements open. Current-source rereads and minimal navigation targets prevent old matches becoming edit authority.


### 10 November 2026 — synthetic MVP first, real connectors by spike, real data last

Complete the everyday MVP against synthetic data/adapters before real services. Validate high-risk adapters (calendar and notification first, then mail intake and local model) through short time-boxed spikes using throwaway accounts and synthetic content, ideally before further features depend on their sealed schemas. Use real private data only last, under separate authorization. Rationale: keeps private data out of development and keeps activation gated while reducing late surprises from provider behaviour. A spike confers no production authority and each account/data flow needs explicit approval. See the [roadmap strategy](ROADMAP.md#delivery-strategy--synthetic-mvp-first-then-connector-spikes-agreed-10-november-2026).

### 14 November 2026 — Spec073 design: overdue and stalled work observation (owner decisions D1–D4)

The owner approved four decisions for the frozen [overdue and stalled work observation](specs/073-overdue-stalled-work/spec.md) design. **D1:** technical administrators may see household-wide state derived from members' private reminder, notification, filing and approved-job records, as queue-level states only (no counts, ages, owners, scopes, records, ids or per-item details); the residual risk that repeated reloads can reveal approximately when, and in small households possibly whose, item became due is accepted, and audit records but does not prevent such probing. **D2:** a fixed 120-second grace period applies to the observer only; workers are never delayed, and the measurement assumes a non-decreasing application clock. **D3:** migration 0038 classifies `operations.work_status` as `operations_read`, keeping the seven-category audit summary shape. **D4:** queues whose workers are not deployed in the default Compose stack may show overdue, and the view must state that it is not a worker-health check. These decisions approve the documented design only: they do not authorize implementation, expand scope, or change any requirement, priority, acceptance criterion or gate status.

### 15 November 2026 — Spec074 (recovery-set manifest): Phase B acceptance, two acknowledged interpretations, Phase C design-only authorization

The owner decisions that fixed the [frozen specification](specs/074-recovery-set-manifest/spec.md) (O1a to O9 and the related decisions of its section 10.1; frozen on 14 November 2026) are recorded there and are not restated here. This entry records later owner decisions that the frozen specification cannot carry.

**Phase B acceptance (15 November 2026).** The owner formally accepted the synthetic-only Phase B implementation of spec 074, merged in [PR #40](https://github.com/LYF-FC/local-assistant-core/pull/40) (merge `47b949e`). The acceptance is bounded to that synthetic-only scope: it is not acceptance of Gate 11, MVP-05 or any other gate, it is not independent verification and it is not a recovery-readiness or RPO/RTO claim. The independent-verification record at an exact `main` revision remains outstanding.

**Two implementation interpretations, explicitly acknowledged and accepted by the owner (15 November 2026).**
1. The section 3.4 / section 7.3 discrepancy: the implementation preserves the closed section 7.3 output schema and reports only the first violation; it adds no count field and no repeated reason codes.
2. The stale-temporary-link interpretation: if temporary-link removal fails after publication but the directory fsync confirms durability, the result is `published_durable` with `stale_temporary_present`; the resulting set remains unverifiable until the temporary link is removed.

The frozen specification is not edited; [docs/RECOVERY_SET.md](docs/RECOVERY_SET.md) documents both.

**Phase C design-only authorization (15 November 2026).** The owner authorized design and preparatory work only for Phase C (key custody, expected-hash governance, retention and forgetting, capacity, key-generation requirements). This does not authorize Phase C implementation, key-management or key-generation tooling, generating, provisioning, storing or rotating a real key, creating or operating a real recovery set, operational recovery or restore, connecting to the NAS or any production storage, running measurements or synthetic-key test runs, or any migration, schema or configuration change. Proposals and designs are not decisions: each deferred matter (O1b, O2 retention, O5 governance, O8 dump ceiling, O9) stays deferred until the owner decides it. This entry changes no requirement, priority, acceptance criterion or gate status; Gates 6, 10 and 11, OPS-09, OPS-10 and MVP-05 are unchanged. The authorized Phase C design/preparation package was delivered as documentation-only PR #42 (merge `b081c12`): five reviewable draft documents and a blank independent-verification template. Their merge records delivery of drafts only; it does not approve any proposal, complete C1–C5 implementation/measurement tasks, satisfy independent verification, or authorize implementation or operations.

### 15 November 2026 — Spec074 Phase C: implementation of the non-operational portions authorized

On 15 November 2026, after the Phase C design drafts merged ([PR #42](https://github.com/LYF-FC/local-assistant-core/pull/42)), the owner explicitly authorized implementation across the five Phase C workstreams (C1 key custody, C2 expected-hash governance, C3 retention and forgetting, C4 capacity validation, C5 key-generation requirements) as one coordinated batch. It extends the design-only authorization recorded in the entry above (same date) for the non-operational portions only. The authorization excludes, and the owner retained as prohibited: generating, provisioning, storing, rotating or activating a real recovery key; creating or operating a real recovery set; real recovery or restore; NAS or production-storage access; capacity measurements and large-data runs; synthetic-key test runs for governance or capacity; key-generation or key-management tooling; migrations, schema or configuration changes outside the approved plan; claims of operational readiness or independent verification; promotion of Gate 6, Gate 10, Gate 11, OPS-09, OPS-10 or MVP-05; and merging any pull request. Proposals and designs remain proposals and each open owner decision (O1b, O2 retention periods, O5, O8 and the dump ceiling, O9) stays open until the owner decides it; independent verification remains a separate prerequisite. The implemented scope is described in [docs/RECOVERY_PHASE_C_IMPLEMENTATION.md](docs/RECOVERY_PHASE_C_IMPLEMENTATION.md). It was delivered and merged in [PR #43](https://github.com/LYF-FC/local-assistant-core/pull/43), merge commit `708e8134098846a40e0c49cae5a954913aef9fdb`, on 15 November 2026. Merge records delivery only: it is not independent verification, owner acceptance of Phase C, completion of C1–C5, or operational authorization. This entry changes no requirement, priority, acceptance criterion or gate status.

### 16 November 2026 — Spec074: T25 second-scenario expected code reconciled with the written verification order

On 16 November 2026 (Europe/Paris) the owner explicitly decided, by their own instruction, to retain the existing verification order of the [frozen specification](specs/074-recovery-set-manifest/spec.md): the key's installation binding is checked **before** the key references and the MAC verification. For T25's second scenario (installation A's key and fingerprint presented with installation B's manifest) the expected rejection is **`key_installation_mismatch`**, with the states of the section 2.5 row "Key bound to a different installation than the manifest declares" (authenticity invalid; integrity, expectations and freshness not evaluated; exit 1).

The precedence was already specified: section 2.5 (its combinations row), section 6.2 (which states this code for exactly this shape) and section 7.2 step 3 all place the binding check first, as does T17. T25's expected column, which listed `manifest_authentication_failed` or `manifest_key_reference_mismatch` for the second scenario, was inconsistent with them. The conflict was found while mapping the tests to the criteria and recorded as unresolved in the [traceability appendix](docs/RECOVERY_INDEPENDENT_VERIFICATION_TRACEABILITY.md) and in [PR #51](https://github.com/LYF-FC/local-assistant-core/pull/51); the owner then decided it as stated here.

Effect: the second-scenario expected code in the spec's T25 row is corrected to `key_installation_mismatch` (the first and third scenarios and every other row are unchanged) and the correction is recorded in the spec as a separately labelled post-freeze clarification. The original freeze (14 November 2026, the content of commit `f903237a69e6e2eeeef8b057abef3fc618a27630`) is not rewritten or re-dated and this is not a new freeze; the current text is that revision plus this one correction. **Implementation behavior is unchanged:** the verification order is retained, nothing in the runtime changes, and the existing test `test_t25_cross_installation_substitution` (merged in PR #51 as `28a2d79`) already asserts this exact outcome.

This decision does not authorize runtime changes, acceptance of any criterion or gate, operational activity, or the closure of any other requirement. Independent verification of spec 074 and the Phase C owner decisions (C1 to C5) remain open, and no register, gate or acceptance status changes.
