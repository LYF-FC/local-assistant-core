# Withdraw selected synthetic sources and clean derived copies

This privileged development/test procedure withdraws selected registered source bindings in one **disabled synthetic workspace with zero grants**. It forgets each live note whose current or retained historical revision references a selected source, discards related pending capture/change/confirmation inputs and clears cached review hashes. All effects and the receipt commit together.

No original document/transcript store is implemented here. Source bindings refer to append-only synthetic validation fixtures. Their markers/audit stay intact. This is source **withdrawal**, not original-file deletion, cryptographic erasure or complete independent recovery. No data leaves the local target.

## Review the complete affected set

Stop consumers and other trusted maintenance. Use the privileged maintenance environment pointed at the explicitly named isolated development/test database. If recovering a backup, follow [the recovery sequence](RECOVERY_ASSESSMENT.md) and [workspace quarantine](WORK_RESTORE_QUARANTINE.md) first. Keep the normal API disconnected from a restored database.

Select 1–10 sorted unique registered source UUIDs explicitly. Repeat `--source` for each selected UUID. Missing or cross-workspace sources refuse; there is no automatic source discovery/adoption.

```sh
python -m app.work_source_withdrawal --environment development \
  --database REVIEWED_DATABASE --operator TECHNICAL_ADMIN_UUID \
  --workspace SYNTHETIC_WORKSPACE_UUID --source SELECTED_SOURCE_UUID
```

Review the **whole metadata plan**, not just the number of sources. It lists source activation flags, affected note IDs/current revisions and whether the dependency occurs currently or in retained history, plus pending/cache references. A note corrected to a different current source is still forgotten if retained history used a selected source. The entire note and all its revisions are redacted; this deliberately avoids trying to guess which text came from which source. Inspect the actual authorized notes before disabling the workspace if you need to decide whether to proceed.

Pending new captures may contain source-derived text before a note exists. Pending corrections on an otherwise unrelated note are also discarded when their proposed payload references a selected source; that unrelated current note stays intact. Pending changes/confirmations and review caches tied to an affected note are included even when they no longer carry source IDs. Parties have no source provenance and are not inferred as derived records.

Plans contain no markers, quotes, payloads, source labels or raw content hashes. A plan supports at most 25 affected live notes and 100 pending/cache effects, within 32 KiB. Any overflow refuses the **entire source withdrawal**; no partial batch can deactivate a source while silently leaving further derivatives. Use separately reviewed existing note/pending-input cleanup to reduce the affected set, then obtain a fresh full preview. Do not edit the plan or skip its unresolved effects.

## Apply exactly the reviewed plan

Use the same explicit target/workspace/operator/source flags and the exact server-issued timestamp/hash within five minutes:

```sh
python -m app.work_source_withdrawal --environment development \
  --database REVIEWED_DATABASE --operator TECHNICAL_ADMIN_UUID \
  --workspace SYNTHETIC_WORKSPACE_UUID --source SELECTED_SOURCE_UUID \
  --issued-at EXACT_SERVER_ISSUED_AT --reviewed-hash EXACT_REVIEWED_HASH \
  --decision withdraw_sources
```

Changed source activation, affected note revision/set, request/cache references, target, workspace, selection or review time requires a new preview. Replay cannot advance another set. An already-inactive selection with no remaining effects produces no completion receipt. An inactive binding with retained derivatives can still be cleaned up after a fresh review.

The operation uses the existing migration-0017 quarantined owner-only forgetting authority and migration-0018 cache-redaction authority; it does not relax their guards. It denies pending requests and redacts their payloads/hashes, forgets affected notes/current/history through the existing lifecycle, checks for remaining selected live dependencies/pending effects, then sets selected `source_registry.is_active=false`. The metadata `admin.work_sources_withdrawn` receipt records prior source flags, forgotten note IDs/revisions/dependency flags, discarded request/cache references, actual database OID and the exact plan hash. Audit/guard/error failure rolls back all effects. CLI output appears only after commit; inspect state/receipt before retrying an uncertain commit.

Unselected source flags, unrelated current notes/parties/pending inputs, other workspaces, append-only validation markers and previous audit remain. No role/grant/schema/dependency/API change, scheduler, model/provider, activation or automatic source repair is installed. The workspace stays disabled/no-grant. Every plan/receipt retains `activation_authorized=false` and `recovery_complete=false`.

## Verify and retain independent evidence

Preview again and inspect the selected inactive flags and empty affected-note/pending set. The source registry is checked by the existing note SQL guard and capture preparation; tests prove withdrawn references cannot back a new note or capture even after a separately controlled test activation. This procedure never activates a workspace. Existing trusted owner powers can subsequently alter source activation; withdrawal is not an irreversible source tombstone or a permanent startup fence. Forgotten notes remain terminal under the existing lifecycle.

After cleanup, retain a new independently authenticated [terminal-note forgetting manifest/checkpoint](WORK_BACKUP_SUPPRESSION.md) for each affected workspace using its separately trusted key/fingerprint. That protects supplied note-forgetting decisions, not the completeness of source withdrawal. Older backups may contain an active source flag. Keep them quarantined and independently review/reapply source withdrawal; no latest source-withdrawal ledger or automatic completeness proof is added.

Original files, raw transcripts, attachment caches, future indexes/summaries/model caches, unmanaged downloaded exports, other workspaces and independent key/host/off-site acceptance remain separate gates. See [export limitations](WORK_NOTES_EXPORT.md) and [recovery assessment](RECOVERY_ASSESSMENT.md). Supported registry/business writers are fenced by a try-lock and fail-fast table locks; arbitrary trusted owner DDL/manual changes remain outside that boundary.

Verification includes actual current/history/pending-copy redaction and unrelated controls on an older logical restore, then a **new backup and restore after withdrawal** that preserves inactive source flags, scrubbed histories, denied pending copies and the receipt. The actual non-root maintenance-container CLI is checked separately. These are synthetic engineering checks, not independent host acceptance.


[Authenticated selected source checkpoints](WORK_SOURCE_CHECKPOINTS.md) are the spec 041 candidate for retaining committed withdrawal evidence separately and reapplying supplied decisions to older registered sources. This does not change the manual command, add a latest-complete ledger, create missing target bindings or prove original-file/independent host recovery.
