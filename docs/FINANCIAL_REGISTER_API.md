# Restricted financial register API — merged spec064 foundation

Merged [PR19](https://github.com/LYF-FC/local-assistant-core/pull/19) implements the storage/API part of [the approved capture contract](FINANCIAL_CAPTURE.md). The financial UI, its view/hidden-tab expiry controls and complete FIN-06/MVP acceptance remain open. No client-only Memory convention, calculation, provider/model, money movement, automatic source fetch or private-data migration is introduced. Use synthetic data only; the existing private deployment is unchanged.

## Records and authority

Every route requires an authenticated current user, current explicit finance_private grant, exact Origin/CSRF and JSON body. Server-generated owner identity is immutable. Another user with the same scope sees no record, history, count or export; technical administration alone grants none. A dedicated fixed-purpose membership lock preserves the task scope restrictions. Owner→record locks, expiry revalidation after waits, expected revisions and commit-before-release audit are reused.

Records have immutable kind goal/assumption/plan/source, schema1 typed values, current revision/state and timestamps. Required topic/basis/title/as_of/source reference and optional target/source date/amount/currency follow the contract. Unknown amount is null, zero is the string0.00; forecasts remain labelled forecasts. The server never calculates returns, totals, conversions, income or tax. Dates remain calendar dates. Sources are untrusted text/opaque references and are never resolved automatically.

Create/correct store proposed plans. Only a separate explicit acknowledgement of the current record/revision can record plan acceptance; actor/time are server-attributed. Material correction clears prior acceptance. A repeated current acknowledgement is a no-op; stale revisions conflict and are never retried automatically. Acceptance records a choice and grants no action authority. Kind/owner/scope cannot be changed in a correction.

## Protected routes

All paths below are under `/api/v1/finance`, all methods POST, and all bodies include scope:finance_private. Unknown keys reject. No arbitrary owner, state, revision, acceptance actor or timestamp is accepted.

| Route | Additional body / behavior |
|---|---|
| Root | kind and values. Creates revision1;201 receipt. |
| /query | Optional search (160characters), UUID after cursor. At most25 rows plus next cursor; includes own minimal tombstones. No global count. |
| /export | Same filters plus literal acknowledge_copy_limits:true; format json(default) or markdown. Bounded page export, managed_copy:false. |
| /{id}/read | Current owner-visible record or uniform404 for inaccessible/missing ID. |
| /{id}/correct | expected_revision and complete values; material changes append history/reset plan acceptance. No-op409. |
| /{id}/accept | expected_revision and literal acknowledge_record_only:true. Plan only; records owner/time at the current payload version. |
| /{id}/forget | expected_revision; atomic payload/history scrub with minimal tombstone. Already-forgotten replay is safe/no mutation. |
| /{id}/history | Optional numeric after cursor;25 revisions/page with actor/time and snapshots (all null after forgetting). |
| /{id}/export | expected_revision, optional history cursor, literal copy acknowledgement and format. Exports current record with bounded correction-history page atomically under the record lock; next history cursor is explicit. |

At most100 owner records including tombstones. Corrections/acceptance pause at revision100; reads/exports remain available, forgetting may append terminal101. Quota enforcement serializes under current owner lock. Search is literal/escaped, scoped to the current owner payload and never matches scrubbed content. Errors/audit carry metadata/status, not financial text or amounts.

## Export, forgetting and recovery

JSON exports preserve schema/IDs/source/date/basis/history/record-only acceptance. Markdown exports wrap the same structured data in an inert JSON code block with a human-readable heading; source content cannot become active HTML/remote-image markup. These downloads are unmanaged local copies; their acknowledgement does not make them revocable. No outbound provider receives data.

Forgetting clears current values/acceptance and all historical payloads in the same audited transaction. Minimal identity/owner/scope/kind/revision/state/timestamps remain; those are tombstones, not hidden financial facts. Old dumps/WAL/screenshots/downloads are outside this managed scrub. Broader older-backup suppression/whole-installation erasure remain separate gates.

Migration0031 creates financial_records/financial_revisions and sealed identity/history/tombstone guards, with least-purpose runtime grants and a fixed finance membership lock. Downgrade deletes these records/history: take and verify a protected pre-upgrade backup and review rollback/data-loss limits before any separately authorized upgrade. A template cannot recover financial records. No production/private upgrade is authorized by synthetic migration/restore tests.

[Spec064 convergence](../specs/064-financial-register/convergence.md) distinguishes full local checks, actual PostgreSQL/migration/restore and trusted HTTPS API evidence from future UI/host acceptance. The earlier spec063 remains the full capture contract; this API delivery does not reduce it or advance deferred REV/refactoring scope. No status is promoted before merge.


The [financial UI](FINANCIAL_UI.md) is now implemented on the spec065 branch, pending review/merge; the original UI/whole-feature acceptance remains distinct from merged server evidence.
