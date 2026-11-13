# Product scope

Local Assistant Core is a local-first assistant for private/shared household and professional records. It remembers confirmed context, coordinates routines, retrieves evidence and proposes or executes only bounded authorized actions. Structured records remain authoritative; models are replaceable capabilities. The complete agreed scope includes the everyday MVP and the later domain/extension work below. A short roadmap is an ordering view, never a reduced product contract.

## Reading and authority

- [**Project master**](../PROJECT_MASTER.md): authoritative scope summary, MVP gates, delivery status, outstanding work and priorities.
- [Complete feature register](FEATURE_REGISTER.md): all 155 current references (the 149-reference baseline plus six approved deferred supporting bundles), bounded evidence and remaining acceptance.
- [Dependencies](FEATURE_DEPENDENCIES.md): prerequisites for every register ID.
- [MVP acceptance](MVP_ACCEPTANCE.md): measurable everyday outcomes and release gates.
- [Reconciliation](SCOPE_RECONCILIATION.md): overlaps, supersessions, alternatives and unresolved decisions.
- [Roadmap](../ROADMAP.md): dependency-aware batches and later stages (a sequencing view; status is in the master).
- [Validation](VALIDATION.md) and [readiness](V0_1_READINESS.md): demonstrated engineering versus outstanding operational acceptance.

Precedence, highest first: the [constitution](../.specify/memory/constitution.md); explicit owner-approved decisions (which must be reflected in the [project master](../PROJECT_MASTER.md)); the project master; the register; MVP acceptance; then specs and feature contracts. Architecture and operational procedures keep authority over their own subjects (full statement in the master's introduction). Feature specs refine these requirements; they cannot silently discard them. Before affected work, reconcile the detailed contract, preserve acceptance and record any duplicate, superseded proposal, private configuration or required owner decision. Personal requirements and historical evidence remain privately retained; they are not shipped as defaults. The public register is a generic projection, not proof of sentence-by-sentence semantic deduplication.

## Everyday MVP

Two adult identities use explicit shared/private spaces, controlled memory, local text conversation in French/Spanish/English and a responsive desktop/mobile interface over private access. A user sees an agenda/briefing, asks about an authorized document, adds a deterministic reminder and forwards an invoice. Local extraction proposes filing; human review confirms the result; original references and audit survive restart; failures support safe retry. Include calendar read/reconciliation, general recurring routines, one explicitly authorized external notification path, a dedicated inbox, bounded PDF/OCR, durable archive/search, scoped local-model cited answers, basic manual financial goal/source capture, operational inventory/status and tested clean-host recovery. Calendar writes follow separate ownership/conflict acceptance. Full acceptance is still open.

## Reusable private installations — owner-approved extension

[INSTALL-01–12](CONFIGURABLE_INSTALLATIONS.md) add reusable household installations, private versioned configuration, secure onboarding, stable installation-local identities, credential provisioning, safe templates, feature activation/dependencies, tested updates and explicit legacy conversion. Each household supplies its own reviewed hardware and keeps its database, records, secrets, storage and backups independent. No public shared-data service is introduced.

Feature controls are not permission grants: identity, authorization, audit and recovery remain mandatory foundations. Disabling a feature stops its active behavior safely without silently deleting records or bypassing export/recovery obligations. Current fixed example scopes remain implemented behavior until a separately reviewed migration supports configurable household members; this planning addition changes no schema or runtime.

This is a prerequisite for private installation adoption and a usable reusable-installation release. Design begins before new hard-coded household assumptions spread; bounded independent document work can continue. Complete onboarding, migration and lifecycle acceptance before converting existing private data. See the [acceptance contract](CONFIGURABLE_INSTALLATIONS.md#acceptance).

## Retained later scope

| Stage | Retained outcomes | Register families |
|---|---|---|
| Household and food | Multi-location stock, batches/expiry, child/adult/emergency supplies, transfers, grocery-order intake, shopping, recipes, food references and portable exports | HOME-01–11; DOC-04–07 |
| Care and coaching | Parent-managed timeline, food/allergens, meal composition, growth/development, medicines/vaccines, consented adult health imports, personal/shared exercise and consultation exports; unknown is distinct from negative | CARE-01–09 |
| Connected life | Equipment/maintenance, environmental monitoring, allowlisted home actions, travel/preparation/checklists/memories, supervised music/catalogue/playlists/device delivery, script repair and expanded operational audit | ORG-04–07; DOC-05–08; OPS-01–10 |
| NOMAD and education | Independent offline appliance/library, constrained attributed bridge, FR/ES/EN resources, concept-level curriculum comparisons and gentle parent-managed learning journals | EDU-01–07; EDU-X01–04; NOMAD-X01–03 |
| Professional workflows | Prospect/client/career/shop pipelines, approved outreach, project continuity, debriefs, meetings, reporting/advisory and authorized connectors under strict Work isolation | WORK-01–07; WCOMP-01–04 |
| Creative production | Local metadata/sidecars/catalogues, approved references, scoped style memory, first assemblies, reviewable editing/audio/color suggestions, validated correction learning and versioned workflows | WORK-08–10; CREATIVE-01–07; CREATIVE-X01 |
| Financial planning | Verified consolidation, goals, long-term trajectories, policy/portfolio oversight, deterministic scenarios/stress tests, structure/property/cost/financing research, opportunity/decision continuity and review packs | FIN-01–17 |
| Platform evolution | Optional licensed voice, per-service lifecycle research, bounded Discovery collectors/digests, privacy-first aggregate mail-authentication monitoring and separately governed external-model research/gateway | CORE-12; RND-01–05; DISC-01–03; DMARC-01–02; AI-01–03 |
| Supported service and measured scale | Accepted reliability/capacity, access review, maintained backups, independent restoration, upgrade/rollback and only measured worker/standby scaling | PLATFORM-01–04; MVP-01–05 |

## Shared contracts and exclusions

FastAPI/PostgreSQL/React remain the baseline. Windmill is the intended deterministic orchestrator; Home Assistant owns physical automation; NOMAD remains separate. Synology is the intended durable archive/backup layer, with local substitutes for development; PostgreSQL runs on local storage. Native acceleration is evaluated separately from portable platform containers. No alternate stack, agent framework, vector store or cluster scheduler becomes mandatory merely because it was investigated.

Records carry stable IDs, owner/workspace, source, timestamp/timezone, version, corrections and retention category. Exports preserve provenance; derived indexes are rebuildable. Current identity and owner checks apply to search, answers, history, exports and connectors. Technical administration is not content access. Jobs use durable state, bounded retries, idempotency and reconciliation for ambiguous external outcomes. Approval binds the actual payload/action/recipient and expires when relevant inputs change. Untrusted document/model text cannot grant authority.

Household scopes are `household_shared`, `member_a_private`, `member_b_private`, `parents_child`, `member_business`, `finance_private`, `technical_admin`. Work uses the separate `work_private` registry, with independent grants and recovery controls; it is not an eighth household scope. Fresh generic schemas do not authorize conversion of existing private data.

Autonomous transfers/trading, medical decisions, legal commitments and unapproved high-impact communications remain excluded from action authority. No silent cloud-model fallback, general production shell or automatic media monitoring. External AI stays disabled; any future exception requires the constitution's scoped policy and separate authorization. Real calendar/mail/NAS/messaging/Work sources, production activation and private-data migration each need separate authorization. Development and evidence use synthetic data only.

## Task-specific LLM and dense/MoE investigation

RND-04/05 add [model research](LLM_RESEARCH.md) within service R&D and product innovation. Investigate whether conversation, coding, cited answers and extraction benefit from different local models, comparing against a single general-model/deterministic baseline. Separately compare dense and sparse MoE architectures on actual supported hardware, measuring quality, memory, context, speed, concurrency, switching and operational cost. Application task routing and a model's internal experts are different mechanisms. No specialist model, MoE runtime, download, remote fallback or deployment is selected by this scope. Use synthetic bounded experiments and existing feature/configuration/permission boundaries; multiple models are not an unconditional MVP requirement.


## Approved deferred review and refactoring

[The programme contract](DEFERRED_REVIEW_PROGRAMME.md) retains all 149 original review assessments plus shared/whole-product improvements and REV-01–06 (former A–F). It follows implementation of the existing scope and later stages. Original 99 product-feature counts remain separate; no existing outcome or permission boundary is lost through consolidation. This approval changes planning, not current runtime/data access or live/production/private-migration authority.
