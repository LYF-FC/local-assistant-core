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
