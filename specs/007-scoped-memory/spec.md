# Spec 007 — scoped explicit local memory

Status: bounded development/test increment. Originally based on bf9804d; now reconciled with main fb8602b after HTTPS prior implementation review merged. No inference, embeddings, automatic capture or work data.

## Outcomes and requirements

M01: an authenticated user explicitly creates profile, preference, experience, procedure or expiring context entries in a currently assigned family/business scope. Owner identity comes from the session; no arbitrary owner/work scope is accepted. Technical administration is not a content scope.
M02: authorize/filter reads in SQL. Private member_a_private/member_b_private/finance_private entries require ownership as well as current scope; household_shared/parents_child/member_business entries are readable by assigned members. Only the owner can correct/forget or inspect history, including shared entries. Private/missing IDs are indistinguishable.
M03: entries contain bounded title/content, source type/reference, confirmed or tentative assessment, dates and revision. No model learning/permission grant follows from an entry. Context requires future expiry; default retrieval excludes expired context. Explicit owner inspection/export may include expired entries without making them active retrieval context.
M04: corrections append owner-attributed snapshots and require expected revision under a row lock. Owner, scope, kind and creation time are sealed. Concurrent/stale edits cannot silently overwrite. Old snapshots are owner-only and labeled historical.
M05: state plus minimal content-free audit commit together; any audit/commit failure prevents response/write. Runtime grants cannot administer users or run DDL. PostgreSQL guards protect immutable context/history through ordinary SQL.
M06: owner forget clears title/content/provenance/assessment/expiry from current record and every revision snapshot transactionally, leaving only minimal IDs/times/status/audit. Forgotten content cannot be restored through the API. Derived indexes are not present; future derived stores require deletion propagation. Existing backups may retain data until documented expiry, and restores must reapply forgetting decisions before retrieval is enabled.
M07: bounded cursor pagination for reads/history/export; versioned JSON export includes authorized current records and explicit expiry/tombstone flags. Export does not grant new access or include others' private history. Export during concurrent writes is page-wise, not a claimed global snapshot.
M08: synthetic negative, concurrency, restricted-role, migration/restore and existing CI tests pass. No family/work records or account connectors are installed. Text/source references are untrusted data and never fetched or executed.

No standing task/action permissions, vector search, LLM prompt assembly, Discovery collector or Work Companion store is implemented. Work isolation spec 005 remains a separate prerequisite to work ingestion.
