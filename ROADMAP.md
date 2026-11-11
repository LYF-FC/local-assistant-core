# Roadmap

The [scope](docs/SCOPE.md), [155-reference register](docs/FEATURE_REGISTER.md), [dependencies](docs/FEATURE_DEPENDENCIES.md) and [MVP acceptance contract](docs/MVP_ACCEPTANCE.md) define the retained product scope. This page orders delivery; brevity here does not remove requirements. Historical versions are dependency stages, not dates, PR quotas or evidence of a released MVP. Version fields of 0.1.0 in package manifests do not establish release acceptance.

For a quick counted inventory, see the [feature overview](docs/FEATURE_OVERVIEW.md), [downloadable interactive dashboard](docs/FEATURE_DASHBOARD.html) and [critical feature review](docs/FEATURE_REVIEW.md). Keep it synchronized with this roadmap and the register after verified feature merges or approved scope changes; open PRs remain separate from merged progress.

## Delivery Kanban

| State | Capability / next evidence |
|---|---|
| Merged foundation | Spec 050 local original archive ([PR #2](https://github.com/LYF-FC/local-assistant-core/pull/2)); authoritative database originals retained. |
| Merged foundation | Spec 051 bounded PDF ingestion ([PR #3](https://github.com/LYF-FC/local-assistant-core/pull/3)): isolated text extraction, source/review/page provenance and recovery. |
| Merged foundation | Spec 052 bounded scanned-PDF OCR ([PR #4](https://github.com/LYF-FC/local-assistant-core/pull/4)): explicit uncertain recognition, review and recovery. |
| Merged foundation | Spec 053 scoped document answers ([PR #7](https://github.com/LYF-FC/local-assistant-core/pull/7)): reviewed lexical evidence, exact quotation selection, current-source citations and a default-disabled local adapter. |
| Merged foundation | Spec 054 calendar reconciliation/day briefing ([PR #8](https://github.com/LYF-FC/local-assistant-core/pull/8)); synthetic/manual adapter boundary, live provider acceptance remains open. |
| Merged foundation | Spec 055 finite recurring routines ([PR #9](https://github.com/LYF-FC/local-assistant-core/pull/9)), current-authority task/private-reminder generation and completion/lifecycle history. |
| Merged foundation | Spec 056 invoice field review, scoped duplicate hints and derived-copy lifecycle ([PR #11](https://github.com/LYF-FC/local-assistant-core/pull/11)). |
| Merged foundation | Spec 057 reviewed logical filing plans ([PR #12](https://github.com/LYF-FC/local-assistant-core/pull/12)): suggestions, corrections, non-executable approval/withdrawal and history. |
| Merged foundation | Spec 058 bounded offline email originals/single-attachment intake ([PR #13](https://github.com/LYF-FC/local-assistant-core/pull/13)), exact replay, creator-only provenance and aggregate forgetting. |
| Merged documentation | Spec 059 counted overview/dashboard and critical review of all 149 references; the complete review programme and six additions are now approved for after existing scope; approval is not runtime delivery. |
| Merged foundation | Spec060 installation UUID, bounded defaults, reviewed templates and informational readiness ([PR15](https://github.com/LYF-FC/local-assistant-core/pull/15)); dynamic members and feature activation remain open. |
| Merged foundation | Specs 062–067 ([PR17](https://github.com/LYF-FC/local-assistant-core/pull/17)–[PR22](https://github.com/LYF-FC/local-assistant-core/pull/22)): scoped daily overview, restricted financial capture (design, server, UI), bounded operations overview and scoped task/document search; no live service, model or status promotion beyond the dashboard counts. |
| Next | Authorized local-model quality/activation and fuller conversation/synthesis, alongside early installation configuration design. Live restricted mailbox/job recovery and separately authorized exactly-once filing remain dependencies after offline intake/proposal review. |
| Next by dependency | Live calendar adapter/full briefing; recurrence/one notification path; forwarded invoice intake/filing; operations and independent recovery. |
| Later, retained | Household/food, care/coaching, connected life, NOMAD/education, professional/creative/financial modules and governed platform evolution below. |
| Done | Documentation scope reconciliation delivered by [PR #1](https://github.com/LYF-FC/local-assistant-core/pull/1). The imported baseline has independent [engineering evidence](docs/VALIDATION.md), not inherited merged PR history or production acceptance. |

Add a verified delivering public PR link beside each completed checkbox only after merge. Keep green open PRs In progress. Host/provider acceptance and release certification remain separate gates.

## Reusable-installation milestone

Owner-approved INSTALL-01–12 add [independent installations, onboarding and feature lifecycle](docs/CONFIGURABLE_INSTALLATIONS.md). Plan the identity/configuration contracts early, implement them in coherent reviewed increments and complete them before any private-data conversion or reusable-installation release. This does not block independent bounded document work or grant production readiness. Keep all existing domain scope; no feature is dropped because it is optional.

| Stage | Exit gate |
|---|---|
| Configuration and identity design | Versioned private config, stable software keys, installation-local identities, household membership/permission migration and dependency catalogue specified. |
| Onboarding and activation | Secure owner/member provisioning; feature/secret readiness; server-side enable/disable and worker reconciliation; reusable safe templates. |
| Independent adoption and updates | Two isolated synthetic households pass lifecycle, export/restore and upgrade tests; existing-installation conversion separately rehearsed/approved with rollback. |

## Substantial MVP batches

Each row is a coherent capability boundary, not necessarily one PR. Group related commits and finish local checks before one completed batch push where practical. Split security/storage/migration changes when necessary for review; repair real failures without weakening verification. Do not repeatedly expand the synthetic Work pilot while everyday dependencies remain open.

| Order | Capability and retained IDs | Prerequisites / exit evidence |
|---|---|---|
| 1 | Durable original storage, bounded PDF extraction and staged OCR — DOC-X01/02, DOC-02/03, CORE-03/10 | Preserve spec 048 byte fidelity, owner/current revision checks, review reset, quotas, audit, export/forget and recovery. Define cross-store consistency, contained paths, parser isolation/bounds and orphan/partial-write recovery. Start with an isolated local adapter; OCR may require a separate worker/dependency review. Preserve future Synology compatibility without accessing a real NAS. |
| 2 | Scoped local answers and conversation — CORE-02/06/07/10, UI-01 | Authorized retrieval/provenance first; replaceable local model adapter with FR/ES/EN quality, refusal, injection, uncertainty and egress evaluations. Deterministic records and reminders survive inference failure. |
| 3 | Calendar read/reconciliation, briefing and dashboard — ORG-01/02, CORE-08/09, UI-01, MVP-02 | Stable IDs/cursors, recurrence/timezones, ownership, duplicates/conflicts and offline/stale state; explicit scopes and responsive private access. Writes are a separately tested extension; no presumed bidirectional mirror. |
| 4 | Recurrence and one notification/messaging path — ORG-03, CORE-11/13, REM-01 | Reuse durable workers; demonstrate recipient mapping, authorization, quiet rules/budgets, deduplication, bounded retry and ambiguous delivery reconciliation. External path requires separate activation authority. |
| 5 | Forwarded invoice intake, review and filing — DOC-01–03, MVP-03 | Storage/parser and worker foundations, restricted mail source, local extraction/uncertainty, reviewed naming/destination and exactly-once effect under retries/crashes. Preserve original/email provenance. |
| 6 | Everyday completion and operational readiness — FIN-06 basic, OPS-09/10, RND-01, MVP-01/04/05, PLATFORM-01–04 | Manual restricted goals/source capture; service/version inventory and failure UI; private desktop/mobile acceptance, offline/restart tests, accepted capacity/RPO/RTO, protected backups and independent clean-host/key/archive recovery. Any private adoption has a separately authorized mapping/rehearsal/rollback. |

Operational, privacy and recovery contracts begin in batch 1 and close across all batches; they are not postponed until final testing. Identity, permissions, audit, export and retention apply throughout. Dependency analysis can reorder independent work while preserving these exit gates.

## Later stages — all retained

| Stage | Capability | Dependencies / acceptance |
|---|---|---|
| Household/food (historical v0.3) | HOME-01–11, DOC-04–07: location stock, batches/expiry, supplies, transfers, grocery order intake, shopping, recipes/references, equipment and exports | Transactional stock/unit ledger; reviewed intake is not receipt; safe fetch; shortages/provenance; reversible file cleanup. Basic financial goal/progress register expands here. |
| Care/coaching (v0.4) | CARE-01–09: timeline, allergens/nutrition, growth, medicine/vaccines, health imports and exercise | Restricted records, sourced parent/clinician instructions, unknown states, consented imports and consultation exports; no autonomous clinical decisions. |
| Connected life (v0.5) | ORG-04–07, DOC-08, OPS-01–10; expanded DISC-02 | Locations/equipment, supported device/player interfaces, travel source minimization, allowlisted actions, reviewable music/repair manifests and outage recovery. Bounded Discovery collection/digest requires configured cadence. |
| NOMAD/education (v0.6; independent hardware can proceed in parallel) | EDU-01–07, EDU-X01–04, NOMAD-X01–03 | Independent offline content, verified constrained attributed bridge, versioned curriculum/concept/language/source hierarchy, private parent journal; no household database exposure. |
| Professional/research (v0.7) | WORK-01–07, WCOMP-01–04; FIN-12/15 manual research; expanded RND/DISC | Strict work/family isolation and independent recovery before real sources; approved outreach, prospect/client/career/shop/project continuity and sourced meeting/reporting/advisory. Manual opportunity/property pipelines and approved creative references may begin here. |
| Creative (v0.8) | WORK-08–10, CREATIVE-01–07, CREATIVE-X01 | Licensed local media, scoped approved style/reference records, verified editing/interchange route, clip organization, then first assemblies, then supervised correction/audio/color learning. Originals/linked media/project versions remain recoverable; creator approves export; sending/publication needs separate authority. |
| Advanced finance/assistance (v0.9) | FIN-01–17 beyond MVP basics; CORE-12 voice | Verified imports, deterministic reproducible long-term plans/policy/portfolio/stress scenarios, property costing/financing, opportunity review and professional review packs. Voice begins with opt-in push-to-talk and license/quality gates; wake word is optional later. No autonomous money movement or commitments. |
| Governed platform work (cross-cutting) | RND-01–05, DISC-01–03, DMARC-01/02, AI-01–03 | Service lifecycle research is distinct from product Discovery. Bounded mail-authentication reports do not authorize mailbox/DNS changes. External-model research/gateway remains disabled until separately authorized policy, payload, retention, budget and denial gates pass. |
| Supported service (v1.0) | Accepted scope plus PLATFORM-02/03 | Measured reliability/capacity, access review, documented maintenance/upgrade/rollback and independent recovery. MVP can be adopted through reviewed releases before the complete long-term vision. |
| Measured scale (v1.1+) | Additional workers/standby only when justified | Queue age, latency, memory/disk pressure or recovery needs; fencing/promotion/failover tests. No cluster requirement or high-availability claim from extra workers alone. |

See [reconciliation](docs/SCOPE_RECONCILIATION.md) for duplicates, superseded planning and unresolved feasibility. No live integration, production deployment, private-data conversion or auto-merge is authorized by this roadmap.

## Model research alongside local-answer design

RND-04/05 investigate task-specialized models and dense/MoE trade-offs under the [research contract](docs/LLM_RESEARCH.md). Start with hardware/task/quality budgets and a general-model baseline; evaluate a small current licensed shortlist only through bounded approved experiments. Report useful quality/resource gains, swapping/concurrency costs, isolation/refusal and deterministic availability. Adopt/defer/reject remains open; do not add a multi-model platform or MoE dependency from a paper or advertised active-parameter count alone. Coordinate with CORE-06/07/10, per-service R&D, product Discovery and INSTALL-02/03/10 without delaying the MVP for unproven specialization.

## Approved deferred review and refactoring — after existing scope

The owner approved **all** [individual and whole-product review recommendations](docs/FEATURE_REVIEW.md), including generalization/consolidation/refactoring, feasibility/cost validation, all shared implementation boundaries and former additions A–F. The [programme contract](docs/DEFERRED_REVIEW_PROGRAMME.md) schedules them after implementation of the existing 149-reference scope, including its later stages. This later ordering supersedes the review's suggestions to accelerate care/asset work or rearrange MVP. Existing baseline obligations and safety/permission gates continue now; the programme does not delay an earlier bounded MVP until the distant full vision is complete.

| Deferred bundle | Current reference | Planned direction |
|---|---|---|
| A | REV-01 | Scoped contacts and service relationships; reusable references without global identity/permission merging. |
| B | REV-02 | Membership departure, bounded delegation and access expiry with ownership/job reconciliation. |
| C | REV-03 | Accessibility and safe interruption recovery in existing interfaces. |
| D | REV-04 | Versioned/simulatable/pausable standing automation rules through current authority/orchestration. |
| E | REV-05 | Optional consented offline custodian continuity pack; no default break-glass authority. |
| F | REV-06 | Shared resource/attention limits, observable pauses and deterministic-service priority. |

These six supporting references complement the baseline; they are not six independent product features or completed implementations. Current register 155 = original149 + six deferred bundles. Original 99 named-feature and existing milestone comparisons remain intact. All 149 baseline assessments also remain part of the later programme, without duplicating them as149 new feature rows. Detailed acceptance and compatibility/migration/refactoring plans precede implementation; no v1.2 allocation or release date is invented. Research decisions remain evidence-based and real integrations/private-data/production effects separately authorized.

Spec059 review merged in PR14; spec060 setup foundations merged in PR15. Only INSTALL-01/02/03/06/08 advance to partial; full original installation contracts and runtime MVP journeys remain open. This batch publishes the approved planning/progress reconciliation, not another runtime capability.


## Merged PR17 — scoped daily overview

[Spec062](docs/DAILY_OVERVIEW.md) groups bounded agenda/tasks, owner-private in-app reminders, document text/extraction attention, failure/freshness limits and current-context source navigation. It implements baseline CORE-08/09, UI-01 and ORG-02 foundations without activating live services, new permissions or a separate queue. Global approvals/search/operations and complete MVP journeys remain open. This is independent of the approved later REV/refactoring programme, whose ordering remains after existing scope. PR16 merged its public scope reconciliation; all155 references remain retained.


## Next FIN-06 dependency — reviewed capture contract

[Spec063 financial capture](docs/FINANCIAL_CAPTURE.md) defines owner-private goals, dated assumptions, recorded existing plans and source references before implementation. Server-validated types, unknown/forecast distinctions, record-only plan acknowledgement/reset and export/forget/recovery must be demonstrated together. This design batch changes no runtime status or milestone. PR17 daily overview is now merged; basic finance remains open, alongside the other live/provider/operations/host acceptance gates. No deferred REV feature is brought forward.


## Merged PR19 — financial storage and lifecycle

[Spec064](docs/FINANCIAL_REGISTER_API.md) implements the approved FIN-06 capture contract's server boundary: typed owner-private records, dated basis/source, plan acknowledgement/reset, quota/concurrency/audit, JSON/Markdown/history export and forgetting/recovery. Financial UI is the following phase of this existing scope; no new design-only substitute or full FIN-06 completion is claimed. Later calculations/imports/providers and deferred review scope stay open. PR18 design and PR19 server delivery are merged; financial UI branch delivery is tracked below.


## Merged PR20 — financial capture UI

[Spec065](docs/FINANCIAL_UI.md) groups typed owner-private capture/correction, unknown-versus-zero/forecast labels, recorded-plan acknowledgement/reset, history, bounded validated JSON/Markdown copies, forgetting and ephemeral privacy/conflict handling. It reuses merged PR19 APIs without backend/schema/grant changes. FIN-06 now has a merged partial server foundation; the dashboard records the merged UI evidence separately from full acceptance and retains all later modelling/import/provider/host requirements. The approved deferred review programme remains after existing scope/later stages.


## Merged PR21 — MVP operations foundations

PR20 merged the financial capture UI. [Spec066 operations overview](docs/OPERATIONS_OVERVIEW.md) now groups explicit service/configuration observations, runtime version inventory, current-actor technical job statuses and private failure/freshness handling for existing OPS-09/RND-01. PR21 is merged engineering, not full operations acceptance. OPS-10 audit/reporting remains open without broadening audit access. The next retained MVP gaps include unified approvals/search, measured service/worker/backup/capacity monitoring, bounded live-adapter engineering, real local-model quality, outage/restart and independent host/key/archive recovery acceptance. Integrations, private adoption and production activation still require separate authorization; original later/deferred scope is unchanged.


## Merged PR22 — scoped task and document search

[Spec067](docs/SCOPED_RECORD_SEARCH.md), merged in [PR #22](https://github.com/LYF-FC/local-assistant-core/pull/22) after PR21 bounded operations foundations (full monitoring/audit/host gates remain), groups keyword search over existing task/document APIs, separate paging/partial failures, current-source validation and source-view navigation with ephemeral privacy. This advances existing CORE-08/UI-01 without new scope, provider or model. Pending approvals, broader/semantic search, measured monitoring/audit, adapter engineering and whole-MVP/outage/independent recovery remain retained next dependencies; real activation/private adoption remain separately authorized.


## Delivery strategy — synthetic MVP first, then connector spikes (agreed 10 November 2026)

Finish the everyday MVP with synthetic data and synthetic adapters first. Then, before any real data is used, run short time-boxed connector spikes: a real connector or local model exercised with a throwaway/sandbox account and invented content, to compare actual provider behaviour with the adapter contracts. Real private data comes last, behind separate authorization. A spike is not production activation: each needs its own approval for any account it uses, a stated data flow and no private records. Calendar and notification spikes start first, as early as their feature batches allow, because their schemas are sealed and costly to change; mail intake and local-model spikes follow. Retained later scope, owner approvals and activation boundaries are unchanged.

| Proposed order of remaining synthetic MVP work | Notes |
|---|---|
| 1 · One notification path with a synthetic channel (spec068, merged in [PR #24](https://github.com/LYF-FC/local-assistant-core/pull/24) with corrections in [PR #25](https://github.com/LYF-FC/local-assistant-core/pull/25); [contract](docs/NOTIFICATIONS.md)) | Delivery states (pending/delivered/failed/unknown), recipient mapping, quiet hours, day budgets, deduplication and bounded retry. |
| 2 · Invoice filing and job recovery (spec069 branch engineering, [contract](docs/FILING_EXECUTION.md)) | Synthetic destination; separate exact single-use filing request, single claimant, reconcile-before-retry and scrub-on-forget under crashes. Reuses item 1 delivery/retry semantics. Restart behaviour, a restricted inbox and any real adapter remain open; the guarantee is conditional on the destination, not unconditional exactly-once. |
| 3 · Calendar recurrence and full briefing | Recurrence/time zone expansion and a provider-shaped synthetic source. |
| 4 · Unified attention inbox | Pending approvals and remaining search gaps. |
| 5 · Operations and recovery | Worker/backup/capacity observation, clean-host restore including originals. |
| 6 · Whole-MVP acceptance tests | Cross-user leakage, offline/model-failure and restart journeys. |

This order is a proposal derived from the batch table above and dependency analysis; it can change when code inspection warrants and does not replace the exit gates in that table.
