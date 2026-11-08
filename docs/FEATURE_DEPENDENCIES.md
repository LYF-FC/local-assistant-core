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

Spec 051 builds on merged spec 050 and extends spec 048; it delivers only bounded PDF text derivation within DOC-X01/CORE-10 and the parser foundation of DOC-02. OCR, reviewed structured fields, restricted mail intake and live Synology remain successive dependencies. No register ID is removed or declared fully accepted by this increment.

Spec 052 extends the spec 051 parser with explicit bounded OCR, preserving all storage/source/review boundaries. Structured field candidates with uncertainty, duplicate detection, mail intake and live filing remain dependencies of DOC-01–03; OCR alone does not complete them.
