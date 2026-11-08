# Roadmap

The [scope](docs/SCOPE.md), [149-entry register](docs/FEATURE_REGISTER.md), [dependencies](docs/FEATURE_DEPENDENCIES.md) and [MVP acceptance contract](docs/MVP_ACCEPTANCE.md) define the retained product scope. This page orders delivery; brevity here does not remove requirements. Historical versions are dependency stages, not dates, PR quotas or evidence of a released MVP. Version fields of 0.1.0 in package manifests do not establish release acceptance.

## Delivery Kanban

| State | Capability / next evidence |
|---|---|
| Merged foundation | Spec 050 local original archive ([PR #2](https://github.com/LYF-FC/local-assistant-core/pull/2)); authoritative database originals retained. |
| In progress | Spec 051 bounded PDF ingestion: isolated local text extraction, exact originals, review/provenance, page citations, retry and recovery. |
| Next | Separately bounded OCR and uncertain structured extraction, followed by reviewed intake/filing foundations. |
| Next by dependency | Scoped local answers; calendar/briefing; recurrence/one notification path; forwarded invoice intake/filing; operations and independent recovery. |
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
