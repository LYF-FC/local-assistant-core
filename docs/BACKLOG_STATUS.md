# Backlog status

The [complete register](FEATURE_REGISTER.md) preserves all 155 references (149 baseline plus six approved deferred bundles). [Dependencies](FEATURE_DEPENDENCIES.md), [reconciliation](SCOPE_RECONCILIATION.md) and [roadmap Kanban](../ROADMAP.md) are the planning views; [validation](VALIDATION.md) is dated engineering evidence. No entry is certified production complete. Partial means a bounded implemented subset, not whole-module acceptance.

The following delivery notes preserve progress at each merge; the latest status is at the end.

Documentation reconciliation was merged in [PR #1](https://github.com/LYF-FC/local-assistant-core/pull/1). Specs 050–052 merged in PRs #2–4 for optional archive, bounded PDF text and explicit OCR, retaining DB originals. Spec 053 merged in [PR #7](https://github.com/LYF-FC/local-assistant-core/pull/7), delivering scoped quotation answers with a default-disabled local selector; real-model activation/quality and full conversation remain open. Spec 054 merged in [PR #8](https://github.com/LYF-FC/local-assistant-core/pull/8), delivering bounded calendar reconciliation/daily briefing using normalized synthetic snapshots; live accounts/full needs briefing remain open. Spec 055 merged in [PR #9](https://github.com/LYF-FC/local-assistant-core/pull/9), delivering finite routines with task/private-reminder generation and current completion history. Spec056 merged in [PR #11](https://github.com/LYF-FC/local-assistant-core/pull/11), delivering invoice candidates, explicit human review/unknowns and scoped duplicate hints. Spec057 merged in [PR #12](https://github.com/LYF-FC/local-assistant-core/pull/12), delivering logical proposals/manual review/non-executable approval/withdrawal/history. Spec058 merged in [PR #13](https://github.com/LYF-FC/local-assistant-core/pull/13), delivering bounded offline email originals/single attachment, creator-only provenance, exact replay and aggregate forgetting. Next priorities include external reminders, restricted mail/email provenance, invoice filing and independent readiness in substantial related batches. Later domain modules remain in scope. Avoid repeatedly expanding the synthetic Work pilot while everyday MVP dependencies remain open.

Promote delivery status only after actual merge with its delivering public PR reference. Keep branch verification, merged delivery and live host/provider acceptance distinct. Record overlaps and supersessions explicitly; concise views must not erase retained requirements.

INSTALL-01–12 add reusable household configuration/onboarding/feature activation before private adoption. These planned requirements preserve all prior scope; see [installation contract](CONFIGURABLE_INSTALLATIONS.md).

RND-04/05 add planned task-specific model and dense/MoE research with bounded synthetic evaluations; no runtime adoption is implied. See [contract](LLM_RESEARCH.md).

[Spec 059 overview and critical review](FEATURE_REVIEW.md) is a documentation/tooling batch, not a new runtime capability or approved scope expansion. [Counters](FEATURE_OVERVIEW.md) show 17/99 partial foundations, 82 planned/not evidenced and 0 full retained-contract acceptance after PR13. All 149 references remain; candidate gaps and proposed ordering changes await explicit owner decisions.


Historical PR14/PR15 planning snapshot (approval and merge status superseded by the current reconciliation below): PR14 merged spec059 overview/review; candidates were then unapproved. Spec060 grouped [installation identity, versioned defaults, reviewed templates and informational readiness](INSTALLATION_SETUP.md). INSTALL-01/02/03/06/08 foundations are partial at most after merge; no source counters are promoted before then. External reminders/live sources, actual filing/recovery, flexible memberships, feature activation and later domains remain open.


## Current reconciliation after PR15

Spec060 merged in [PR15](https://github.com/LYF-FC/local-assistant-core/pull/15); INSTALL-01/02/03/06/08 advance to partial, with dynamic membership/activation/full portability still open. Ten public engineering batches now follow the imported baseline. Original 99 named features remain 17 partial/82 planned; baseline 149 now 38 partial/111 planned. Owner approved the complete [later review/refactoring programme](DEFERRED_REVIEW_PROGRAMME.md), including all 149 assessments/shared/whole-product recommendations and six supporting REV bundles after existing scope/later stages. Current 155 references: 38 partial/117 planned/0 full accepted. Earlier pending-approval statements describe the original review; the owner decision supersedes them. No next runtime feature is implemented by this planning batch.


PR16 scope/presentation reconciliation is merged. Spec062 branch [daily overview](DAILY_OVERVIEW.md) focuses existing baseline CORE-08/09/UI-01/ORG-02 with current records, failure/freshness and source navigation. No source counters are advanced before merge. Remaining real/provider/operations/finance/whole-MVP gates and all approved later review work stay open.


PR17 daily overview is merged. Spec063 publishes [the bounded FIN-06 capture contract](FINANCIAL_CAPTURE.md); dedicated financial storage/UI remains unimplemented and FIN-06 stays planned. No implementation counter is advanced. Existing live integrations, operations/recovery, later financial modelling and deferred review scope remain open.


PR18 design is merged; spec064 is an actual [financial storage/API branch](FINANCIAL_REGISTER_API.md), with financial UI still next and full FIN-06 acceptance open. No branch implementation is counted as merged; source counters remain on verified merged feature evidence.


PR19 financial server foundation is merged, advancing FIN-06 to partial; original 99 now has 18 partial and 81 planned and current 155 has 39 partial and 116 planned. Twelve public engineering batches follow the imported baseline. Spec065 [financial UI](FINANCIAL_UI.md) is the current branch, not another design-only delivery or a full FIN-06 completion. Later finance/MVP/host/provider and deferred review scope stay open.


PR20 financial UI is verified merged; 13 public engineering batches now follow the imported baseline. FIN-06 stays partial, with full finance/MVP/host gates retained. Spec066 [operations overview](OPERATIONS_OVERVIEW.md) is current branch engineering, not another financial UI delivery or a full MVP completion. Named18/all39 partial counts remain unchanged.


PR21 operations foundations are verified merged:OPS-09 advances only to partial and RND-01 records runtime version observations. Named19/all40 partial,14 merged public batches. Spec067 [scoped search](SCOPED_RECORD_SEARCH.md) is current branch engineering, not complete unified inbox/search or MVP acceptance.


PR22 scoped search is verified merged. Counts are unchanged: named 19 partial, all 155 references 40 partial, 15 merged public engineering batches and no full retained feature contract accepted. The earlier statement that spec067 is current branch engineering is superseded. Remaining MVP gaps and their proposed order are in the [roadmap](../ROADMAP.md#delivery-strategy--synthetic-mvp-first-then-connector-spikes-agreed-10-november-2026).

Spec068 [synthetic notification path](NOTIFICATIONS.md) is merged ([PR #24](https://github.com/LYF-FC/local-assistant-core/pull/24), corrections [PR #25](https://github.com/LYF-FC/local-assistant-core/pull/25)) for item1 of the agreed order: durable delivery states, quiet/day-budget reuse, per-cycle deduplication, bounded retry and unknown-outcome reconciliation against a synthetic channel. No real provider, device push or email is supplied and CORE-11 stays partial; its limitations are tracked on [PR #25](https://github.com/LYF-FC/local-assistant-core/pull/25).

Spec069 [synthetic filing execution](FILING_EXECUTION.md) is current branch engineering for item2: a separate exact single-use filing request, single claimant, reconcile-before-retry, no overwrite and scrub-on-forget against a synthetic destination. Counts are unchanged until merge; no real filesystem or adapter is supplied and DOC-03/MVP-03 stay partial.
