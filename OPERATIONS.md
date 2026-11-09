# Operations and recovery boundary

Use synthetic data until independent deployment/security/recovery acceptance is complete. Never run destructive tests against an existing installation. Review migrations before applying them and use independent backups. Ordinary SQL seals do not constrain a trusted database superuser that changes triggers.

Restores can resurrect older content, sessions and pending intent. Stop consumers, quarantine restored access and follow the retained technical recovery guides before any deliberate restart. Downloaded files, historical backups and WAL may retain forgotten content. No physical secure-erasure/latest-backup certificate is claimed.

- [Logical backup/restore](docs/BACKUP_RESTORE.md).
- [Restored sessions](docs/RESTORED_SESSION_QUARANTINE.md).
- [Work source/backup recovery](docs/WORK_SOURCE_CHECKPOINTS.md).
- [Document limitations](docs/DOCUMENT_LIBRARY.md).

Never cache databases, authentication outcomes or test results to accelerate CI. Production/package certification needs full exact-main evidence and separately reviewed host/key/recovery procedures.

Optional [local archive operations](docs/DOCUMENT_ARCHIVE.md) require a separately provisioned private root and consistent DB plus root backup. Never discard/reinitialize/repoint a bound root to bypass a failed cleanup. The synthetic restore drill checks a separately copied directory; it is not a clean-host or older-backup suppression certificate. Root bindings survive disabling the setting, and forgetting refuses unavailable roots. Decommission copies before any real downgrade that removes binding metadata.

Optional [PDF ingestion operations](docs/PDF_INGESTION.md) require a separately selected synthetic overlay. Unavailable extraction retains the original; retry explicitly after repairing the worker. Preserve parser package/build provenance with backups, and verify raw/derived hashes and review state after restore. Migration 0024 refuses downgrade while PDF content or extraction-operation history exists. Forgetting scrubs content but retains immutable operation evidence; keep the migration when that evidence exists. Never apply this exercise to an existing private deployment.

## Explicit bounded OCR — spec 052

The optional PDF worker now includes fixed OCR language models. Failed/over-limit OCR retains the source and creates an unreviewed failure version; choose text extraction or explicit OCR again after checking the cause. Do not treat recognized names/dates/numbers as authoritative. Back up build/model provenance. Migration 0025 refuses downgrade with retained OCR content/snapshots; normal managed forgetting scrubs that metadata, while migration 0024 still protects extracted-operation history. See [limits and recovery](docs/PDF_OCR.md).

## Planned installation operations

INSTALL-01–12 require independent per-household configuration/secrets/records/backups, auditable feature changes, safe worker/dependency shutdown, upgrade compatibility and rollback. Disabling never abandons bound data-cleanup obligations. Versioned template exports omit private data and secret values by default. This is scope only; no production onboarding or toggle interface is delivered. Existing operations and migration refusal remain in force. See [installation lifecycle](docs/CONFIGURABLE_INSTALLATIONS.md).

## Planned model research and operating budgets

RND-04/05 require explicit task/hardware/budget manifests, runtime/weight/quantization provenance, memory/context limits, cold/warm/switching/concurrency measurements and honest failures before model recommendations. No automatic download, background benchmark schedule, model replacement or expansion of tool/network privileges follows from this planning change. Deterministic jobs remain available during inference outages. See [model research](docs/LLM_RESEARCH.md).

## Scoped source answers — spec 053

Document questions and source bundles are ephemeral: no question/prompt/answer content or query hash enters the audit, database history, browser storage or cache. Metadata-only preparation records may represent interrupted/unknown selection; no automatic retries occur. Model failure retains authorized source inspection. Existing document export/forget/backup/recovery remains authoritative, without a duplicate context store. Real runtime retention, offline egress, model/template/context/resource limits and timeout/cancellation behavior require separately authorized acceptance before activation. See [bounds](docs/DOCUMENT_ANSWERS.md).

## Calendar and briefing — spec 054

Calendar sources retain last good bounded windows while offline/failed, expose capture age/coverage and refuse conflicting updates atomically. Source/history quotas pause new changes without blocking explicit forget. Normal logical backups include current/revision payloads; restore fixtures verify recurrence/zone provenance and forgotten scrubbing. Downgrade removes these tables and requires reviewed protected backup/rollback. Event text/UIDs/cursors and briefing content stay out of audit/logs. See [operator limits](docs/CALENDARS.md).

## Recurring routines — spec 055

Routine and reminder consumers remain independently opt-in; the base stack does not start either. Generation uses at most 100 routines/pass with one task each, current grants, atomic cursor/receipt/audit and no model. Counts-only failure output preserves private text. Stop consumers for migration/restore and review restored intent before restart; old backups can replay later-cancelled intent. New logical recovery sentinels verify paused plans, task/reminder lineage and forgotten scrubbing. [Limits/rollback](docs/RECURRING_ROUTINES.md).

## Invoice field review — spec 056

Invoice values, quotes and keys remain out of logs/audit; current source drift withholds fields. History/export is creator-only, five revisions/page; downloaded copies/old backups are outside recall. Invoice-only forget retains the source; document forget scrubs both atomically. Migration 0028 and full logical restore cover current/forgotten reviews. Downgrade removes derived tables/history and needs reviewed protected backup/rollback. No service/provider activation follows. See [limits](docs/INVOICE_REVIEW.md).

## Reviewed invoice filing plans — spec 057

Plans share invoice quotas, current-source invalidation, creator history/export and aggregate scrubbing. No filesystem effect occurs; approved restored plans remain non-executable. Logical recovery verifies approved/proposed history and forgotten copies. Before rollback stop writers and preserve a protected backup: older binaries do not implement plan invalidation and must not continue invoice writes under this contract. [Operator guide](docs/INVOICE_FILING_PLANS.md).

## Offline email intake — spec 058

Migration 0029 protects raw email/initial source linkage with restricted scrub-column grants. Creator raw-mail capacity is 4 MiB plus existing document quotas. Normal logical recovery tests exact envelope bytes and forgotten tombstones; restore starts no poller/consumer. Downgrade drops raw provenance and requires protected backup/export and reviewed rollback. Stop writers: older binaries lack envelope-forget semantics and must not continue writes/forgetting of linked sources. Message hashes/headers stay out of logs/audit; raw export/download and older backups remain outside recall. [Guide](docs/OFFLINE_EMAIL_INTAKE.md).
