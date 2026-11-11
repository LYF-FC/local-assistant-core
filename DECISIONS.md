# Decisions

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
