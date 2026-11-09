# Critical feature and product review

Review of all **99 original product features and 50 supporting references**, based on merged main `33a3b91679066b788e23cc5df2f61ae6c34ab1db` (PR #13). This is a product/scope/dependency review, not certification of every implementation or a new security/code audit. The [register](FEATURE_REGISTER.md), [detailed reconciliation](SCOPE_RECONCILIATION.md) and [MVP acceptance](MVP_ACCEPTANCE.md) remain authoritative. Private household values/history stay outside Git.

**Bottom line of the assessment:** the vision is coherent, but the inventory is not 99 independent modules, and implementation breadth currently exceeds everyday end-to-end acceptance. Keep the agreed outcomes; reduce duplicate machinery and close useful workflows before adding optional platforms. The largest delivery risk is an expanding collection of safe synthetic foundations that never becomes a usable daily assistant.

## What the counts do and do not mean

Merged main now has **17/99 partial foundations, 82 planned/not yet evidenced and 0 full retained feature contracts accepted**. Across all 149 references: 33 partial, 116 planned. There are nine merged public feature batches after the imported baseline. These are different units of progress, not interchangeable completion percentages.

A broad feature can span MVP and later expansions. Accept a bounded MVP through its actual MVP gates; do not require every distant extension to finish first. Conversely, do not call a broad feature complete because a bounded slice or synthetic adapter passes. Future progress reporting should show: (1) delivered engineering slices, (2) accepted user journeys for the intended installation, and (3) full retained feature scope. Planned/not evidenced does not establish that no code exists. Test counts measure verification volume, not usefulness or percent complete.

## Overall critique

1. **Stop treating every row as a subsystem.** Identity, source/provenance, task/routine, notification, asset, decision and controlled-adapter contracts recur throughout. Share implementation primitives while keeping domain data, permissions and acceptance distinct. This does not imply a universal JSON record, global memory/index or microservice/agent per feature.
2. **Close vertical workflows.** The invoice path now has originals, PDF/OCR, field review, non-executable plans and offline mail lineage. It still lacks a live restricted source and authorized destination/effect reconciliation. Another preparatory store will not close MVP-03. The calendar has the same normalized-snapshot versus live-source gap.
3. **The usable interface lags the foundations.** UI-01 already requires a unified attention/review inbox. Surface conflicts, failed/unknown actions, stale sources and the next safe step. Consolidate review ergonomics where safe: a receipt can bind source/field/plan review, but actual external execution still requires its own current exact-action authority. Measure accepted task flows, not only responsive layout.
4. **Configuration/onboarding is not a cosmetic later feature.** Fixed sample members/scopes are acceptable fixtures, not a reusable installation model. Begin INSTALL identity/configuration/readiness before more adapters encode household assumptions. Feature activation, content grants, secret readiness and job lifecycle are separate controls.
5. **Keep vendor preferences, generalize contracts.** Retain requested first integrations and appliance behavior; place them behind source/device/export adapters. MailPlus, Apple calendars, players, health providers, commerce and editors remain feasibility targets until tested. This review makes no new claim about their current APIs, availability or licensing.
6. **Do not overbuild AI infrastructure.** One evaluated local model plus deterministic records/parsers is the first baseline. Specialists, MoE, distributed inference and a remote gateway are conditional research, not mandatory MVP platforms or shortcuts around missing user journeys. No model download, benchmark, private-data transfer or activation is authorized here.
7. **Domain timing should follow value as well as historical versions.** Low-friction capture, everyday triage and configurable household identity are near-term priorities. An optional dependent-care or asset/reminder slice may be more time-sensitive than later research/creative automation, but moving it into MVP requires an explicit scope decision. Preserve every later outcome and existing version label meanwhile.
8. **Some present limits need real usability evidence.** 128 KiB originals, two-page OCR, narrow label extraction and the strict offline MIME subset can exclude intended inputs. Test a rights/privacy-reviewed representative corpus and failure handling before changing bounds; do not silently enlarge parsers. Exact email hashes and issuer/number hints do not establish semantic duplicates or exactly-once filing.
9. **Forgetting needs one understandable contract.** Current scrubbing, retained replay fingerprints, old dumps/WAL, keys and downloaded exports have different guarantees. Preserve the disclosed tombstone trade-off, but make the policy understandable across domains and prove older-restore handling. More per-module forget buttons are not evidence of complete deletion/recovery.
10. **Versions are ordering labels, not a delivery estimate.** Keep the existing v0.1–v0.9 stages, v1.0 supported-service gates and v1.1+ evidence-driven scale. Do not invent v1.2 allocations. The 99 rows vary enormously in size and overlap; neither rows nor PRs are a sensible time estimate.

## Shared implementation map — overlaps, not scope deletions

Each row names a proposed implementation home, preserving all listed requirement references and their distinct acceptance. No canonical ID is removed or superseded by this review.

| Shared implementation home | Overlapping references | Boundary that must stay distinct |
|---|---|---|
| Installation-local identity, relationships and explicit grants | CORE-01, CORE-04, INSTALL-05, INSTALL-06, PLATFORM-04 | Identity/relationship is not permission; onboarding is not legacy conversion. |
| Source, audit, export and retention kernel contracts | CORE-02, CORE-03, CORE-05, DOC-X02, PLATFORM-01–03 | Domain stores/history remain authoritative; export is not clean-host recovery or universal erasure. |
| Attention/search/briefing projections | CORE-08, UI-01, ORG-02, MVP-02, OPS-09 | No second agenda/queue or cross-scope search authority. |
| Task/routine and notification policies | ORG-03, REM-01, CORE-11, CORE-13, CARE-08, DOC-07, DOC-08 | Calendar import recurrence, plans, completion evidence and external delivery are different states. |
| Document intake/derivation/review | DOC-01–03, DOC-X01, MVP-03, HOME-07 | Raw email privacy, attachment truth, ordered versus received stock and authorized file effect differ. |
| Reviewed file-change manifests | DOC-04, OPS-04, CREATIVE-X01 | Different libraries/scopes/rights; suspected duplicates cannot authorize deletion. |
| Asset/location/service history | DOC-05, DOC-08, OPS-01, OPS-07, ORG-06 | Equipment identity, sensor observations, credentials and completed interventions differ. |
| Inventory ledger and projections | HOME-01–07, HOME-11 | Lots, orders, receipts, transfers and consumption cannot be collapsed into one count. |
| Care observations and disclosure/export | CARE-01–09, CORE-03 | Observation, interpretation, prescription, reminder and administration remain distinct; no clinical authority from a shared store. |
| Offline resource/curriculum/journal contracts | EDU-01–07, EDU-X01–04, NOMAD-X01–03 | Independent appliance availability, resource access and household-private learning observations remain separate. |
| Scoped people/projects/opportunities/decisions | WORK-01–07, WCOMP-01–04, FIN-12, FIN-15 | Shared schemas do not merge career, employer, business or household records. |
| Creative reference/proposal/correction/version flow | WORK-08–10, CREATIVE-01–07, CREATIVE-X01 | Metadata, style preference, project constraints, export approval and publication permission differ. |
| Reconciled finance/scenario/decision engine | FIN-01–17, CORE-03, CORE-05 | Actuals, forecasts, policy, property estimates and financial actions remain distinct. FIN-02/07 are not two engines. |
| Service/content lifecycle and bounded collection | RND-01–05, DISC-01–03, OPS-07, OPS-09, OPS-10, EDU-07 | Installed-service research, product Discovery and content updates have different purpose/consent. |
| Real effect and refusal boundary | PLATFORM-01, CORE-04, AI-01–03, OPS-02, WORK-03 | No generic authority promotion: sending, devices, filing and remote inference need exact capability-specific policy. |
| Mail-authentication reports | DMARC-01, DMARC-02 | Reuse acquisition limits where useful; aggregate security reports are not general mailbox collection or DNS administration. |

## Missing, or already present?

The following are **already covered** and must not be added again merely under a new title:

| Apparent gap | Existing scope | Recommendation |
|---|---|---|
| Unified inbox, approval/failure review and explanations | UI-01, CORE-04/05/08, OPS-10 | Prioritize and complete the projection; do not create another inbox database. |
| Backups, restoration and old-copy resurrection | MVP-05, PLATFORM-02/03, DOC-X02, INSTALL-10/11 | Complete the existing whole-installation/older-restore acceptance. |
| Configurable household members and optional features | INSTALL-01–12 | Implement the agreed foundation; do not rename fixed fixtures and claim onboarding complete. |
| Warranties, renewals, contracts and maintenance reminders | DOC-05/07/08, ORG-03 | Link sourced obligations/assets to the common task engine. |
| Provider/model interchangeability and local-first outage behavior | CORE-06/07/10/12, MVP-04, RND-04/05, AI-01–03 | Keep the local baseline and explicit failure; no automatic remote fallback. |
| Preference/correction feedback and provenance | CORE-02/05, DISC-01, CREATIVE-02/06, FIN-17 | Generalize the correction contract while preserving scope-specific meaning. |
| Per-person languages, timezones and installation settings | INSTALL-02/05, EDU-X02, ORG-01/03 | Make these consistent shared contracts; retain initial FR/ES/EN acceptance. |
| Isolated professional records and licensed tooling | WCOMP-02/04, CREATIVE-X01, constitution | Finish isolation/rights/recovery evidence; do not infer access from expressed interest. |

### Candidate gaps requiring an explicit owner decision

These are **proposals or under-specified cross-cutting refinements**, not newly approved feature IDs. They are excluded from the 99/149 totals. Merging this review publishes analysis; it does not approve these additions, move version commitments or authorize implementation/activation.

| Candidate | Evidence/coverage distinction | Recommendation and decision needed |
|---|---|---|
| A · Scoped contacts and service relationships | WCOMP-01/WORK-02 cover professional people/organizations; assets/care/calendar imply other relationships. A reusable household/service-contact contract is not explicit. | Consider a minimal scoped person/organization/contact reference with provenance and consent. Do not build a global address book, infer identity from email or merge private relationships across contexts. Decide whether this is a shared refinement or a new requirement. |
| B · Membership departure, temporary delegation and access expiry | INSTALL-05/06 cover flexible identities/roles; guest/caregiver expiry and offboarding transitions are not explicit acceptance cases. | Add deliberate lifecycle cases to identity design: grant expiry/revocation, record ownership/export and queued-action invalidation. No emergency/admin bypass or automatic transfer from a relationship. Policy needs owner choice before implementation. |
| C · Accessibility and interruption-friendly use | CORE-09/UI-01/INSTALL-12 cover mobile/usability, but keyboard/screen-reader/large-text and interruption recovery are not explicit acceptance. | Propose these as quality criteria on the existing UI, not another app. Include low-friction capture, clear unknown/failure state and recovery from abandoned forms. Agree representative tasks/devices before numerical targets. |
| D · Standing automation rule lifecycle | Preserved intake intent includes established-rule auto-filing; CORE-04/11 and PLATFORM-01 supply controls, but user-facing rule versioning/simulation is not a clear product contract. | Before recurring real effects, specify owner/trigger/conditions/capabilities/budget, preview, pause, change history and why a rule fired. Reuse the intended orchestrator and current authority; do not introduce another workflow platform or imply this is MVP-delivered. |
| E · Consented emergency/custodian continuity | Recovery/checklists/care exports exist; a deliberately selected offline continuity pack and unavailable-owner policy are not explicit. | Consider an optional minimal pack using existing scoped exports. Define exactly who may see which records and how it stays current. No default break-glass access to private health/finance/work or automatic legal/medical authority; this is not automatically MVP scope. |
| F · Cross-feature attention/resource budgets | PLATFORM-02, RND and AI cover capacity/budgets individually. Shared priorities under competing storage/inference/job/notification load are not a unified owner-facing contract. | Refine existing capacity/readiness controls with declared resource/attention limits, observable pauses and deterministic-service priority. Measure before choosing limits; do not build a cluster scheduler or silently spend on external providers. |

The private source review found explicit coverage for caregiver attribution, established incoming rules and extensive retention/recovery, but no explicit accessibility or temporary-access lifecycle acceptance. That is evidence of **under-specification**, not proof of every possible absence. Private source text and personal prioritization notes remain outside Git.

## Recommended next decisions and delivery order

1. Keep all 149 IDs and existing milestones; accept the shared-implementation map as a proposal for future design, not a deletion/merge of requirements.
2. Prefer the next implementation batch around installation-local identity/configuration/readiness contracts, using independent synthetic households. Then make UI-01 and the manual daily loop coherent, including the still-open basic FIN-06 capture and actionable operations state.
3. Close one real calendar/notification/intake/filing route at a time **only after its separate activation/source authorization**. Measure review friction and outage/retry outcomes; do not add extra synthetic adapters as a substitute for that acceptance.
4. Decide whether a time-sensitive dependent-care/asset slice should run earlier without silently expanding MVP. Keep advanced finance, creative observation, MoE/shared inference and extra channels conditional on usefulness and evidence.
5. Review candidates A–F explicitly. Accessibility and identity-lifecycle criteria are recommended clarifications; a cross-domain contact contract and emergency pack need stronger scope decisions. No candidate is an automatic implementation task from this PR.

## Per-feature review

Verdicts are independent of delivery status. **Keep** = coherent outcome/gate; **Generalize** = retain use case but remove unnecessary fixed assumptions; **Consolidate** = share implementation while preserving IDs and acceptance; **Validate** = feasibility/evidence needed; **Challenge** = cost/priority/boundary needs a decision, not deletion. Every canonical reference is reviewed exactly once below.

### CORE

| ID | Verdict | Critical assessment / recommended boundary |
|---|---|---|
| CORE-01 | Generalize | Essential, but two adults is a test scenario rather than an identity schema. Separate member, dependent and workspace relationships from explicit grants; do not infer access from family roles. Align with INSTALL-05 and INSTALL-06. |
| CORE-02 | Keep | Durable confirmed memory is useful. Keep observations, preferences and approved decisions distinguishable; conflicting or outdated facts need visible correction rather than silent model reconciliation. Reuse provenance/retention contracts without merging Work context. |
| CORE-03 | Consolidate | Portability is a contract of every durable domain, not a separate export product. Standardize stable IDs, source links and paginated histories while allowing domain-specific readable views. Export availability is not full backup recovery. |
| CORE-04 | Keep | Authorization is foundational. Model read, propose, modify and external effect separately; approval must bind the exact action and current authority. Share policy enforcement, not blanket consent, across adapters and INSTALL feature controls. |
| CORE-05 | Consolidate | One audit contract should cover all modules. Keep operational logs separate, avoid private payload duplication, and retain actor/source/version/outcome evidence. A large audit store alone does not provide an understandable explanation to users. |
| CORE-06 | Validate | The desired conversational interface makes sense, but a passage selector is not conversation. Evaluate one local baseline on multilingual daily tasks, refusal and grounding before adding specialists or free-form authority. Keep manual workflows useful without inference. |
| CORE-07 | Challenge | A specialist per domain risks premature agent complexity. Start with a small capability registry and deterministic authorized dispatch; introduce model routing only where measured quality justifies it. Do not make an agent framework an MVP dependency. |
| CORE-08 | Consolidate | A dashboard should answer what needs attention, not collect widgets. Use UI-01 as the unified triage/search surface and ORG-02 as its briefing projection; infrastructure detail belongs behind actionable summaries with current scope filtering. |
| CORE-09 | Generalize | Keep a private mobile-first interface, with iPhone as an initial acceptance device rather than a platform lock. Specify interruption recovery, keyboard/large-text use and selected offline capture separately; responsive layout alone does not prove usability. |
| CORE-10 | Keep | Source-backed document answers are high value. Preserve exact citations and abstention, but test retrieval usefulness beyond lexical matching before calling the outcome complete. Semantic search or synthesis must never broaden permissions or invent evidence. |
| CORE-11 | Consolidate | Notification policy should be shared by reminders, care, maintenance and digests. Separate urgency, quiet rules, recipient identity and delivery outcome; avoid building another notification engine for each domain. Users need quieting and correction controls. |
| CORE-12 | Validate | Voice is optional interaction, not a new authority layer. Begin with explicit push-to-talk, correction and visible recording state; evaluate language quality, latency and commercial licensing before choosing a runtime. Wake-word listening remains a later opt-in. |
| CORE-13 | Generalize | The user outcome is reliable authorized messaging, not one vendor. Retain the requested first proof of concept, but accept an adapter only after identity, inbound authority and ambiguous-delivery tests. Do not implement several channels before one works. |

### ORG

| ID | Verdict | Critical assessment / recommended boundary |
|---|---|---|
| ORG-01 | Validate | A shared calendar is central, but reads, writes and mirroring are different products of the adapter. Complete one authorized read/reconciliation route first; preserve recurrence, zones, deletions and last-good state without treating synthetic snapshots as provider proof. |
| ORG-02 | Consolidate | Briefing overlaps CORE-08 and UI-01. Build one permission-filtered projection over current records, with stale/unknown data visible. Separate recorded obligations from inferred household needs; do not introduce a second authoritative agenda. |
| ORG-03 | Generalize | Keep one routine/task lifecycle for household, maintenance and exercise. Domain-specific completion evidence can differ, but recurrence, pause, exceptions, catch-up and cancellation should share machinery. Imported calendar recurrence is a separate boundary. |
| ORG-04 | Generalize | Preparation is useful even without live routing. Separate deterministic checklists and configured lead times from optional online travel estimates; keep location precision, freshness and collection consent explicit. Avoid continuous tracking as an implied dependency. |
| ORG-05 | Challenge | A mirror creates another copy and conflict surface. Retain it as an optional feasibility experiment after reliable read access; prefer a clearly owned one-way projection before any bidirectional behavior. Do not block the MVP on mirroring. |
| ORG-06 | Generalize | Use configurable places, transitions and reusable checklist templates rather than named homes or one family configuration. Distinguish a reminder from verified physical completion. Share tasks with ORG-03; do not turn checklist text into device authority. |
| ORG-07 | Generalize | Trip journals are distinct from calendar truth and household memory. Use opt-in linked sources and selective imports, preserving provenance and media rights. Keep broad photo/archive scanning out of scope until separately authorized and useful. |

### DOC

| ID | Verdict | Critical assessment / recommended boundary |
|---|---|---|
| DOC-01 | Validate | Restricted intake is valuable, but the current offline MIME subset is not a live mailbox. Exact raw-message hashing will not reconcile changed forwarding envelopes. Prove source rules, attachment ambiguity, cursors and interrupted delivery before provider activation. |
| DOC-02 | Generalize | Use a document-derivation contract with field schemas per document type, not an invoice-only parser platform. Keep original, OCR uncertainty, human decisions and duplicate hints distinct. Measure representative formats and limits before widening automation. |
| DOC-03 | Validate | Filing plans are preparation, not filing. The next execution boundary needs an authorized root, collision policy, exact action consent and retry/crash reconciliation. Preserve original/email lineage; never repurpose an old non-executable plan approval as dispatch permission. |
| DOC-04 | Consolidate | Share file inventory and reviewed change-manifest primitives with music/creative cleanup, while keeping each scope isolated. Preview moves, renames and suspected duplicates with rollback limits. Filename similarity alone must not authorize deletion or a global dedup store. |
| DOC-05 | Generalize | An asset registry should cover equipment and other maintainable items, with configurable locations and source-linked warranties/manuals. It is the shared record behind DOC-08; avoid separate incompatible equipment catalogues for every home domain. |
| DOC-06 | Validate | Manual discovery is a constrained acquisition adapter. Prefer official sourced candidates, type/size checks, exact model matching and user confirmation; a search hit is not a verified manual. Keep ambiguous models and unavailable downloads visible. |
| DOC-07 | Consolidate | Administrative obligations belong on sourced records plus the general task/routine engine. Model due date, renewal rule and unknown completion/payment separately. Avoid another scheduler or automatic subscription/legal commitment; link the relevant document and correction history. |
| DOC-08 | Consolidate | Maintenance books are asset service-history views, not independent equipment databases. Reuse DOC-05 identity and ORG-03 scheduling while preserving intervention evidence, provider details and history. Source service intervals; do not infer completion from a dismissed reminder. |
| DOC-X01 | Consolidate | This reference prevents staging/library behavior being mislabeled durable end-to-end ingestion. Reuse original/version/review/archive contracts across DOC-01/02/03; preserve byte fidelity and source lineage. Do not count each storage refinement as an independent user feature. |
| DOC-X02 | Keep | Managed forgetting, retained replay fingerprints, old dumps/WAL and unmanaged copies have different guarantees. Keep the current tombstone trade-off explicit and define older-restore suppression/key policy. A successful current logical restore does not prove universal erasure or resurrection prevention. |

### HOME

| ID | Verdict | Critical assessment / recommended boundary |
|---|---|---|
| HOME-01 | Generalize | The core is a scoped multi-location stock ledger, not a two-home spreadsheet. Define item identity, units and locations before adding suggestions. Keep household members configurable and prevent professional/private inventories from being silently combined. |
| HOME-02 | Consolidate | Batches and opening/expiry dates extend the stock ledger. Keep unknown dates and distinct lots explicit; first-expiring suggestions must not fabricate shelf life. Corrections should preserve which observation changed rather than overwrite stock provenance. |
| HOME-03 | Generalize | Child supplies are an initial category set, not a second inventory engine. Use configurable dependent-specific items and units, with care data isolated. Do not conflate medicine stock, a prescription and an administration event. |
| HOME-04 | Consolidate | Adult and emergency supplies use HOME-01/02 with category-specific thresholds and review dates. Keep the emergency use case, but avoid parallel counts for the same item. A stock suggestion is not a clinical safety determination. |
| HOME-05 | Keep | Accountable consumption, transfers and corrections are essential before forecasting. Preserve source/destination, units and observed events; never count an order as receipt or treat a forecast as actual depletion. Forecasting can follow reliable manual entry. |
| HOME-06 | Consolidate | Shopping lists should project recorded shortages, planned meals and trips rather than become another stock authority. Explain why an item appears, allow dismissal/quantity correction, and avoid duplicate purchases. Sending an order remains separate authorization. |
| HOME-07 | Generalize | Separate order ingestion from receipt and stock movement. Reuse document/mail provenance with product/unit matching and explicit review; changing vendors should not require a new inventory model. Preserve partial deliveries, substitutions and unknown quantities. |
| HOME-08 | Challenge | A chef assistant is useful only after preferences, explicit constraints and reliable stock exist. Start with explainable suggestions and available recipes; do not infer allergies, medical suitability or exact pantry quantities from model memory. |
| HOME-09 | Keep | A recipe book offers independent manual value before advanced meal planning. Preserve source, license where applicable, versions, ratings and modifications. URL imports need bounded safe acquisition; recipe text must not execute instructions or imply provider access. |
| HOME-10 | Validate | Food quality/seasonality references need dated provenance and a clear meaning of quality. Treat providers as replaceable hypotheses, not guaranteed APIs. Keep uncertain or missing information explicit rather than creating a misleading universal score. |
| HOME-11 | Consolidate | Spreadsheet/CSV views are exports of the ledger, not a second editable source of truth. Reuse CORE-03 portability and unit/source metadata. Any later reimport must reconcile identities and corrections explicitly rather than overwrite database state. |

### CARE

| ID | Verdict | Critical assessment / recommended boundary |
|---|---|---|
| CARE-01 | Generalize | The immediate baby journal can become a configurable dependent-care timeline without delaying the initial use case. Keep observations, caregiver, timestamp and uncertainty distinct; recorded, scheduled and administered are different states. Avoid shipping a personal child profile. |
| CARE-02 | Keep | Introductions and observed reactions deserve structured history and sourced guidance. Separate observed facts from possible interpretation; do not diagnose allergies or infer safe exposure. Keep parent control, restricted access and correction/export paths explicit. |
| CARE-03 | Consolidate | Meal composition is a care-specific view over observations and approved guidance, not a duplicate recipe or nutrition authority. Preserve portions, units and uncertainty. Avoid presenting unsourced model calculations as individualized clinical recommendations. |
| CARE-04 | Validate | Growth/development tracking should show sourced observations and measurement context. Version any reference framework and preserve uncertainty; avoid diagnosis, ranking or invented milestones. Generalize the subject model while keeping age/stage-sensitive interpretation separately reviewed. |
| CARE-05 | Keep | Medicine and vaccine history is high risk and must remain deterministic. Separate prescribed, scheduled, reminded and administered; record actor/source, units and product-specific opening limits. No inferred dose changes or autonomous medical decisions follow from reminders. |
| CARE-06 | Generalize | Health providers are source adapters, not the record model. Prefer consented manual/export routes until account/API feasibility is proven; preserve units, timestamps, duplicates and revoked access. Do not assume direct server access to phone health data. |
| CARE-07 | Generalize | Training support can share observations/goals with explicit consent, but must not merge household health contexts by default. Start from recorded activity and declared constraints; separate coaching suggestions from clinical advice and authoritative measurements. |
| CARE-08 | Consolidate | Exercise routines reuse ORG-03 and CORE-11, with opt-in adherence records and shared/private boundaries. Keep the user outcome without assuming a commercial fitness API. Missing completion data is unknown, not evidence of non-adherence. |
| CARE-09 | Consolidate | Consultation exports are a scoped portability view over care records. Preserve sources, units, corrections and unknowns; support selective disclosure instead of exporting a whole household. Reuse CORE-03 without treating export as clinical validation. |

### OPS

| ID | Verdict | Critical assessment / recommended boundary |
|---|---|---|
| OPS-01 | Generalize | Environmental monitoring should use normalized observations and freshness, with vendor adapters underneath. Keep read-only sensing separate from OPS-02 actions and Home Assistant ownership. A stale reading must not produce false reassurance or an unexplained alert. |
| OPS-02 | Keep | Allowlisted physical actions require stronger current authority and outcome reconciliation than read-only monitoring. Retain Home Assistant as executor boundary; define safe manual fallback and ambiguous-result handling. No general device/shell authority should emerge from conversation. |
| OPS-03 | Generalize | Separate scoped music search from playback commands and device identity. Retain intended player integrations as initial adapters, not universal assumptions. Preserve supported interfaces and current user authorization; finding a track does not authorize device control. |
| OPS-04 | Consolidate | Music cleanup shares DOC-04 manifest/preview/rollback machinery, with music-specific metadata and rights checks. Preserve originals and explicit duplicate ambiguity. Do not silently retag, replace or delete a library from model-generated recommendations. |
| OPS-05 | Challenge | Weekly playlists combine rights, acquisition, curation, scheduling and delivery. Split these boundaries in implementation while retaining the outcome. Prove one licensed/source-approved route and quiet failure reporting before adding recurring downloads or multiple services. |
| OPS-06 | Generalize | Device delivery is an adapter/export format, not a fixed household folder convention. Keep the required player behavior configurable, preview the output and preserve existing files. Unsupported device protocols need feasibility evidence before an implementation promise. |
| OPS-07 | Consolidate | A script catalogue belongs in the operational service/capability inventory with RND-01 and OPS-09. Record ownership, expected effects and secret references, not credentials. Listing a script never makes it safe to execute automatically. |
| OPS-08 | Challenge | Supervised repairs need a proposal/test/release boundary, not a production agent with general shell access. Keep branches, synthetic reproduction, verification and explicit deployment authority. Recovery must remain available if the assistant or repair itself fails. |
| OPS-09 | Consolidate | Operational status should use one service/version/resource inventory and an actionable projection in CORE-08. Show freshness and unavailable dependencies; avoid another dashboard silo. Read-only visibility must not grant access to secrets or host administration. |
| OPS-10 | Consolidate | Operational audit is a quiet reviewed summary over audit/job/access/resource evidence, not another log store. Preserve unknown outcomes and actionable next steps. Separate policy alerts from noisy routine activity and avoid repeating private payloads. |

### EDU

| ID | Verdict | Critical assessment / recommended boundary |
|---|---|---|
| EDU-01 | Keep | Independent offline NOMAD availability is a distinct product boundary, not a Butler database replica. Hardware/toolchain preferences need feasibility evidence and configurable support. Keep direct local use working without Butler, shared inference or internet connectivity. |
| EDU-02 | Generalize | Use a licensed versioned resource catalogue with language, edition, integrity and completeness metadata. Different content systems can share catalogue contracts without identical storage. Offline availability must be tested, not inferred from a listed download. |
| EDU-03 | Consolidate | The bridge overlaps NOMAD-X02 and should have one constrained connector contract. Supported search/retrieval endpoints, attribution and private authentication need verification. Read-only resource access must never expand into household records or unrestricted appliance control. |
| EDU-04 | Generalize | Keep French/Spanish/English as required initial language acceptance, with configurable language expressions per member. Separate vocabulary from conceptual understanding. Do not turn multilingual support into a hard-coded household profile or assume all resources have equivalent translations. |
| EDU-05 | Consolidate | Curriculum comparison uses EDU-X01/03 as its model/source contract. Version official systems and mappings; retain disagreements rather than flatten them into one universal curriculum. The comparison is guidance for parents, not a ranking or diagnostic engine. |
| EDU-06 | Keep | Parent-managed interests, activities and progression are useful, but observation and recommendation must remain distinct. Preserve source and uncertainty; avoid forced completion percentages or inferred deficits. Share the journal contract with EDU-X04, not unrestricted general memory. |
| EDU-07 | Consolidate | Resource maintenance reuses service/content inventory, quotas and update verification while preserving independent appliance operation. Updates need integrity, license and rollback/availability checks. A research recommendation must not trigger downloads or delete an older usable edition. |
| EDU-X01 | Consolidate | This is the shared model behind EDU-04/05/06, not another curriculum application. Version concepts, language expressions, mappings, resources and observations separately; preserve conflicting systems and attribution instead of flattening them into a universal progression score. |
| EDU-X02 | Keep | Pedagogical safeguards are acceptance constraints across learning features. Concept understanding and language vocabulary must remain separate; keep parent agency and avoid ranking/deficit assumptions. Do not count this as another delivered product feature when only a policy document exists. |
| EDU-X03 | Consolidate | Source hierarchy refines EDU-02/05 acquisition and comparison. Keep configured primary systems, official dated provenance and resource licensing explicit. A content collector or model answer must not silently choose a different curriculum authority. |
| EDU-X04 | Consolidate | The gentle journal is the parent-managed observation/interest layer of EDU-06. Preserve privacy, continuity and correctable recommendations without hidden assessment. Generalize stages and moves; do not ship one child's biography or require forced completion metrics. |

### WORK

| ID | Verdict | Critical assessment / recommended boundary |
|---|---|---|
| WORK-01 | Generalize | Opportunity research should use explicit professional profiles and bounded authorized sources. Keep source/date and relevance rationale, with separate household/business context. Do not equate expressed interest with permission to scrape accounts or contact prospects. |
| WORK-02 | Consolidate | The pipeline is a source-linked relationship/opportunity workflow, not another generic memory store. Reuse scoped people/organization references and task follow-up, retaining consent and communication history. Do not automatically merge private contacts across workspaces. |
| WORK-03 | Keep | Drafting, reminder scheduling and sending need separate states and authority. Bind approval to recipient/content/channel and reconcile uncertain delivery; a draft or overdue follow-up never authorizes a send. Reuse messaging policy without sharing credentials across scopes. |
| WORK-04 | Generalize | Use a project/client/deliverable lifecycle that supports the initial studio workflow without hard-coding one business. Link rights, approvals, schedules and invoice references; preserve professional isolation. This is not permission for automatic client publication or financial execution. |
| WORK-05 | Challenge | Portfolio, limited editions and commerce are distinct concerns with different obligations. Retain them, but start with manual records and one verified connector only when needed. Do not make a named shop platform or automatic fulfilment a core dependency. |
| WORK-06 | Consolidate | Career opportunities can reuse scoped pipeline/document-version/follow-up primitives, with distinct private career visibility and lifecycle. Keep CV variants and application evidence; employer/project access does not imply permission to disclose job-search material or send applications. |
| WORK-07 | Consolidate | Continuity overlaps WCOMP-01/03 but spans multiple authorized projects. Reuse sourced decisions, current/next/later state and release evidence, keeping scope isolation. The existing synthetic pilot is a foundation, not an accepted general professional assistant. |
| WORK-08 | Generalize | Photo metadata should use scoped taxonomies and sidecar/export adapters, with uncertainty and creator review. Initial tags are examples, not a universal schema. Keep rights, original files and professional/household classification separate; no background media scan follows interest. |
| WORK-09 | Generalize | Retain the intended editing environment as the first adapter, but define reviewable timeline/interchange outputs independently. Reuse CREATIVE contracts for references, corrections and final approval. Verify supported APIs before promising in-editor automation or learning from real projects. |
| WORK-10 | Validate | A workflow runner should accept versioned allowlisted creative graphs with resource/rights checks, not arbitrary execution. Keep model/plugin compatibility, failure output and original preservation explicit. Adopting a named tool does not authorize new weights, downloads or live media. |

### FIN

| ID | Verdict | Critical assessment / recommended boundary |
|---|---|---|
| FIN-01 | Keep | Consolidation is a deterministic reconciliation foundation. Preserve currency, dates, account ownership and source provenance; distinguish imported observations from corrections and forecasts. Start with restricted manual/import routes before live providers; balances must not depend on model memory. |
| FIN-02 | Consolidate | Ten-year planning overlaps FIN-07 and FIN-10. Use one versioned deterministic scenario engine with explicit assumptions, not parallel calculators. A ten-year view is a configuration/output horizon; separate forecasts from approved facts and preserve reproducibility. |
| FIN-03 | Generalize | Structure analysis needs configurable jurisdictions, dated assumptions and qualified review, not a universal holding-company optimizer. Reuse the finance scenario/evidence engine; preserve unknown taxes/costs and do not turn a comparison into incorporation, advice certification or execution authority. |
| FIN-04 | Generalize | Research is sourced input to decisions, not a trading signal engine. Reuse bounded collection/manual imports with restricted newsletter/account rights and freshness. Keep general market information separate from personalized recommendations and reconciled financial state. |
| FIN-05 | Consolidate | Review packs project selected financial evidence with explicit redaction and recipient context. Reuse CORE-03 export primitives while preserving dates, assumptions and uncertainties. Producing a pack neither certifies professional advice nor authorizes sending it. |
| FIN-06 | Keep | Manual goals and dated assumptions can deliver value before live finance integrations. Separate desired outcomes, confirmed inputs, forecasts and accepted constraints. Keep personal amounts/configuration private; retain later full-model scope without making it the initial capture requirement. |
| FIN-07 | Consolidate | Trajectory is the longitudinal view of FIN-01/02, comparing actual observations with a versioned baseline. Do not build a second ten-year engine. Preserve revisions and explain whether changes came from actual data, corrected assumptions or modelled scenarios. |
| FIN-08 | Keep | An explicit investment policy is a human-approved constraint/decision record. Keep risk, liquidity and horizon assumptions sourced and revisable, with periodic review proposals. It must not create autonomous trading or silently rewrite the strategy when conditions change. |
| FIN-09 | Consolidate | Portfolio oversight reuses reconciled positions/cash flows and the policy record. Distinguish missing prices, valuation dates and imported fees; flag deviations without inventing trades. Advanced monitoring depends on reliable imports, not an independent authoritative portfolio database. |
| FIN-10 | Consolidate | Stress tests are parameterized runs of the same deterministic engine, not free-form model predictions. Version inputs, units, correlations where used and uncertainty. Compare assumptions transparently; do not imply probability or guaranteed outcomes without justified evidence. |
| FIN-11 | Generalize | Property requirements should describe configurable projects, locations, phases and constraints, not a private household's fixed dream. Keep aspirations separate from verified site capabilities and costs. Link the project brief to sourced research and deterministic affordability scenarios. |
| FIN-12 | Consolidate | Property research is a typed sourced opportunity pipeline with versioned criteria and unresolved due diligence. Reuse FIN-15/project links without merging private data indiscriminately. Keep collection on demand unless a specific source/cadence is authorized. |
| FIN-13 | Consolidate | Whole-project costing shares the scenario engine, with explicit phases, one-off/recurring costs, contingencies and provenance. Avoid double-counting transactions or treating an estimate as a quote. Affordability needs reconciled household assumptions and reviewed unknowns. |
| FIN-14 | Validate | Financing comparison needs dated terms, fees, repayment assumptions and uncertainty, plus qualified review where required. Reuse project/cash-flow modelling. No lender contact, eligibility promise or application follows from storing an option or approving a comparison. |
| FIN-15 | Generalize | Use one scoped opportunity/decision pipeline with typed investment/property ideas, not another unsourced recommendation feed. Retain accept/reject/revisit rationale and verification state. An opportunity record never implies return certainty, provider access or transaction authority. |
| FIN-16 | Consolidate | The goal dashboard is a projection of reconciled state, approved goals and scenarios. Define each metric, valuation date and uncertainty; do not invent an independent financial-freedom score. Keep missing inputs visible and link every conclusion to reproducible evidence. |
| FIN-17 | Consolidate | Decision continuity belongs in the common sourced decision/correction contract, with finance-specific assumptions and policy binding. Preserve why a strategy was approved and what changed. A change alert proposes review; it cannot replace human strategy or execute money movement. |

### CREATIVE

| ID | Verdict | Critical assessment / recommended boundary |
|---|---|---|
| CREATIVE-01 | Keep | An approved reference library is the legitimate basis for style assistance. Preserve rights, project context, creator annotations and original links. Voluntary selection is not permission to scan a whole archive or copy professional references into household memory. |
| CREATIVE-02 | Generalize | Model preferences by project/client/general scope and explicit versioned confirmation. Separate deliberate style from source constraints or one-off client settings. Reuse preference provenance, but avoid one global style profile that contaminates different creators or commercial work. |
| CREATIVE-03 | Challenge | Learning from workflow observation has a high privacy/cost surface. Start with voluntary project exports and explicit feedback, not continuous recording or keystrokes. Any observation mechanism needs a new bounded opt-in contract and a demonstrable benefit. |
| CREATIVE-04 | Keep | A first assembly is a useful bounded deliverable if source selection, brief, constraints and references are explicit. Preserve originals and editable versions. Treat selects/order as a proposal; unsupported editor APIs should fall back to reviewable interchange. |
| CREATIVE-05 | Consolidate | Reviewable editing suggestions extend the assembly/reference workflow rather than form another autonomous editor. Explain departures from prior style and preserve project-specific context. Audio/color claims need actual technical validation; suggestions cannot overwrite approved media or versions. |
| CREATIVE-06 | Validate | A changed edit is not automatically a general preference. Ask when intent is ambiguous, scope validated feedback correctly and retain correction history. Measure whether learning improves later proposals without leaking client/project style or retaining covert observations. |
| CREATIVE-07 | Keep | Preservation and final creative approval are essential gates, not a publishing permission. Bind the approved version/export and keep original/project recovery viable. Client delivery, upload or publication must retain separate explicit recipient/channel/action authorization. |
| CREATIVE-X01 | Consolidate | Interchange/API feasibility and reopenable project/original recovery are acceptance of WORK-09 and CREATIVE workflows. Prefer reviewable outputs when an editor API is insufficient. Final creative approval is distinct from client delivery/publication and commercial-rights clearance. |

### MVP

| ID | Verdict | Critical assessment / recommended boundary |
|---|---|---|
| MVP-01 | Keep | This is an everyday outcome test, not another feature to implement. Track complete user journeys and failure recovery, including actual host/provider acceptance. Passing many component tests does not close this gate or justify a percentage-complete claim. |
| MVP-02 | Consolidate | Calendar integrity is acceptance of ORG-01 and its briefing projection, not a second calendar subsystem. Keep conflicts, cursors, recurrence and retries visible. Synthetic normalized windows cannot certify a specific live provider's read/write semantics. |
| MVP-03 | Keep | Retain the complete invoice journey: original/email provenance, reviewed fields, destination and exactly-once effect. Current offline intake and non-executable plans leave substantial gaps. Test changed forwarding envelopes and crash boundaries before claiming duplicate-safe live filing. |
| MVP-04 | Keep | Offline/model-failure acceptance is cross-cutting and should be tested on whole journeys. Distinguish local availability from queued external effects and stale snapshots. No silent remote fallback, replay of old intent or implied external success is acceptable. |
| MVP-05 | Keep | Independent clean-host recovery is a release gate, not another logical-dump test. Include keys, originals, configuration and restored authority quarantine, with measured owner-approved targets. Existing synthetic recovery evidence is valuable but cannot substitute for that rehearsal. |

### PLATFORM

| ID | Verdict | Critical assessment / recommended boundary |
|---|---|---|
| PLATFORM-01 | Consolidate | Share bounded adapter/job contracts across domains instead of creating an executor per feature. Keep intent, approval, idempotency and observed outcome distinct, especially after uncertain delivery. A synthetic/no-op handler does not prove a real integration is safe. |
| PLATFORM-02 | Keep | Capacity, failure visibility and recovery targets need measured acceptance rather than attractive defaults. Define resource budgets and action thresholds before adding standby workers. Keep operational targets configurable and do not infer reliability from green CI or container health. |
| PLATFORM-03 | Keep | Separate source engineering, merged-main verification, real host/provider evidence and supported production. A release manifest should state exactly what is accepted. Do not require every distant domain to be finished before accepting a bounded MVP, or certify it prematurely. |
| PLATFORM-04 | Keep | Legacy adoption is a distinct operator decision with private mappings and rehearsed rollback. Sharing source code never permits blind database/history merges or inferred identity matching. Keep the current private deployment untouched until that separate acceptance succeeds. |

### UI

| ID | Verdict | Critical assessment / recommended boundary |
|---|---|---|
| UI-01 | Keep | A unified review/attention inbox is already agreed, not a missing new feature. Prioritize current-user projections of approvals, conflicts, failures, unknown outcomes and stale sources. Reuse domain records/jobs; do not create a new global queue or cross-scope search authority. |

### AI

| ID | Verdict | Critical assessment / recommended boundary |
|---|---|---|
| AI-01 | Challenge | The gateway is optional later scope, not a shortcut around local-model gaps. Require deterministic classification/minimization, exact payload-bound approval, provider controls and bounded egress. Keep protected categories blocked and no silent cloud fallback; research does not activate data transfer. |
| AI-02 | Consolidate | Gateway refusal/response handling is inseparable from AI-01's acceptance boundary. Keep explicit negative tests for modification, expiry, budget and malicious responses. Remote output remains untrusted advice and cannot acquire tool authority or replace structured numerical truth. |
| AI-03 | Validate | Provider evaluation should compare actual local baselines and account-specific controls, not marketing or old benchmarks. Bound research cost and retain negative findings. No vendor recommendation, credentials, model download or private-data test follows from this review. |

### NOMAD

| ID | Verdict | Critical assessment / recommended boundary |
|---|---|---|
| NOMAD-X01 | Keep | The appliance trust/availability boundary is a non-negotiable refinement of EDU-01/03. Keep it independent and prohibit household database/credential replication. Direct offline value must survive Butler/inference outages; a shared network does not imply shared context. |
| NOMAD-X02 | Consolidate | Implement one constrained resource connector with EDU-03, preserving supported endpoints, attribution, authentication and bounded responses. Verify actual capabilities before naming integrations as delivered. Resource search cannot silently become broad appliance administration or private-household retrieval. |
| NOMAD-X03 | Challenge | Shared inference is optional optimization, not a prerequisite for offline resources. Prove meaningful benefit, bounded scheduling and context isolation first. Do not build a distributed model platform merely because two devices exist; independent appliance availability remains mandatory. |

### RND

| ID | Verdict | Critical assessment / recommended boundary |
|---|---|---|
| RND-01 | Consolidate | Service/model/version inventory is shared infrastructure with OPS-07/09 and update acceptance. Keep installed, available, approved and stable states distinct, with provenance/license/support dates. A listed update or advisory never authorizes deployment or weight acquisition. |
| RND-02 | Keep | Bounded evaluation and migration/rollback proposals support maintainability. Require a useful question, resource budget and acceptance evidence before experiments. Retain defer/reject outcomes; research completion does not authorize merge, install or private deployment changes. |
| RND-03 | Consolidate | Proactive lifecycle research reuses source collection/checkpoint/quiet notification primitives, but has an installed-service purpose distinct from product Discovery. Configure cadence and budget explicitly; absence of fresh evidence is stale/unknown, not proof that a service is safe or current. |
| RND-04 | Validate | Task specialization is a hypothesis. Compare a small licensed shortlist with one general local model and deterministic baselines on useful tasks. Require measured gains before extra resident models, routing complexity or a specialist per domain. |
| RND-05 | Validate | MoE investigation must separate total footprint, active parameters, context/cache and runtime behavior from application routing. Keep a negative result valid. Architecture research is neither permission to download weights nor an unconditional MVP dependency. |

### DISC

| ID | Verdict | Critical assessment / recommended boundary |
|---|---|---|
| DISC-01 | Keep | Correctable interest/preference feedback is useful, with rejection, snooze and topic suppression. Separate interest from installation, media access or notification consent. Share preference provenance with memory where appropriate without flattening household and professional profiles. |
| DISC-02 | Consolidate | Use common bounded collection/checkpoint/deduplication primitives with RND-03, while keeping user-facing purpose, scopes and cadence distinct. Start with explicit permitted sources; a digest must not become unsolicited background browsing or a noisy notification stream. |
| DISC-03 | Validate | Photo research should first establish rights, privacy, resource cost and retrieval/classification usefulness. Keep household and professional evaluations separate with synthetic or explicitly approved data. Interest in photo tooling does not authorize an archive scan or model adoption. |

### WCOMP

| ID | Verdict | Critical assessment / recommended boundary |
|---|---|---|
| WCOMP-01 | Consolidate | Debrief continuity refines WORK-07 through reviewable evidence, people/project references and explicit unknown owner/date. Preserve separate observation/proposal/decision states. Voice remains an optional licensed capture adapter, not proof that real professional sources are accepted. |
| WCOMP-02 | Keep | Work isolation is a foundational trust boundary, not an optional module switch. Share software only: keep grants, namespaces/keys/indexes/prompts/jobs/exports/retention separated. Prove bidirectional denial and independent recovery before any real professional adoption. |
| WCOMP-03 | Consolidate | Meeting preparation/reporting/advisory project authorized evidence through the same continuity model. Distinguish what was observed, suggested, approved and actually done. Do not create an unsourced executive-memory silo or treat draft recommendations as commitments. |
| WCOMP-04 | Validate | Real professional connectors require policy, license, account, action and retention acceptance per source. Synthetic pilot success cannot grant employer/client data access. Commercial voice compatibility, original lineage and independent recovery must be proved before activation. |

### DMARC

| ID | Verdict | Critical assessment / recommended boundary |
|---|---|---|
| DMARC-01 | Keep | Aggregate mail-authentication reporting is a bounded admin pipeline distinct from correspondence intake. Reuse safe acquisition/parser budgets where appropriate, not raw mailbox access. Preserve normalization/provenance and reject archive/XML abuse; no DNS changes follow automatically. |
| DMARC-02 | Consolidate | History and quiet anomaly review extend DMARC-01 rather than form another security agent. Calibrate actionable notifications and preserve admin-scoped export/retention. Uncertainty or unusual sources require review, not automatic mailbox/DNS repair. |

### REM

| ID | Verdict | Critical assessment / recommended boundary |
|---|---|---|
| REM-01 | Consolidate | This is baseline/remaining acceptance for tasks, reminders and ORG-03 routines, not another reminder product. Keep fuller recurrence, calendar coupling and one real notification route visible. Do not equate in-app delivery with an external channel. |

### INSTALL

| ID | Verdict | Critical assessment / recommended boundary |
|---|---|---|
| INSTALL-01 | Keep | Independent installations are the right reuse unit: shared versioned software, separate identities/data/secrets/files/jobs/backups. Do not accidentally turn this into a multi-tenant service or synchronization promise. Prove a second synthetic household before claiming portability. |
| INSTALL-02 | Generalize | Move household/provider/hardware assumptions into validated versioned private configuration, not source forks. Keep configuration distinct from operational records and secret references. Missing or incompatible values need actionable failure, never guessed defaults that activate a provider. |
| INSTALL-03 | Keep | Feature readiness and activation must be explicit and authorized, with useful setup/failure states. They do not grant content permissions. Plan this early so new modules do not add inconsistent environment switches or expose unusable controls. |
| INSTALL-04 | Keep | Disable/re-enable behavior is an authority and recovery lifecycle, not just UI visibility. Stop new dispatch, reconcile queued/in-flight ambiguity and preserve records. Security/audit/recovery foundations cannot be disabled as an optional feature or bypassed by dependency resolution. |
| INSTALL-05 | Generalize | Keep the initial household fixture, but implement configurable membership/relationships and explicit roles for independent users. Secure bootstrap and owner recovery need clear policy. Guest, caregiver, departure and access-expiry cases need explicit decisions rather than inferred family authority. |
| INSTALL-06 | Keep | Stable software keys must be distinct from installation-local subjects/workspaces and display names. Preserve cross-reference mapping and refusal of foreign bindings. Do not infer identity, restore ownership or permission from a name, email string or family relationship. |
| INSTALL-07 | Keep | Protected credential provisioning/rotation/revocation is essential before live adapters. Use references and redacted readiness results, with per-installation isolation. Configuration templates and logs must never become secret transport; validation does not imply permission to execute a connector action. |
| INSTALL-08 | Keep | Templates should export only allowlisted non-sensitive configuration, preview changes and mint fresh identities. Reject incompatible graphs without partial grants or provisioning. A reusable template is not a backup or a safe vehicle for private records/credentials. |
| INSTALL-09 | Keep | Cross-installation denial is an acceptance test of shared-code reuse, not another feature count. Include search, answers, jobs, secrets, exports and restore bindings, not just separate logins. No real data is needed to prove the synthetic isolation boundary. |
| INSTALL-10 | Consolidate | Updates share release/configuration compatibility and recovery contracts with PLATFORM-02/03. Preserve private settings, identities and disabled states; never enable providers through an upgrade. Separate source merge, install migration and actual owner adoption with explicit rollback limits. |
| INSTALL-11 | Keep | Legacy conversion is not ordinary onboarding or a Git merge. Keep mappings/private history outside Git, rehearse on isolated copies and verify grants/provenance/tombstones. No operator action follows from generic feature delivery without the separately authorized conversion gate. |
| INSTALL-12 | Keep | Usability acceptance must demonstrate a minimal useful setup and complete feature lifecycle on independent installations. Do not require every optional domain to be configured before first use. Measure owner-facing friction and failure recovery, not only successful provisioning commands. |

## Review coverage and acceptance

All 149 canonical references have one individual assessment: 41 Keep, 31 Generalize, 52 Consolidate, 16 Validate and 9 Challenge. No register/dependency row or approved scope has been removed. Review recommendations do not change implemented status, version assignments, data permissions or activation authority. Snapshot generation and coverage checks must fail on missing/duplicate IDs or unrecognized statuses; privacy and links are reviewed before publication.
