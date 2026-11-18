# Recovery-set retention and forgetting reconciliation — spec 074 Phase C (C3)

**Scoped owner decision — 18 November 2026:** C3 inventory/co-retirement/authentication-retention relationships approved. Every actual lifetime, expiry/purge/destruction rule and evidence method remains pending. No deletion, reconciliation operation or restore is authorized. See [the authoritative decision](../DECISIONS.md#18-november-2026--spec074-c1c3-design-c4-planning-and-c5-manual-ceremony-requirements-approved) and [remaining fields](SPEC_074_OWNER_DECISION_WORKSHEET.md).


**Status: C3 design relationships approved on 18 November 2026; no retention duration, operational deletion rule or forgetting operation is approved.** On 15 November 2026 the owner authorized Phase C design and preparatory work, then separately authorized implementation of the non-operational portions; that bounded implementation was merged in PR #43 ([RECOVERY_PHASE_C_IMPLEMENTATION.md](RECOVERY_PHASE_C_IMPLEMENTATION.md)). Remaining durations and operational procedures remain proposals; validators and report-only reconciliation do not delete, purge, expire or modify records. Every duration below is `[owner decision, not decided]`. Nothing is deleted, purged, expired or modified, and DOC-X02 is not implemented. Spec 074 section 9.4 separates four matters and finalizes none of their durations; this draft organizes them and records the conflicts. No gate, register row or status changes.

## 1. Boundary: a verified manifest is not permission to restore

- A manifest that verifies shows integrity and authenticity of a defined set; it is "evidence about an old set only and never permission to restore forgotten material" (spec 9.4, O2).
- **Until the DOC-X02 requirements are resolved, an older non-Work recovery set must not be treated as safe to restore merely because its manifest verifies.** Existing documentation already says older backups can reintroduce forgotten data ([BACKUP_RESTORE.md](BACKUP_RESTORE.md), memory recovery and older-backup sections). Work records have a reviewed reconciliation path for older synthetic snapshots (specs 018, 032 to 034: [WORK_BACKUP_SUPPRESSION.md](WORK_BACKUP_SUPPRESSION.md)); the register's DOC-X02 row records that non-Work older-restore suppression acceptance is not defined, and spec 074 lists reconciliation design for non-Work records as a blocker for the wider recovery programme (spec 12).
- Retention, however it is decided, cannot make a retained older set safe to restore. Only the reconciliation obligations can.

## 2. Retention matrix (durations not decided)

| Artifact | Lifecycle states (proposed) | Duration | Expiry/deletion responsibility | Sensitivity | Evidence of expiry (proposed) |
|---|---|---|---|---|---|
| Recovery set (dump, archive) | active, superseded, expired, destroyed | not decided | backup custodian (owner decision) | High: contains source data; older sets can reintroduce forgotten data | Signed destruction record: set id, date, who, method, copy-inventory check; no forgotten object identifiers |
| Manifest | tied to its set; retired with it (proposal) | not decided | as the set | Moderate: names archive object ids (document UUID and revision) and sizes (spec 9.4) | as the set |
| Expected-hash record | kept at least as long as any manifest it governs (proposal) | not decided | keeper | Low: hash-only | entry marked retired |
| Expected-fingerprint record and revocation register | kept while any manifest under that key is kept (spec 6.7) | not decided | keeper | Low | entry marked retired |
| Key, all copies | generated, provisioned, active, rotated, retired, destroyed | not decided | both custodians | Critical | destruction log entry per copy |
| Key-event and generation records | kept while the key or its manifests exist (proposal) | not decided | primary custodian | Low to moderate (metadata) | entry marked retired |
| Captured tool output | operator's discretion until a rule exists | not decided | operator | Low (public references: `manifest_hash`, `key_id`, fingerprint) | deletion noted in the log |
| Temporary artifacts (`.recovery-set-tmp-*`) | removed on discovery (`RECOVERY_SET.md`) | none | operator | Moderate: can hold manifest bytes | directory listing after cleanup |
| Application audit rows | existing append-only audit | outside this spec | existing procedures | Low (metadata) | not applicable here |

## 3. Conflict register

| ID | Conflict | Sources | Proposed treatment |
|---|---|---|---|
| CR1 | Retaining sets for recovery versus forgetting obligations; older backups reintroduce forgotten data | `BACKUP_RESTORE.md`; spec 9.4 matter 2 | Owner decides a maximum lifetime and whether an early purge on forgetting is promised. No erasure of backups is promised today. |
| CR2 | Retaining manifests for history versus identifier disclosure | spec 9.4 | Manifests expire with their sets (proposal); a listing of a forgotten object never permits a restore |
| CR3 | Keeping keys for old manifests versus retiring old sets | spec 6.7 | Key retirement follows the last manifest under it |
| CR4 | Destroying a key does not erase data | spec 9.2: no encryption of backups or archives | Key destruction removes only the means to authenticate; never record it as erasure |
| CR5 | Deletion evidence that itself names what was deleted | spec 9.4 | Evidence uses set ids and hashes, not object identifiers |
| CR6 | Copies outside the inventory (removable media, snapshots, hard-linked trees) | spec 3.6 | A signed copy inventory is a precondition for any "destroyed" claim; its completeness cannot be proven by the tool |
| CR7 | Restoring an older non-Work set needs reconciliation that is not defined | DOC-X02 (register); spec 12 | Section 1: such a set is not safe to restore merely because it verifies; a blocker for real use, not solved here |
| CR8 | Work expiry applies to the live database only | [WORK_RETENTION.md](WORK_RETENTION.md) | Document the interaction; Work older-snapshot reconciliation covers Work records only |
| CR9 | Append-only audit versus deletion | [OPERATIONS_OVERVIEW.md](OPERATIONS_OVERVIEW.md) (INSERT-only audit) | Out of scope; audit rows are not governed by this matrix |

## 4. Owner decisions required (unresolved)

Every duration in the matrix; whether backups may be purged early on a forgetting request; who may authorize destruction; the standard of deletion evidence; actual copy-inventory procedures and completeness evidence (the inventory design baseline is approved); the interim rule for older non-Work sets (for example, no restore of such a set without a separately designed reconciliation).

## 5. Objective acceptance criteria for this document

- Each artifact class of spec 9.4's four matters has a row with states, a responsible party, a sensitivity and an evidence rule.
- No row presents a duration as approved.
- Each conflict cites a source and names an owner decision.
- The document states that a verified manifest is not permission to restore and that nothing is deleted or implemented.

## 6. Out of scope

DOC-X02 design or implementation; any purge job, scheduler or deletion; modifying any data; changing retention of live records; changing `spec.md`.
