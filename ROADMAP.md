# Roadmap

**Sequencing view only.** Current status of every MVP stage and gate, what is delivered and outstanding, and the current priorities are owned by [PROJECT_MASTER.md](PROJECT_MASTER.md); this page does not maintain a second set of status facts. The [scope](docs/SCOPE.md), [155-reference register](docs/FEATURE_REGISTER.md), [dependencies](docs/FEATURE_DEPENDENCIES.md) and [MVP acceptance contract](docs/MVP_ACCEPTANCE.md) define the retained product scope; brevity here does not remove requirements. Versions are dependency stages, not dates, PR quotas or evidence of a released MVP; 0.1.0 package versions do not establish release acceptance.

Counted views are generated: [feature overview](docs/FEATURE_OVERVIEW.md) and [dashboard](docs/FEATURE_DASHBOARD.html). They are derived, never edited by hand. Open PRs are not merged progress.

## Where the MVP stands and what is next

Gate-by-gate progress, evidence and blockers: [PROJECT_MASTER.md, section 5](PROJECT_MASTER.md#5-stage-and-gate-progress). Ordered priorities with reasons: [section 7](PROJECT_MASTER.md#7-dependencies-order-and-priorities). Work already merged (specs 050–070, PRs #2–#29) is recorded there and in the historical notes at the end of this page. No gate is accepted.

## Reusable-installation milestone

Owner-approved INSTALL-01–12 add [independent installations, onboarding and feature lifecycle](docs/CONFIGURABLE_INSTALLATIONS.md). Plan the identity/configuration contracts early, implement them in coherent reviewed increments and complete them before any private-data conversion or reusable-installation release. This does not block independent bounded document work or grant production readiness. Keep all existing domain scope; no feature is dropped because it is optional.

| Stage | Exit gate |
|---|---|
| Configuration and identity design | Versioned private config, stable software keys, installation-local identities, household membership/permission migration and dependency catalogue specified. |
| Onboarding and activation | Secure owner/member provisioning; feature/secret readiness; server-side enable/disable and worker reconciliation; reusable safe templates. |
| Independent adoption and updates | Two isolated synthetic households pass lifecycle, export/restore and upgrade tests; existing-installation conversion separately rehearsed/approved with rollback. |

## Substantial MVP batches (capability boundaries and exit evidence)

Each row is a coherent capability boundary, not necessarily one PR; the order is by dependency and is not a delivery status (see the master for what is merged). The order of the remaining work is the master's section 7. Group related commits and finish local checks before one completed batch push where practical. Split security/storage/migration changes when necessary for review; repair real failures without weakening verification. Do not repeatedly expand the synthetic Work pilot while everyday dependencies remain open.

| Order | Capability and retained IDs | Prerequisites / exit evidence |
|---|---|---|
| 1 | Durable original storage, bounded PDF extraction and staged OCR — DOC-X01/02, DOC-02/03, CORE-03/10 | Preserve spec 048 byte fidelity, owner/current revision checks, review reset, quotas, audit, export/forget and recovery. Define cross-store consistency, contained paths, parser isolation/bounds and orphan/partial-write recovery. Start with an isolated local adapter; OCR may require a separate worker/dependency review. Preserve future Synology compatibility without accessing a real NAS. |
| 2 | Scoped local answers and conversation — CORE-02/06/07/10, UI-01 | Authorized retrieval/provenance first; replaceable local model adapter with FR/ES/EN quality, refusal, injection, uncertainty and egress evaluations. Deterministic records and reminders survive inference failure. |
| 3 | Calendar read/reconciliation, briefing and dashboard — ORG-01/02, CORE-08/09, UI-01, MVP-02 | Stable IDs/cursors, recurrence/timezones, ownership, duplicates/conflicts and offline/stale state; explicit scopes and responsive private access. Writes are a separately tested extension; no presumed bidirectional mirror. Delivery status of this batch: [spec 070](specs/070-calendar-recurrence-briefing/spec.md), [PROJECT_MASTER.md gate 4](PROJECT_MASTER.md#gate-4--calendar-and-briefing-mvp-02). |
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

Spec059 review merged in PR14; spec060 setup foundations merged in PR15. Only INSTALL-01/02/03/06/08 advance to partial; full original installation contracts and runtime MVP journeys remain open. The PR #16 reconciliation published the approved planning/progress record, not another runtime capability.

## Delivery strategy — synthetic MVP first, then connector spikes (agreed 10 November 2026)

Finish the everyday MVP with synthetic data and synthetic adapters first. Then, before any real data is used, run short time-boxed connector spikes: a real connector or local model exercised with a throwaway/sandbox account and invented content, to compare actual provider behaviour with the adapter contracts. Real private data comes last, behind separate authorization. A spike is not production activation: each needs its own approval for any account it uses, a stated data flow and no private records. Calendar and notification spikes start first, as early as their feature batches allow, because their schemas are sealed and costly to change; mail intake and local-model spikes follow. Retained later scope, owner approvals and activation boundaries are unchanged.

## Historical delivery notes (dated; not current status)

The notes below are retained as written when each batch merged. Where they say "next" or "branch", that was true at the time; current status is in [PROJECT_MASTER.md](PROJECT_MASTER.md). The former delivery Kanban and the "proposed order of remaining synthetic MVP work" table were retired in the governance consolidation: their content is in the master's gate entries (section 5) and priorities (section 7), and in git history.

Merged foundations by PR: spec 050 [PR #2](https://github.com/LYF-FC/local-assistant-core/pull/2); 051 [#3](https://github.com/LYF-FC/local-assistant-core/pull/3); 052 [#4](https://github.com/LYF-FC/local-assistant-core/pull/4); 053 [#7](https://github.com/LYF-FC/local-assistant-core/pull/7); 054 [#8](https://github.com/LYF-FC/local-assistant-core/pull/8); 055 [#9](https://github.com/LYF-FC/local-assistant-core/pull/9); 056 [#11](https://github.com/LYF-FC/local-assistant-core/pull/11); 057 [#12](https://github.com/LYF-FC/local-assistant-core/pull/12); 058 [#13](https://github.com/LYF-FC/local-assistant-core/pull/13); 059 [#14](https://github.com/LYF-FC/local-assistant-core/pull/14); 060 [#15](https://github.com/LYF-FC/local-assistant-core/pull/15); 061 programme reconciliation [#16](https://github.com/LYF-FC/local-assistant-core/pull/16); 062 [#17](https://github.com/LYF-FC/local-assistant-core/pull/17); 063 design [#18](https://github.com/LYF-FC/local-assistant-core/pull/18); 064 [#19](https://github.com/LYF-FC/local-assistant-core/pull/19); 065 [#20](https://github.com/LYF-FC/local-assistant-core/pull/20); 066 [#21](https://github.com/LYF-FC/local-assistant-core/pull/21); 067 [#22](https://github.com/LYF-FC/local-assistant-core/pull/22); 068 [#24](https://github.com/LYF-FC/local-assistant-core/pull/24) and corrections [#25](https://github.com/LYF-FC/local-assistant-core/pull/25); 069 [#26](https://github.com/LYF-FC/local-assistant-core/pull/26) and follow-up [#29](https://github.com/LYF-FC/local-assistant-core/pull/29); 070 [#28](https://github.com/LYF-FC/local-assistant-core/pull/28). [PR #27](https://github.com/LYF-FC/local-assistant-core/pull/27) was a Batch 3 design proposal, not an implementation delivery. [PR #1](https://github.com/LYF-FC/local-assistant-core/pull/1) delivered documentation scope reconciliation; the imported baseline has independent [engineering evidence](docs/VALIDATION.md) rather than inherited merged PR history.

## Merged PR17 — scoped daily overview

[Spec062](docs/DAILY_OVERVIEW.md) groups bounded agenda/tasks, owner-private in-app reminders, document text/extraction attention, failure/freshness limits and current-context source navigation. It implements baseline CORE-08/09, UI-01 and ORG-02 foundations without activating live services, new permissions or a separate queue. Global approvals/search/operations and complete MVP journeys remain open. This is independent of the approved later REV/refactoring programme, whose ordering remains after existing scope. PR16 merged its public scope reconciliation; all155 references remain retained.


## FIN-06 reviewed capture contract (spec 063 design, merged PR #18)

[Spec063 financial capture](docs/FINANCIAL_CAPTURE.md) defines owner-private goals, dated assumptions, recorded existing plans and source references before implementation. Server-validated types, unknown/forecast distinctions, record-only plan acknowledgement/reset and export/forget/recovery must be demonstrated together. This design batch changed no runtime status or milestone. Basic finance stayed open at that time, alongside the other live/provider/operations/host acceptance gates. No deferred REV feature is brought forward.


## Merged PR19 — financial storage and lifecycle

[Spec064](docs/FINANCIAL_REGISTER_API.md) implements the approved FIN-06 capture contract's server boundary: typed owner-private records, dated basis/source, plan acknowledgement/reset, quota/concurrency/audit, JSON/Markdown/history export and forgetting/recovery. Financial UI is the following phase of this existing scope; no new design-only substitute or full FIN-06 completion is claimed. Later calculations/imports/providers and deferred review scope stay open. PR18 design, PR19 server delivery and PR20 financial UI are merged.


## Merged PR20 — financial capture UI

[Spec065](docs/FINANCIAL_UI.md) groups typed owner-private capture/correction, unknown-versus-zero/forecast labels, recorded-plan acknowledgement/reset, history, bounded validated JSON/Markdown copies, forgetting and ephemeral privacy/conflict handling. It reuses merged PR19 APIs without backend/schema/grant changes. FIN-06 now has a merged partial server foundation; the dashboard records the merged UI evidence separately from full acceptance and retains all later modelling/import/provider/host requirements. The approved deferred review programme remains after existing scope/later stages.


## Merged PR21 — MVP operations foundations

PR20 merged the financial capture UI. [Spec066 operations overview](docs/OPERATIONS_OVERVIEW.md) now groups explicit service/configuration observations, runtime version inventory, current-actor technical job statuses and private failure/freshness handling for existing OPS-09/RND-01. PR21 is merged engineering, not full operations acceptance. OPS-10 audit/reporting remains open without broadening audit access. The next retained MVP gaps include unified approvals/search, measured service/worker/backup/capacity monitoring, bounded live-adapter engineering, real local-model quality, outage/restart and independent host/key/archive recovery acceptance. Integrations, private adoption and production activation still require separate authorization; original later/deferred scope is unchanged.


## Merged PR22 — scoped task and document search

[Spec067](docs/SCOPED_RECORD_SEARCH.md), merged in [PR #22](https://github.com/LYF-FC/local-assistant-core/pull/22) after PR21 bounded operations foundations (full monitoring/audit/host gates remain), groups keyword search over existing task/document APIs, separate paging/partial failures, current-source validation and source-view navigation with ephemeral privacy. This advances existing CORE-08/UI-01 without new scope, provider or model. Pending approvals, broader/semantic search, measured monitoring/audit, adapter engineering and whole-MVP/outage/independent recovery remain retained next dependencies; real activation/private adoption remain separately authorized.

