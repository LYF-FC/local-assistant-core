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
