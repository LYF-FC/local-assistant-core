# Feature overview

Snapshot: **12 November 2026**, verified merged main [`8476320`](https://github.com/LYF-FC/local-assistant-core/commit/84763205f335bf368399a95b5f4fa156e603518a) through PR #27. This view does not query CI or certify exact-main/host/provider acceptance.

[Critical review of every feature](FEATURE_REVIEW.md) · [Interactive dashboard — download HTML](FEATURE_DASHBOARD.html) · [Source metadata](FEATURE_PROGRESS.json)

GitHub renders this Markdown summary. It displays HTML as source: download the dashboard and open the saved `.html` in a browser. No Pages hosting, external dependencies, network requests or browser storage are activated.

## At a glance

| Catalog | Full retained contract accepted | Working foundation, partial | Planned / not evidenced | Total |
|---|---:|---:|---:|---:|
| Original named product features | **0** | **19** | **80** | **99** |
| Of those, first-stage MVP | **0** | **18** | **3** | **21** |
| Additional supporting references | **0** | **21** | **35** | **56** |
| Complete retained register | **0** | **40** | **115** | **155** |

**19 of 99 have working foundations; 0 full retained feature contracts are accepted.** This is not a percentage of effort or production readiness. A bounded MVP can be accepted before all later expansions of a broad feature finish; its own user-journey gates must actually pass. Planned/not evidenced does not prove no code exists. The additional supporting references overlap product outcomes, not extra independent deliverables.

Across all 155 references: 40 partial and 115 planned/not evidenced. Review verdicts describe recommendations and never change delivery status or approved scope.

## Existing version plan

A feature is counted once at its first stage; later expansions remain retained. FIN-06 starts with basic MVP capture and expands later. FIN-12/15 start with manual research in v0.7 before advanced finance. Installation, research and release gates span stages. These historical stages are not dates or new promises.

| First stage | Named features | Full retained contract accepted | Partial | Planned / not evidenced |
|---|---:|---:|---:|---:|
| MVP · v0.1–v0.2 | 21 | 0 | 18 | 3 |
| v0.3 · Household & food | 15 | 0 | 0 | 15 |
| v0.4 · Care & coaching | 9 | 0 | 0 | 9 |
| v0.5 · Connected life | 13 | 0 | 0 | 13 |
| v0.6 · NOMAD & education | 7 | 0 | 0 | 7 |
| v0.7 · Professional & research | 9 | 0 | 1 | 8 |
| v0.8 · Creative | 10 | 0 | 0 | 10 |
| v0.9 · Advanced finance & voice | 15 | 0 | 0 | 15 |
| v1.0 · Supported service | — | — | — | Cross-scope reliability/capacity/maintenance/recovery gates; no new named allocation. |
| v1.1+ · Measured scale | — | — | — | Workers/standby only when measurements justify them. |
| v1.2 | — | — | — | No separate scope allocated; do not invent assignments. |

## Delivered building blocks

18 public feature batches have merged after the imported engineering foundation. Documentation PRs are not feature deliveries; building blocks are not added to the original-feature denominator.

| Evidence | Working engineering subset |
|---|---|
| [Imported engineering baseline](VALIDATION.md) | HTTPS accounts/sessions/scopes; Memory and manual Discovery; manual tasks/private in-app reminders; document history/review/export; synthetic Work review/recovery. |
| [PR #2 · Durable originals](https://github.com/LYF-FC/local-assistant-core/pull/2) | Optional local archive and original-byte consistency. |
| [PR #3 · PDF extraction](https://github.com/LYF-FC/local-assistant-core/pull/3) | Bounded isolated PDF text, page/source provenance and review. |
| [PR #4 · Explicit OCR](https://github.com/LYF-FC/local-assistant-core/pull/4) | Bounded uncertain scanned-PDF recognition and review. |
| [PR #7 · Document answers](https://github.com/LYF-FC/local-assistant-core/pull/7) | Scoped exact-quotation answers; optional selector disabled by default. |
| [PR #8 · Calendar & briefing](https://github.com/LYF-FC/local-assistant-core/pull/8) | Normalized synthetic calendar reconciliation and day view. |
| [PR #9 · Recurring routines](https://github.com/LYF-FC/local-assistant-core/pull/9) | Finite daily/weekly plans, generated tasks/private reminders and history. |
| [PR #11 · Invoice review](https://github.com/LYF-FC/local-assistant-core/pull/11) | Bounded candidates, explicit confirmed/unknown decisions, duplicate hints and forgetting. |
| [PR #12 · Filing plans](https://github.com/LYF-FC/local-assistant-core/pull/12) | Logical names/destinations, manual correction and non-executable approval/withdrawal. |
| [PR #13 · Offline email intake](https://github.com/LYF-FC/local-assistant-core/pull/13) | Exact original email/single attachment, private provenance, replay and aggregate forgetting; no live mailbox. |
| [PR #15 · Installation setup](https://github.com/LYF-FC/local-assistant-core/pull/15) | Explicit installation UUID, versioned bounded defaults, reviewed sanitized templates and informational readiness; no activation controls or dynamic membership. |
| [PR #17 · Scoped daily overview](https://github.com/LYF-FC/local-assistant-core/pull/17) | Explicit bounded agenda/tasks, private reminders and document attention with freshness clearing and current-source navigation; full dashboard/live/operations acceptance remains open. |
| [PR #19 · Financial storage/API](https://github.com/LYF-FC/local-assistant-core/pull/19) | Typed owner-private financial records, plan-record acknowledgement/reset, history/export/forget and verified recovery; UI followed in PR20 and full FIN-06 acceptance remains open. |
| [PR #20 · Financial capture UI](https://github.com/LYF-FC/local-assistant-core/pull/20) | Typed owner forms, explicit unknown/forecast/zero, plan review/reset, bounded history/copy/forget and privacy clearing; full financial/MVP/host acceptance remains open. |
| [PR #21 · Operations observations](https://github.com/LYF-FC/local-assistant-core/pull/21) | Protected API/database transaction observations, runtime software metadata and bounded own technical job statuses; configured flags remain unverified, audit review and full monitoring/host acceptance stay open. |
| [PR #22 · Scoped task/document search](https://github.com/LYF-FC/local-assistant-core/pull/22) | Bounded keyword search over existing task and document APIs with independent paging, current-source validation and source-view navigation; no status counts change and pending approvals, broader search and whole-MVP acceptance remain open. |
| [PR #24 · Synthetic notification path](https://github.com/LYF-FC/local-assistant-core/pull/24) | Durable delivery states, quiet hours, day budgets, per-cycle deduplication and bounded retry against a synthetic channel; no real provider, device push or whole-MVP acceptance. |
| [PR #25 · Notification audit corrections](https://github.com/LYF-FC/local-assistant-core/pull/25) | Paused deliveries are parked and history snapshots are fully validated (audit of PR #24); no status count changes. |
| [PR #26 · Synthetic invoice filing execution](https://github.com/LYF-FC/local-assistant-core/pull/26) | A separate single-use exact filing request, single claimant, reconcile-before-retry, no overwrite and scrub-on-forget against a synthetic destination only; no real adapter, original-byte copy or restart proof, and no status count changes. |

## All original named features

Statuses come from the [register](FEATURE_REGISTER.md). Review recommendations link to the [individual assessments](FEATURE_REVIEW.md), while [dependencies](FEATURE_DEPENDENCIES.md), [roadmap](../ROADMAP.md) and [MVP acceptance](MVP_ACCEPTANCE.md) retain their authority.

### MVP · v0.1–v0.2

| ID | Feature | Merged status | Review recommendation | Remaining acceptance |
|---|---|---|---|---|
| CORE-01 | Individual and shared identities | Working foundation · partial | [Generalize](FEATURE_REVIEW.md#core) | Accounts/transport/grants exist; full parent-managed/domain profiles and actual-host acceptance remain. |
| CORE-02 | Durable local memory | Working foundation · partial | [Keep](FEATURE_REVIEW.md#core) | Explicit memory lifecycle exists; broader automatic/coordinator memory is not delivered. |
| CORE-03 | History portability | Working foundation · partial | [Consolidate](FEATURE_REVIEW.md#core) | Bounded feature exports exist; not every future domain/original/full-history portability contract. |
| CORE-04 | Permissions and approval policies | Working foundation · partial | [Keep](FEATURE_REVIEW.md#core) | Permissions and bounded no-op/synthetic approvals exist; real external actions remain gated. |
| CORE-05 | Action and decision audit | Working foundation · partial | [Consolidate](FEATURE_REVIEW.md#core) | Transactional audit foundation exists; future recommendations/connectors/model activity need implementation. |
| CORE-06 | Local conversation | Working foundation · partial | [Validate](FEATURE_REVIEW.md#core) | Scoped lexical evidence and a default-disabled exact-passage selector exist. Real-model quality/activation, multi-turn conversation and free-form synthesis remain open. |
| CORE-07 | Coordinator and specialists | Planned / not evidenced | [Challenge](FEATURE_REVIEW.md#core) | No claim of full delivery; verify exact code and acceptance before promotion. |
| CORE-08 | Home dashboard | Working foundation · partial | [Consolidate](FEATURE_REVIEW.md#core) | Scoped calendar/task/memory day briefing added; complete dashboard/infrastructure/approval integration remains. PR17 adds bounded scoped daily overview, partial/freshness handling and current-source navigation; full retained contract stays open. |
| CORE-09 | iPhone access | Working foundation · partial | [Generalize](FEATURE_REVIEW.md#core) | Responsive HTTPS engineering exists; private remote/mobile owner acceptance is not certified. PR17 adds bounded scoped daily overview, partial/freshness handling and current-source navigation; full retained contract stays open. |
| CORE-10 | Trusted document answers | Working foundation · partial | [Keep](FEATURE_REVIEW.md#core) | Literal excerpts and optional archive copies exist; spec 051 adds reviewed PDF page citations. Spec 052 adds explicit uncertain OCR. Spec 053 adds scoped exact-quotation answers with a default-disabled local selector. Real-model quality/activation, free-form synthesis/conversation, NAS and full archive acceptance remain open. |
| CORE-11 | Proactive notification control | Working foundation · partial | [Consolidate](FEATURE_REVIEW.md#core) | Private in-app quiet/day-budget control and finite routine generation exist; external delivery/proactive summaries remain separately gated. |
| CORE-13 | Messaging adapters | Planned / not evidenced | [Generalize](FEATURE_REVIEW.md#core) | No claim of full delivery; verify exact code and acceptance before promotion. |
| ORG-01 | Shared calendar | Working foundation · partial | [Validate](FEATURE_REVIEW.md#org) | Bounded complete-window synthetic imports/reconciliation; live Apple/iCloud read, recurrence expansion/provider semantics and controlled writes remain. |
| ORG-02 | Daily briefing | Working foundation · partial | [Consolidate](FEATURE_REVIEW.md#org) | Deterministic scoped calendar/task/memory-reference day view; inferred needs, upcoming multi-day planning and live-provider acceptance remain. PR17 adds bounded scoped daily overview, partial/freshness handling and current-source navigation; full retained contract stays open. |
| ORG-03 | Recurring routines | Working foundation · partial | [Generalize](FEATURE_REVIEW.md#org) | Finite daily/weekly plans, atomic generated tasks/private reminders and current completion/lifecycle history; monthly/exception/delegation/calendar and external delivery remain. |
| DOC-01 | Dedicated forwarded inbox | Working foundation · partial | [Validate](FEATURE_REVIEW.md#doc) | Bounded offline original email/single attachment, creator-only provenance and exact-message replay. Live mailbox/source rules, jobs/cursors/recovery and broader intake remain open. |
| DOC-02 | Attachment extraction | Working foundation · partial | [Generalize](FEATURE_REVIEW.md#doc) | Bounded PDF/OCR and invoice candidates, explicit human confirmed/unknown decisions, provenance and scoped duplicate hints advance extraction. Live mailbox lineage and full intake/filing acceptance remain open. |
| DOC-03 | Synology filing | Working foundation · partial | [Validate](FEATURE_REVIEW.md#doc) | Logical folder/name proposals, manual review and non-executable approval/withdrawal reuse original-linked invoice history. Offline email lineage is added by spec 058; spec 069 adds execution against a synthetic destination only; live-source lineage, authorized contained apply/rollback against a real root and real-destination exactly-once recovery remain open. |
| OPS-09 | Infrastructure dashboard | Working foundation · partial | [Consolidate](FEATURE_REVIEW.md#ops) | Authenticated API/database transaction reachability, configured-versus-unknown states, runtime package inventory and bounded own technical job statuses exist. Actual worker/NAS/capacity/backup/certificate/model/remote-hardware observation, independent alerting and full host/MVP acceptance remain open. [Boundary](OPERATIONS_OVERVIEW.md). |
| OPS-10 | Periodic operational audit | Planned / not evidenced | [Consolidate](FEATURE_REVIEW.md#ops) | No claim of full delivery; verify exact code and acceptance before promotion. |
| FIN-06 | Goal and assumption register | Working foundation · partial | [Keep](FEATURE_REVIEW.md#fin) | Typed owner-private dated goals/assumptions/plans/sources, acknowledgement/reset, history/export/forget, recovery and ephemeral owner UI exist. Full goal/progress modelling, reconciled imports and later financial/MVP/host acceptance remain open. [UI boundary](FINANCIAL_UI.md). |

### v0.3 · Household & food

| ID | Feature | Merged status | Review recommendation | Remaining acceptance |
|---|---|---|---|---|
| DOC-04 | File organization audit | Planned / not evidenced | [Consolidate](FEATURE_REVIEW.md#doc) | No claim of full delivery; verify exact code and acceptance before promotion. |
| DOC-05 | Equipment archive | Planned / not evidenced | [Generalize](FEATURE_REVIEW.md#doc) | No claim of full delivery; verify exact code and acceptance before promotion. |
| DOC-06 | Manual discovery | Planned / not evidenced | [Validate](FEATURE_REVIEW.md#doc) | No claim of full delivery; verify exact code and acceptance before promotion. |
| DOC-07 | Administrative deadlines | Planned / not evidenced | [Consolidate](FEATURE_REVIEW.md#doc) | No claim of full delivery; verify exact code and acceptance before promotion. |
| HOME-01 | Multi-location inventory | Planned / not evidenced | [Generalize](FEATURE_REVIEW.md#home) | No claim of full delivery; verify exact code and acceptance before promotion. |
| HOME-02 | Batches and expiry | Planned / not evidenced | [Consolidate](FEATURE_REVIEW.md#home) | No claim of full delivery; verify exact code and acceptance before promotion. |
| HOME-03 | Child essentials | Planned / not evidenced | [Generalize](FEATURE_REVIEW.md#home) | No claim of full delivery; verify exact code and acceptance before promotion. |
| HOME-04 | Adult and emergency supplies | Planned / not evidenced | [Consolidate](FEATURE_REVIEW.md#home) | No claim of full delivery; verify exact code and acceptance before promotion. |
| HOME-05 | Consumption and transfers | Planned / not evidenced | [Keep](FEATURE_REVIEW.md#home) | No claim of full delivery; verify exact code and acceptance before promotion. |
| HOME-06 | Shopping lists | Planned / not evidenced | [Consolidate](FEATURE_REVIEW.md#home) | No claim of full delivery; verify exact code and acceptance before promotion. |
| HOME-07 | Basket/order ingestion | Planned / not evidenced | [Generalize](FEATURE_REVIEW.md#home) | No claim of full delivery; verify exact code and acceptance before promotion. |
| HOME-08 | Chef assistant | Planned / not evidenced | [Challenge](FEATURE_REVIEW.md#home) | No claim of full delivery; verify exact code and acceptance before promotion. |
| HOME-09 | Family recipe book | Planned / not evidenced | [Keep](FEATURE_REVIEW.md#home) | No claim of full delivery; verify exact code and acceptance before promotion. |
| HOME-10 | Food quality references | Planned / not evidenced | [Validate](FEATURE_REVIEW.md#home) | No claim of full delivery; verify exact code and acceptance before promotion. |
| HOME-11 | Inventory exports | Planned / not evidenced | [Consolidate](FEATURE_REVIEW.md#home) | No claim of full delivery; verify exact code and acceptance before promotion. |

### v0.4 · Care & coaching

| ID | Feature | Merged status | Review recommendation | Remaining acceptance |
|---|---|---|---|---|
| CARE-01 | Baby timeline | Planned / not evidenced | [Generalize](FEATURE_REVIEW.md#care) | No claim of full delivery; verify exact code and acceptance before promotion. |
| CARE-02 | Diversification and allergens | Planned / not evidenced | [Keep](FEATURE_REVIEW.md#care) | No claim of full delivery; verify exact code and acceptance before promotion. |
| CARE-03 | Meal composition | Planned / not evidenced | [Consolidate](FEATURE_REVIEW.md#care) | No claim of full delivery; verify exact code and acceptance before promotion. |
| CARE-04 | Growth and development | Planned / not evidenced | [Validate](FEATURE_REVIEW.md#care) | No claim of full delivery; verify exact code and acceptance before promotion. |
| CARE-05 | Medicines and vaccines | Planned / not evidenced | [Keep](FEATURE_REVIEW.md#care) | No claim of full delivery; verify exact code and acceptance before promotion. |
| CARE-06 | Adult health imports | Planned / not evidenced | [Generalize](FEATURE_REVIEW.md#care) | No claim of full delivery; verify exact code and acceptance before promotion. |
| CARE-07 | Personal training | Planned / not evidenced | [Generalize](FEATURE_REVIEW.md#care) | No claim of full delivery; verify exact code and acceptance before promotion. |
| CARE-08 | Shared exercise routines | Planned / not evidenced | [Consolidate](FEATURE_REVIEW.md#care) | No claim of full delivery; verify exact code and acceptance before promotion. |
| CARE-09 | Care exports | Planned / not evidenced | [Consolidate](FEATURE_REVIEW.md#care) | No claim of full delivery; verify exact code and acceptance before promotion. |

### v0.5 · Connected life

| ID | Feature | Merged status | Review recommendation | Remaining acceptance |
|---|---|---|---|---|
| ORG-04 | Travel time and preparation | Planned / not evidenced | [Generalize](FEATURE_REVIEW.md#org) | No claim of full delivery; verify exact code and acceptance before promotion. |
| ORG-05 | Calendar mirror option | Planned / not evidenced | [Challenge](FEATURE_REVIEW.md#org) | No claim of full delivery; verify exact code and acceptance before promotion. |
| ORG-06 | Contextual checklists | Planned / not evidenced | [Generalize](FEATURE_REVIEW.md#org) | No claim of full delivery; verify exact code and acceptance before promotion. |
| ORG-07 | Travel and family memories | Planned / not evidenced | [Generalize](FEATURE_REVIEW.md#org) | No claim of full delivery; verify exact code and acceptance before promotion. |
| DOC-08 | Maintenance books | Planned / not evidenced | [Consolidate](FEATURE_REVIEW.md#doc) | No claim of full delivery; verify exact code and acceptance before promotion. |
| OPS-01 | Netatmo/HomeKit monitoring | Planned / not evidenced | [Generalize](FEATURE_REVIEW.md#ops) | No claim of full delivery; verify exact code and acceptance before promotion. |
| OPS-02 | Controlled home actions | Planned / not evidenced | [Keep](FEATURE_REVIEW.md#ops) | No claim of full delivery; verify exact code and acceptance before promotion. |
| OPS-03 | Music library access | Planned / not evidenced | [Generalize](FEATURE_REVIEW.md#ops) | No claim of full delivery; verify exact code and acceptance before promotion. |
| OPS-04 | Music organization | Planned / not evidenced | [Consolidate](FEATURE_REVIEW.md#ops) | No claim of full delivery; verify exact code and acceptance before promotion. |
| OPS-05 | Weekly playlists | Planned / not evidenced | [Challenge](FEATURE_REVIEW.md#ops) | No claim of full delivery; verify exact code and acceptance before promotion. |
| OPS-06 | Device delivery | Planned / not evidenced | [Generalize](FEATURE_REVIEW.md#ops) | No claim of full delivery; verify exact code and acceptance before promotion. |
| OPS-07 | Script catalogue | Planned / not evidenced | [Consolidate](FEATURE_REVIEW.md#ops) | No claim of full delivery; verify exact code and acceptance before promotion. |
| OPS-08 | Supervised software repairs | Planned / not evidenced | [Challenge](FEATURE_REVIEW.md#ops) | No claim of full delivery; verify exact code and acceptance before promotion. |

### v0.6 · NOMAD & education

| ID | Feature | Merged status | Review recommendation | Remaining acceptance |
|---|---|---|---|---|
| EDU-01 | Independent NOMAD appliance | Planned / not evidenced | [Keep](FEATURE_REVIEW.md#edu) | No claim of full delivery; verify exact code and acceptance before promotion. |
| EDU-02 | Offline knowledge library | Planned / not evidenced | [Generalize](FEATURE_REVIEW.md#edu) | No claim of full delivery; verify exact code and acceptance before promotion. |
| EDU-03 | Controlled Butler bridge | Planned / not evidenced | [Consolidate](FEATURE_REVIEW.md#edu) | No claim of full delivery; verify exact code and acceptance before promotion. |
| EDU-04 | Trilingual learning | Planned / not evidenced | [Generalize](FEATURE_REVIEW.md#edu) | No claim of full delivery; verify exact code and acceptance before promotion. |
| EDU-05 | Curriculum comparison | Planned / not evidenced | [Consolidate](FEATURE_REVIEW.md#edu) | No claim of full delivery; verify exact code and acceptance before promotion. |
| EDU-06 | Learning progression | Planned / not evidenced | [Keep](FEATURE_REVIEW.md#edu) | No claim of full delivery; verify exact code and acceptance before promotion. |
| EDU-07 | Content maintenance | Planned / not evidenced | [Consolidate](FEATURE_REVIEW.md#edu) | No claim of full delivery; verify exact code and acceptance before promotion. |

### v0.7 · Professional & research

| ID | Feature | Merged status | Review recommendation | Remaining acceptance |
|---|---|---|---|---|
| WORK-01 | Prospect research | Planned / not evidenced | [Generalize](FEATURE_REVIEW.md#work) | No claim of full delivery; verify exact code and acceptance before promotion. |
| WORK-02 | Prospect pipeline | Planned / not evidenced | [Consolidate](FEATURE_REVIEW.md#work) | No claim of full delivery; verify exact code and acceptance before promotion. |
| WORK-03 | Outreach and follow-up | Planned / not evidenced | [Keep](FEATURE_REVIEW.md#work) | No claim of full delivery; verify exact code and acceptance before promotion. |
| WORK-04 | Studio/client operations | Planned / not evidenced | [Generalize](FEATURE_REVIEW.md#work) | No claim of full delivery; verify exact code and acceptance before promotion. |
| WORK-05 | Portfolio and print shop | Planned / not evidenced | [Challenge](FEATURE_REVIEW.md#work) | No claim of full delivery; verify exact code and acceptance before promotion. |
| WORK-06 | Career assistant | Planned / not evidenced | [Consolidate](FEATURE_REVIEW.md#work) | No claim of full delivery; verify exact code and acceptance before promotion. |
| WORK-07 | Project continuity | Working foundation · partial | [Consolidate](FEATURE_REVIEW.md#work) | Specifications/dependency CI are foundations, not the authorized project-continuity connector. |
| FIN-12 | Long-term property project research | Planned / not evidenced | [Consolidate](FEATURE_REVIEW.md#fin) | No claim of full delivery; verify exact code and acceptance before promotion. |
| FIN-15 | Opportunity pipeline | Planned / not evidenced | [Generalize](FEATURE_REVIEW.md#fin) | No claim of full delivery; verify exact code and acceptance before promotion. |

### v0.8 · Creative

| ID | Feature | Merged status | Review recommendation | Remaining acceptance |
|---|---|---|---|---|
| WORK-08 | Photo metadata | Planned / not evidenced | [Generalize](FEATURE_REVIEW.md#work) | No claim of full delivery; verify exact code and acceptance before promotion. |
| WORK-09 | Resolve editing assistance | Planned / not evidenced | [Generalize](FEATURE_REVIEW.md#work) | No claim of full delivery; verify exact code and acceptance before promotion. |
| WORK-10 | ComfyUI workflows | Planned / not evidenced | [Validate](FEATURE_REVIEW.md#work) | No claim of full delivery; verify exact code and acceptance before promotion. |
| CREATIVE-01 | Approved reference library | Planned / not evidenced | [Keep](FEATURE_REVIEW.md#creative) | No claim of full delivery; verify exact code and acceptance before promotion. |
| CREATIVE-02 | Editing-style memory | Planned / not evidenced | [Generalize](FEATURE_REVIEW.md#creative) | No claim of full delivery; verify exact code and acceptance before promotion. |
| CREATIVE-03 | Workflow learning | Planned / not evidenced | [Challenge](FEATURE_REVIEW.md#creative) | No claim of full delivery; verify exact code and acceptance before promotion. |
| CREATIVE-04 | First assembly | Planned / not evidenced | [Keep](FEATURE_REVIEW.md#creative) | No claim of full delivery; verify exact code and acceptance before promotion. |
| CREATIVE-05 | Reviewable editing suggestions | Planned / not evidenced | [Consolidate](FEATURE_REVIEW.md#creative) | No claim of full delivery; verify exact code and acceptance before promotion. |
| CREATIVE-06 | Correction learning | Planned / not evidenced | [Validate](FEATURE_REVIEW.md#creative) | No claim of full delivery; verify exact code and acceptance before promotion. |
| CREATIVE-07 | Final approval gate | Planned / not evidenced | [Keep](FEATURE_REVIEW.md#creative) | No claim of full delivery; verify exact code and acceptance before promotion. |

### v0.9 · Advanced finance & voice

| ID | Feature | Merged status | Review recommendation | Remaining acceptance |
|---|---|---|---|---|
| CORE-12 | Voice | Planned / not evidenced | [Validate](FEATURE_REVIEW.md#core) | No claim of full delivery; verify exact code and acceptance before promotion. |
| FIN-01 | Financial consolidation | Planned / not evidenced | [Keep](FEATURE_REVIEW.md#fin) | No claim of full delivery; verify exact code and acceptance before promotion. |
| FIN-02 | Ten-year planning | Planned / not evidenced | [Consolidate](FEATURE_REVIEW.md#fin) | No claim of full delivery; verify exact code and acceptance before promotion. |
| FIN-03 | Holding analysis | Planned / not evidenced | [Generalize](FEATURE_REVIEW.md#fin) | No claim of full delivery; verify exact code and acceptance before promotion. |
| FIN-04 | Financial research | Planned / not evidenced | [Generalize](FEATURE_REVIEW.md#fin) | No claim of full delivery; verify exact code and acceptance before promotion. |
| FIN-05 | Review packs | Planned / not evidenced | [Consolidate](FEATURE_REVIEW.md#fin) | No claim of full delivery; verify exact code and acceptance before promotion. |
| FIN-07 | Ten-year trajectory | Planned / not evidenced | [Consolidate](FEATURE_REVIEW.md#fin) | No claim of full delivery; verify exact code and acceptance before promotion. |
| FIN-08 | Investment strategy and policy | Planned / not evidenced | [Keep](FEATURE_REVIEW.md#fin) | No claim of full delivery; verify exact code and acceptance before promotion. |
| FIN-09 | Portfolio oversight | Planned / not evidenced | [Consolidate](FEATURE_REVIEW.md#fin) | No claim of full delivery; verify exact code and acceptance before promotion. |
| FIN-10 | Scenario and stress testing | Planned / not evidenced | [Consolidate](FEATURE_REVIEW.md#fin) | No claim of full delivery; verify exact code and acceptance before promotion. |
| FIN-11 | Property project requirements | Planned / not evidenced | [Generalize](FEATURE_REVIEW.md#fin) | No claim of full delivery; verify exact code and acceptance before promotion. |
| FIN-13 | Total project costing | Planned / not evidenced | [Consolidate](FEATURE_REVIEW.md#fin) | No claim of full delivery; verify exact code and acceptance before promotion. |
| FIN-14 | Financing research | Planned / not evidenced | [Validate](FEATURE_REVIEW.md#fin) | No claim of full delivery; verify exact code and acceptance before promotion. |
| FIN-16 | Goal dashboard | Planned / not evidenced | [Consolidate](FEATURE_REVIEW.md#fin) | No claim of full delivery; verify exact code and acceptance before promotion. |
| FIN-17 | Decision continuity | Planned / not evidenced | [Consolidate](FEATURE_REVIEW.md#fin) | No claim of full delivery; verify exact code and acceptance before promotion. |

## All supporting references

These overlap product features and remain fully retained, including INSTALL and RND extensions.

<details>
<summary>Show all 56 supporting requirements (21 partial, 35 planned)</summary>

| ID | Requirement | First stage / gate | Merged status | Review |
|---|---|---|---|---|
| MVP-01 | Everyday end-to-end acceptance | MVP · v0.1–v0.2 — MVP | planned | [Keep](FEATURE_REVIEW.md#mvp) |
| MVP-02 | Calendar integrity | MVP · v0.1–v0.2 — MVP | partial | [Consolidate](FEATURE_REVIEW.md#mvp) |
| MVP-03 | Invoice and job integrity | MVP · v0.1–v0.2 — MVP | partial | [Keep](FEATURE_REVIEW.md#mvp) |
| MVP-04 | Offline and model failure | MVP · v0.1–v0.2 — MVP | partial | [Keep](FEATURE_REVIEW.md#mvp) |
| MVP-05 | Independent clean-host recovery | MVP · v0.1–v0.2 — MVP | planned | [Keep](FEATURE_REVIEW.md#mvp) |
| PLATFORM-01 | Safe deterministic adapters and workers | MVP · v0.1–v0.2 — MVP foundation | partial | [Consolidate](FEATURE_REVIEW.md#platform) |
| PLATFORM-02 | Operational targets and capacity | Release/readiness gate · MVP through v1.0 — Release gate | partial | [Keep](FEATURE_REVIEW.md#platform) |
| PLATFORM-03 | Production and host acceptance | Release/readiness gate · MVP through v1.0 — Release gate | partial | [Keep](FEATURE_REVIEW.md#platform) |
| PLATFORM-04 | Private installation adoption | Installation/adoption gate — Before private real-data adoption | planned | [Keep](FEATURE_REVIEW.md#platform) |
| UI-01 | Unified inbox, search and explainability | MVP · v0.1–v0.2 — MVP essentials; expand later | partial | [Keep](FEATURE_REVIEW.md#ui) |
| AI-01 | Controlled external-model gateway | Cross-cutting · No fixed release — Later; disabled | planned | [Challenge](FEATURE_REVIEW.md#ai) |
| AI-02 | Gateway refusal and response handling | Cross-cutting · No fixed release — Later; disabled | planned | [Consolidate](FEATURE_REVIEW.md#ai) |
| AI-03 | Provider and local-baseline evaluation | Cross-cutting · No fixed release — Research gate | planned | [Validate](FEATURE_REVIEW.md#ai) |
| EDU-X01 | Concept-level curriculum model | v0.6 · NOMAD & education — Later | planned | [Consolidate](FEATURE_REVIEW.md#edu) |
| EDU-X02 | Multilingual and pedagogical safeguards | v0.6 · NOMAD & education — Later | planned | [Keep](FEATURE_REVIEW.md#edu) |
| EDU-X03 | Curriculum source hierarchy | v0.6 · NOMAD & education — Later | planned | [Consolidate](FEATURE_REVIEW.md#edu) |
| EDU-X04 | Personalized gentle learning journal | v0.6 · NOMAD & education — Later | planned | [Consolidate](FEATURE_REVIEW.md#edu) |
| NOMAD-X01 | Independent appliance and trust boundary | v0.6 · NOMAD & education — Later; parallel hardware | planned | [Keep](FEATURE_REVIEW.md#nomad) |
| NOMAD-X02 | Constrained resource connector | v0.6 · NOMAD & education — Later | planned | [Consolidate](FEATURE_REVIEW.md#nomad) |
| NOMAD-X03 | Optional shared inference | v0.6 · NOMAD & education — Later; optional | planned | [Challenge](FEATURE_REVIEW.md#nomad) |
| RND-01 | Per-service asset/version catalogue | MVP · v0.1–v0.2 — MVP inventory; expand later | partial | [Consolidate](FEATURE_REVIEW.md#rnd) |
| RND-02 | Technology evaluation and upgrade lifecycle | Cross-cutting · No fixed release — Later | partial | [Keep](FEATURE_REVIEW.md#rnd) |
| RND-03 | Scoped proactive lifecycle research | Cross-cutting · No fixed release — Later; cadence unconfigured | planned | [Consolidate](FEATURE_REVIEW.md#rnd) |
| RND-04 | Task-specific model research | Cross-cutting · No fixed release — Research alongside local-answer/coordinator design | planned | [Validate](FEATURE_REVIEW.md#rnd) |
| RND-05 | Dense versus sparse MoE evaluation | Cross-cutting · No fixed release — Research; no mandatory MoE adoption | planned | [Validate](FEATURE_REVIEW.md#rnd) |
| DISC-01 | Discovery feedback and preference lifecycle | MVP · v0.1–v0.2 — MVP manual; expand later | partial | [Keep](FEATURE_REVIEW.md#disc) |
| DISC-02 | Safe public collectors and digests | v0.5 · Connected life — Later | planned | [Consolidate](FEATURE_REVIEW.md#disc) |
| DISC-03 | Local photo research priority | Cross-cutting · No fixed release — Research; later implementation | planned | [Validate](FEATURE_REVIEW.md#disc) |
| WCOMP-01 | Professional debrief and continuity | v0.7 · Professional & research — Synthetic partial; real later | partial | [Consolidate](FEATURE_REVIEW.md#wcomp) |
| WCOMP-02 | Shared platform, strict work isolation | v0.7 · Professional & research — Synthetic partial; real gate | partial | [Keep](FEATURE_REVIEW.md#wcomp) |
| WCOMP-03 | Meeting, reporting and advisory | v0.7 · Professional & research — Synthetic partial; real later | partial | [Consolidate](FEATURE_REVIEW.md#wcomp) |
| WCOMP-04 | Real connectors, licensed voice and retention | v0.7 · Professional & research — Later; activation gated | planned | [Validate](FEATURE_REVIEW.md#wcomp) |
| DMARC-01 | Local bounded aggregate report pipeline | Cross-cutting · No fixed release — Later | planned | [Keep](FEATURE_REVIEW.md#dmarc) |
| DMARC-02 | Historical security review and quiet anomalies | Cross-cutting · No fixed release — Later | planned | [Consolidate](FEATURE_REVIEW.md#dmarc) |
| CREATIVE-X01 | Verified creative interchange and quality | v0.8 · Creative — Later; creative stages in roadmap | planned | [Consolidate](FEATURE_REVIEW.md#creative) |
| REM-01 | Existing task/reminder baseline and remaining delivery | MVP · v0.1–v0.2 — MVP partial | partial | [Consolidate](FEATURE_REVIEW.md#rem) |
| DOC-X01 | Document staging versus durable ingestion | MVP · v0.1–v0.2 — MVP partial | partial | [Consolidate](FEATURE_REVIEW.md#doc) |
| DOC-X02 | Deletion and old-backup resurrection | MVP · v0.1–v0.2 — MVP/recovery gate | partial | [Keep](FEATURE_REVIEW.md#doc) |
| INSTALL-01 | Independent household installations | Installation/adoption gate — Before private adoption and reusable-installation release | partial | [Keep](FEATURE_REVIEW.md#install) |
| INSTALL-02 | Versioned private configuration | Installation/adoption gate — Before private adoption and reusable-installation release | partial | [Generalize](FEATURE_REVIEW.md#install) |
| INSTALL-03 | Explicit feature activation | Installation/adoption gate — Before private adoption and reusable-installation release | partial | [Keep](FEATURE_REVIEW.md#install) |
| INSTALL-04 | Dependency and safe-disable lifecycle | Installation/adoption gate — Before private adoption and reusable-installation release | planned | [Keep](FEATURE_REVIEW.md#install) |
| INSTALL-05 | Configurable household onboarding | Installation/adoption gate — Before private adoption and reusable-installation release | planned | [Generalize](FEATURE_REVIEW.md#install) |
| INSTALL-06 | Stable software keys and local identities | Installation/adoption gate — Before private adoption and reusable-installation release | partial | [Keep](FEATURE_REVIEW.md#install) |
| INSTALL-07 | Private credential provisioning | Installation/adoption gate — Before private adoption and reusable-installation release | planned | [Keep](FEATURE_REVIEW.md#install) |
| INSTALL-08 | Safe reusable configuration templates | Installation/adoption gate — Before private adoption and reusable-installation release | partial | [Keep](FEATURE_REVIEW.md#install) |
| INSTALL-09 | Cross-installation isolation acceptance | Installation/adoption gate — Before private adoption and reusable-installation release | planned | [Keep](FEATURE_REVIEW.md#install) |
| INSTALL-10 | Versioned updates and configuration continuity | Installation/adoption gate — Before private adoption and reusable-installation release | planned | [Consolidate](FEATURE_REVIEW.md#install) |
| INSTALL-11 | Explicit existing-installation conversion | Installation/adoption gate — Before private adoption and reusable-installation release | planned | [Keep](FEATURE_REVIEW.md#install) |
| INSTALL-12 | Usable optional-feature acceptance | Installation/adoption gate — Before private adoption and reusable-installation release | planned | [Keep](FEATURE_REVIEW.md#install) |
| REV-01 | Scoped contacts and service relationships | After existing scope · All review improvements/refactoring + six supporting bundles — After existing agreed scope, including later stages | planned | [Keep](FEATURE_REVIEW.md#rev) |
| REV-02 | Departure, temporary delegation and access expiry | After existing scope · All review improvements/refactoring + six supporting bundles — After existing agreed scope, including later stages | planned | [Keep](FEATURE_REVIEW.md#rev) |
| REV-03 | Accessibility and interruption recovery | After existing scope · All review improvements/refactoring + six supporting bundles — After existing agreed scope, including later stages | planned | [Keep](FEATURE_REVIEW.md#rev) |
| REV-04 | Standing automation rule lifecycle | After existing scope · All review improvements/refactoring + six supporting bundles — After existing agreed scope, including later stages | planned | [Keep](FEATURE_REVIEW.md#rev) |
| REV-05 | Consented emergency/custodian continuity | After existing scope · All review improvements/refactoring + six supporting bundles — After existing agreed scope, including later stages | planned | [Keep](FEATURE_REVIEW.md#rev) |
| REV-06 | Cross-feature attention/resource budgets | After existing scope · All review improvements/refactoring + six supporting bundles — After existing agreed scope, including later stages | planned | [Keep](FEATURE_REVIEW.md#rev) |

</details>

## Counting and maintenance contract

The register owns retained requirements/evidence; FEATURE_PROGRESS.json records verified snapshot and first-stage mappings; FEATURE_REVIEW.md owns separately labelled recommendations. All IDs must match, and every reference has exactly one review. No review candidate is automatically added to scope.

After a verified feature merge or approved scope/status/milestone change, reconcile the register/roadmap and metadata, including the register-row fingerprint. Run `python3 scripts/build_feature_overview.py` and review generated counters, links and first-stage assignments. `--check` verifies reproducibility without writes; `--export-dir PATH` additionally exports standalone HTML/Markdown/JSON outside the repository when requested. Repository policy rejects stale/tampered output, missing/duplicate IDs or unknown completion claims. No CI/network query is performed by generation. Record hosted CI evidence in PR metadata; do not push source solely to add CI proof or refresh a snapshot after a documentation-only merge.

Changing the generator, template or CI policy remains full CI. Only the exact validated dashboard/metadata paths can join Markdown in documentation-only selection; other new HTML/JSON is unknown/full. Never use green open PRs as merged evidence or turn full retained-scope completion into a prerequisite for every earlier bounded MVP. Private history/profile values remain outside Git.
