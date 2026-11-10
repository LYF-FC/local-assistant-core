# Feature dependencies

Companion to the [complete register](FEATURE_REGISTER.md). These are prerequisites and feasibility questions, not installed dependencies or activation authority. Preserve parent mappings when splitting work. Manual imports can unblock a domain but do not certify its live connector. Historical version labels are planning stages; the [roadmap](../ROADMAP.md) orders work by current dependencies.

| ID | Required foundation or feasibility gate |
|---|---|
| CORE-01 | authentication and policy |
| CORE-02 | PostgreSQL |
| CORE-03 | export schema |
| CORE-04 | policy engine |
| CORE-05 | audit store |
| CORE-06 | Authorized local inference adapter; FR/ES/EN evaluation and resource bounds |
| CORE-07 | core policy and tool registry |
| CORE-08 | web interface/API |
| CORE-09 | HTTPS/VPN |
| CORE-10 | ingestion, OCR, search |
| CORE-11 | durable scheduler |
| CORE-12 | audio capture and model benchmark |
| CORE-13 | API/account feasibility |
| ORG-01 | verified calendar adapter |
| ORG-02 | calendar, tasks, memory |
| ORG-03 | scheduler and durable jobs |
| ORG-04 | calendar, location/routing |
| ORG-05 | conflict model |
| ORG-06 | location profiles and inventory |
| ORG-07 | files/imports |
| DOC-01 | IMAP/SMTP credentials |
| DOC-02 | sandboxed parser and OCR |
| DOC-03 | limited SMB/API access |
| DOC-04 | file inventory/hashes |
| DOC-05 | document records |
| DOC-06 | online fetch boundary |
| DOC-07 | scheduler/documents |
| DOC-08 | equipment/locations |
| HOME-01 | transactional records |
| HOME-02 | batch ledger |
| HOME-03 | product/unit catalogue |
| HOME-04 | inventory |
| HOME-05 | stock movements |
| HOME-06 | inventory/tasks |
| HOME-07 | DOC-01/02 |
| HOME-08 | inventory and recipe records |
| HOME-09 | controlled fetch/parsing |
| HOME-10 | Permitted quality/seasonal sources; dated manual references before optional automation |
| HOME-11 | export jobs |
| CARE-01 | restricted health records |
| CARE-02 | food/allergen model |
| CARE-03 | recipes and care profile |
| CARE-04 | time series/imports |
| CARE-05 | approved instructions and audit |
| CARE-06 | verified provider access |
| CARE-07 | training records |
| CARE-08 | calendar/tasks; no assumed provider API |
| CARE-09 | restricted export policy |
| OPS-01 | supported device bridge |
| OPS-02 | device capabilities and policy |
| OPS-03 | indexed files/player adapter |
| OPS-04 | audio metadata pipeline |
| OPS-05 | reviewed scripts, source access |
| OPS-06 | verified device sync tooling |
| OPS-07 | job framework |
| OPS-08 | sandbox and GitHub CI |
| OPS-09 | Service/model/storage/backup/job health inventory; stale/failure semantics |
| OPS-10 | Audit/error/access/capacity records; redaction and operator visibility |
| EDU-01 | Independent supported hardware/storage; verified offline content and recovery |
| EDU-02 | NOMAD supported content |
| EDU-03 | documented interface and firewall |
| EDU-04 | content metadata |
| EDU-05 | curated sourced corpus |
| EDU-06 | restricted learning records |
| EDU-07 | content manifest |
| WORK-01 | online fetch and private workspace |
| WORK-02 | CRM records |
| WORK-03 | mail/send policy |
| WORK-04 | client workspace/docs/calendar |
| WORK-05 | shop access and transactional IDs |
| WORK-06 | private career records |
| WORK-07 | scoped GitHub adapter |
| WORK-08 | local vision/metadata worker |
| WORK-09 | Resolve access, local media worker |
| WORK-10 | suitable native/GPU worker |
| FIN-01 | verified statements/imports |
| FIN-02 | deterministic calculation engine |
| FIN-03 | sourced rules and documents |
| FIN-04 | mail/public research |
| FIN-05 | redaction/export checks |
| FIN-06 | MVP: manually confirmed goals, dated assumptions and source references in restricted records; advanced modeling follows reconciled imports |
| FIN-07 | Restricted records; reconciled imports; deterministic versioned scenarios; dated currency/tax/jurisdiction assumptions; professional review where appropriate |
| FIN-08 | Restricted records; reconciled imports; deterministic versioned scenarios; dated currency/tax/jurisdiction assumptions; professional review where appropriate |
| FIN-09 | Restricted records; reconciled imports; deterministic versioned scenarios; dated currency/tax/jurisdiction assumptions; professional review where appropriate |
| FIN-10 | Restricted records; reconciled imports; deterministic versioned scenarios; dated currency/tax/jurisdiction assumptions; professional review where appropriate |
| FIN-11 | Restricted configurable project brief and dated criteria; no live research required for manual capture |
| FIN-12 | Approved public research; dated candidate/source/due-diligence records; no schedule by default |
| FIN-13 | Restricted records; reconciled imports; deterministic versioned scenarios; dated currency/tax/jurisdiction assumptions; professional review where appropriate |
| FIN-14 | Restricted records; reconciled imports; deterministic versioned scenarios; dated currency/tax/jurisdiction assumptions; professional review where appropriate |
| FIN-15 | Manual scoped opportunity records, provenance, risk/verification and review states; automatic monitoring later |
| FIN-16 | Restricted records; reconciled imports; deterministic versioned scenarios; dated currency/tax/jurisdiction assumptions; professional review where appropriate |
| FIN-17 | Restricted records; reconciled imports; deterministic versioned scenarios; dated currency/tax/jurisdiction assumptions; professional review where appropriate |
| CREATIVE-01 | Approved reference media/projects, annotations, usage rights and scoped provenance |
| CREATIVE-02 | CREATIVE-01; versioned project/client/general preference records |
| CREATIVE-03 | Explicit opt-in project snapshots/exports/feedback; no continuous hidden monitoring |
| CREATIVE-04 | CREATIVE-01/02; verified editor/interchange route; bounded local media worker |
| CREATIVE-05 | CREATIVE-04; evidence-linked review and reversible versioned suggestions |
| CREATIVE-06 | Reviewed proposal/correction comparison; validation before preference changes |
| CREATIVE-07 | Recoverable originals/linked-media/project versions; creator quality/export approval; separate send authority |
| MVP-01 | All MVP rows; cross-user end-to-end acceptance |
| MVP-02 | ORG-01; stable provider IDs and conflict rules |
| MVP-03 | DOC-01–03; PLATFORM-01; durable archive |
| MVP-04 | Local inference/retrieval; deterministic workers; stale external state |
| MVP-05 | DB, archive, keys/configuration; independent recovery host |
| PLATFORM-01 | Current identity, approvals/audit, transactional jobs/outbox |
| PLATFORM-02 | Measured workloads; accepted resource and RPO/RTO targets |
| PLATFORM-03 | Full exact-main CI; deployment/security/key/recovery runbooks |
| PLATFORM-04 | Accepted upstream release; private mapping/backup/rehearsal/rollback |
| UI-01 | Scoped APIs, agenda, search, approvals and durable job outcomes |
| AI-01 | Separate policy/egress ADR; classification; payload-bound approval |
| AI-02 | AI-01; denial, budget, expiry and malicious-response tests |
| AI-03 | Local baseline; current provider controls; synthetic/public evaluation only unless separately authorized |
| EDU-X01 | Versioned systems/stages/domains/concepts/mappings/resources/observations |
| EDU-X02 | EDU-X01; FR/ES/EN expression layer; parent control |
| EDU-X03 | Dated official sources; configurable source hierarchy; licensing |
| EDU-X04 | EDU-X01–03; authorized private observations and interests |
| NOMAD-X01 | Independent hardware/content and restricted network boundary |
| NOMAD-X02 | NOMAD-X01; verified endpoint capabilities and attribution |
| NOMAD-X03 | Optional authenticated local inference; no general memory bridge |
| RND-01 | Service/version inventory, manifests, licenses, advisories, evidence and exception expiry |
| RND-02 | RND-01; sourced benchmarks; migration/restore/rollback review |
| RND-03 | Safe public research; deduplication, severity and configured budgets/cadence |
| RND-04 | RND-01/02; synthetic task datasets and executable baselines; intended hardware/quality/resource budgets; CORE-06/07/10; INSTALL-02/03; workspace isolation |
| RND-05 | RND-04 evaluation protocol; dated primary model/runtime/license sources; total versus active weights, context/KV/quantization and memory/concurrency measurements |
| DISC-01 | Explicit scoped memory, correctable preferences and feedback |
| DISC-02 | DISC-01; safe collectors, checkpoints, retry and notification policy |
| DISC-03 | Separate household/professional rights, privacy/license/quality evaluation |
| WCOMP-01 | Explicit Work grants; reviewed debriefs and source lineage |
| WCOMP-02 | Separate DB roles/files/keys/indexes/prompts/jobs/audit/export/retention; recovery gates |
| WCOMP-03 | Authorized work evidence; WCOMP-01/02; reviewed claims |
| WCOMP-04 | Employer policy; specific accounts/actions; commercial voice license; independent recovery |
| DMARC-01 | Approved aggregate reports; bounded XML/archive parser; provenance/deduplication |
| DMARC-02 | DMARC-01; admin scope, historical retention/export and calibrated quiet alerts |
| CREATIVE-X01 | WORK-09; CREATIVE-01–07; verified version-specific interchange and quality review |
| REM-01 | Specs 046/047; recurrence/calendar/channel contracts remain open |
| DOC-X01 | Spec 048; durable storage consistency; sandboxed PDF/OCR and archive restore |
| DOC-X02 | DOC-X01; key/derived-copy lifecycle; authenticated older-restore suppression |
| INSTALL-01 | Reviewed deployment/isolation contract; PLATFORM-02/03 |
| INSTALL-02 | INSTALL-01; configuration schema/versioning; secrets references |
| INSTALL-03 | INSTALL-02; current administrative authority; dependency/status model |
| INSTALL-04 | INSTALL-03; durable jobs, approval invalidation, recovery and concurrency tests |
| INSTALL-05 | INSTALL-01/02; identity policy, secure bootstrap and relationship/privacy review |
| INSTALL-06 | INSTALL-05; explicit policy/schema migration and stable export identities |
| INSTALL-07 | INSTALL-02; secret storage/reference policy; least-privilege connectors |
| INSTALL-08 | INSTALL-02/05/07; classification, import validation and schema compatibility |
| INSTALL-09 | INSTALL-01/06/07; isolated DB/files/jobs/keys/backup tests |
| INSTALL-10 | INSTALL-02/04; release manifest, upgrade/recovery contracts; PLATFORM-03 |
| INSTALL-11 | INSTALL-05/06/10; PLATFORM-04; separate owner authorization |
| INSTALL-12 | INSTALL-01–11; MVP acceptance; reviewed hardware/toolchain prerequisites |

Spec 051 builds on merged spec 050 and extends spec 048; it delivers only bounded PDF text derivation within DOC-X01/CORE-10 and the parser foundation of DOC-02. OCR, reviewed structured fields, restricted mail intake and live Synology remain successive dependencies. No register ID is removed or declared fully accepted by this increment.

Spec 052 extends the spec 051 parser with explicit bounded OCR, preserving all storage/source/review boundaries. Structured field candidates with uncertainty, duplicate detection, mail intake and live filing remain dependencies of DOC-01–03; OCR alone does not complete them.

Spec 053 reuses reviewed sources/provenance from specs 048/051/052. It adds lexical evidence and validated quotation selection, not a parallel index/store or free-form dialogue. Real model/license/quality/context/egress acceptance, RND-04/05 evaluation and installation configuration remain separate dependencies; model controls never grant document permissions.

Spec 054 implements the complete normalized calendar window/read boundary and a deterministic day briefing over current tasks/confirmed memory references. ORG-01/02, CORE-08/09, UI-01 and MVP-02 remain partial; live Apple/iCloud/CalDAV account feasibility, recurrence expansion/pagination, full needs briefing and later writes/mirroring still require separate evidence. INSTALL-01–12 and all 149 IDs remain unchanged in scope.

Spec 055 extends specs 046/047 with bounded daily/weekly routine plans, task/private-reminder generation and completion/lifecycle history. ORG-03 recurrence is distinct from spec 054 imported occurrence identity. Monthly/exception/delegated/calendar recurrence, CORE-13 external channels, INSTALL lifecycle and independent recovery/adoption remain open. All 149 IDs and original parent mappings remain.

## Invoice field review — spec 056

Spec 056 extends specs 048/051/052 reviewed originals and extraction with bounded invoice candidates, human confirmed/unknown decisions, exact provenance, current-source invalidation and scoped duplicate hints. DOC-02 advances; DOC-01 mail/email provenance and DOC-03 destination/name proposals and exactly-once filing still gate MVP-03. DOC-04 inventory/cleanup remains distinct. No original parent mapping or any of the 149 IDs is superseded.

## Reviewed invoice filing plans — spec 057

Spec 057 extends spec 056 with reviewed logical naming/destination proposals and non-executable approval/withdrawal. DOC-03 remains partial: restricted mail/email lineage (DOC-01), configured destination authorization, real contained/collision-safe apply/rollback and retry/crash reconciliation still gate MVP-03. No new original, executor or approval store; DOC-04 inventory/cleanup remains distinct. All 149 IDs and INSTALL/RND scope remain.

## Offline email intake — spec 058

Spec 058 extends document originals/extraction and specs 056/057 with offline exact raw-email/single-attachment provenance and per-owner/scope exact replay. DOC-01 advances without a live mailbox; restricted source/sender rules, cursors/jobs/recovery and broader MIME remain dependencies. DOC-03 actual authorized contained apply/rollback and retry/crash reconciliation still gate MVP-03. Duplicate hints and plan approvals keep their original bounded/non-executable contracts; DOC-04 and all 149 IDs/INSTALL/RND remain.


Merged spec060 (PR15): [setup foundation](INSTALLATION_SETUP.md) depends on existing identity/admin grants, durable audit, schema migration and logical recovery. Informational capability dependencies do not implement activation/disable enforcement. Dynamic membership, credentials, rollout/health/recovery and full independent-domain portability remain prerequisites to later installation acceptance; no retained reference is superseded or deleted.


## Approved deferred programme — after existing scope

The original149 references remain. REV-01–06 add six supporting references; all 149 baseline reviews and shared/overall improvements are retained in [the approved later programme](DEFERRED_REVIEW_PROGRAMME.md). Overlap is refinement, not permission to delete original outcomes or count duplicate implementations.

| ID | Required foundation or feasibility gate |
|---|---|
| REV-01 | Existing149-reference implementation/later-stage decisions first; CORE-01/04, WORK-02/WCOMP-01 and scoped domain consumers; cross-context refusal and duplicate/ambiguity review. Detailed bounded acceptance and migration/recovery review before implementation. |
| REV-02 | Existing149-reference implementation/later-stage decisions first; INSTALL-05/06, CORE-01/04 and job authority; expired/revoked tokens, stale jobs and implicit ownership-transfer refusal. Detailed bounded acceptance and migration/recovery review before implementation. |
| REV-03 | Existing149-reference implementation/later-stage decisions first; CORE-09, UI-01, INSTALL-12; representative devices/tasks, measurable usability criteria and scoped-draft confidentiality. Detailed bounded acceptance and migration/recovery review before implementation. |
| REV-04 | Existing149-reference implementation/later-stage decisions first; CORE-04/11, PLATFORM-01 and original established-rule intent; current exact-action authority, in-flight reconciliation and audit. Detailed bounded acceptance and migration/recovery review before implementation. |
| REV-05 | Existing149-reference implementation/later-stage decisions first; CORE-03/04, MVP-05 and scoped recovery/exports; unconsented health/finance/work refusal, protected access and copy-limit disclosure. Detailed bounded acceptance and migration/recovery review before implementation. |
| REV-06 | Existing149-reference implementation/later-stage decisions first; PLATFORM-02, RND and AI budget contracts; measured limits and competing-load/refusal/failure evidence without surprise spending or remote fallback. Detailed bounded acceptance and migration/recovery review before implementation. |


Spec062 (merged PR #17) [daily overview](DAILY_OVERVIEW.md) depends on the existing scoped day briefing, private owner-reminder inbox, document query/current-source read and strict UI/session transport. It adds no new authority, queue or live adapter. Baseline UI-01/CORE-08/ORG-02 are refined without moving REV additions/refactoring ahead of their approved later stage.


Spec063 [financial capture](FINANCIAL_CAPTURE.md) specifies FIN-06 prerequisites: typed server validation, current finance grant plus record ownership, provenance/basis/plan acknowledgement, concurrency/audit, bounded export/forget and migration/recovery evidence. Generic Memory JSON alone is not acceptance of this domain. No existing dependency row is removed or changed.


Spec064 (merged PR #19) [financial storage/API](FINANCIAL_REGISTER_API.md) supplies FIN-06 typed owner/grant authority, lifecycle/audit/concurrency and recovery foundations; the financial UI followed in merged PR #20. No source row or later calculation/import/provider gate is removed.


Spec065 [financial UI](FINANCIAL_UI.md) consumes merged spec064 server authority/types/lifecycle/export/recovery; no new feature reference, permission or fixture dependency. Full FIN-06 modelling/imports and later financial/MVP/host acceptance remain. Strict client checks complement rather than replace server authority; deferred REV work is unchanged.


Spec066 [operations overview](OPERATIONS_OVERVIEW.md) uses existing identity/CSRF/technical-admin membership locking, metadata audit and runtime package metadata; own technical job statuses use existing SELECT grants. OPS-10 needs a separately reviewed narrow audit projection; no general audit SELECT is introduced. Full monitoring/scouting/independent recovery remain dependencies of acceptance, not inferred from configured flags.


Spec067 [search](SCOPED_RECORD_SEARCH.md) consumes existing task/document query/read authority and current grant/edit attribution. Independent cursors and original-query expiry apply across partial failures; destinations reread minimal source targets. Broader libraries/semantic search/pending approvals remain separate retained dependencies, not inferred from these two APIs.
