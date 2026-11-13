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

## Feature overview and scope review — spec 059

After a verified feature merge or approved scope change, reconcile register/roadmap and docs/FEATURE_PROGRESS.json, including its snapshot fingerprint, then run `python3 scripts/build_feature_overview.py`. Repository policy checks generated output and ID/review coverage without network or writes; `--check` can be run directly. Export local copies only through an explicit `--export-dir PATH`. Do not query CI just to refresh a static view or certify operational health from its counters. GitHub shows Markdown and downloadable HTML source; no hosting/service/telemetry is activated.


### Installation setup foundation (spec060, merged PR #15)

Follow [the setup/template/identity and rollback contract](docs/INSTALLATION_SETUP.md). Current technical administrators explicitly preview/apply defaults; no provider/worker is activated. Review preference/timezone disclosure before exporting an unmanaged template. At100 revisions changed writes stop, while reads/export remain available. Backups preserve identity/history; templates cannot restore them. Migration0030 downgrade destroys these records and needs a reviewed protected-backup rollback. No private upgrade or deployment authorization is implied.


### Deferred scope approval and operating boundaries

The [approved later programme](docs/DEFERRED_REVIEW_PROGRAMME.md) introduces no running service, deployment, background collection, permission, continuity-pack export or resource policy now. Its six planned REV bundles and all 149 baseline improvements follow existing scope. Future refactors require compatibility/recovery and audit review; existing private systems and separately authorized integration/activation/migration gates stay unchanged. Spec060 references above now describe merged PR15 engineering; no private installation upgrade follows.


### Spec062 (merged PR #17): overview operation

[Daily overview](docs/DAILY_OVERVIEW.md) needs no new service, migration, fixture privilege or consumer activation. An unavailable section is not an empty list or a healthy subsystem. After expiry/hidden tab/context changes, refresh explicitly; external notification and live source status remain separate. No app/worker/secret/deployment configuration or private installation is changed. Existing audit, recovery and source-panel operations remain authoritative.


### Spec063 financial capture design

[The contract](docs/FINANCIAL_CAPTURE.md) requires full synthetic PostgreSQL/migration/restore and runtime-grant evidence before delivery. No operator provisioning, database migration or finance export is performed now. Future forgetting must disclose old backup/download limits; future downgrade needs a reviewed protected backup and loss disclosure. Existing private repository/deployment and all activation/migration authorizations stay unchanged.


### Spec064 (merged PR #19) — financial migration and recovery

Follow [the storage/API contract](docs/FINANCIAL_REGISTER_API.md). Migration0031 downgrade destroys financial records/history and requires reviewed protected-backup rollback; no private upgrade is authorized. Synthetic full restore must preserve basis/zero/unknown/source/acceptance history and scrubbed tombstones without enabling consumers. Downloads and old WAL/dumps remain outside managed forgetting; no external financial action is introduced.


### Spec065 (merged PR #20) — financial UI privacy

[Financial register](docs/FINANCIAL_UI.md) requires the existing current finance grant and ownership; no setup/migration/worker or private deployment change. Drafts/data clear on hidden tab, expiry or context change; explicit current reload is required after conflicts/ambiguous errors. Downloads are unmanaged bounded copies; forgetting does not erase old dumps/WAL/screenshots/downloads. Existing server recovery and separate activation/private-adoption gates remain authoritative.


### Spec066 (merged PR #21) — inspect local observations explicitly

A current technical administrator can reload [Operations overview](docs/OPERATIONS_OVERVIEW.md). This is a 60-second bounded snapshot, not an independent alert, worker heartbeat, backup certificate or periodic audit. Unknown capacity/backup/certificate/host/model/service checks remain operator acceptance work. No Docker socket, filesystem/network probes, auto-repair, activation or private-deployment change is introduced.


### Spec067 (merged PR #22) — search privacy

[Synthetic notification worker](docs/NOTIFICATIONS.md) is optional development/test engineering (`python -m app.notification_worker --once`); it reaches no provider and is not started by default. Keep it stopped across schema updates and after older-backup restores until pending intent is reviewed.

[Synthetic filing worker](docs/FILING_EXECUTION.md) is likewise optional development/test engineering (`python -m app.filing_worker --once`); it writes to no filesystem, folder or network and is not started by default. Keep it stopped across schema updates and after older-backup restores; an unknown filing is reconciled by lookup, never repeated. Downgrading migration 0034 permanently deletes all filing executions and sealed filing history, including the consumed-request evidence, and does not recall anything already written to a destination; after a re-upgrade a consumed plan revision can be requested again. Take a protected backup, stop the worker and roll forward instead; schema downgrade is not a production rollback ([details](docs/FILING_EXECUTION.md#schema-rollback--migration-0034-is-destructive)).

[Search tasks/documents](docs/SCOPED_RECORD_SEARCH.md) requires explicit submission and current grants. Queries/results/previews clear on hidden tab, context change, denial or the original60second deadline; paging cannot renew unchanged sections. Source references remain inert. No deployment, backend, provider or model activation; existing recovery/activation gates remain.
