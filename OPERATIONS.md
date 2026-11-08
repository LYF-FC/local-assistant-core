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
