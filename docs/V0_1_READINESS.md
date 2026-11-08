# MVP readiness — engineering and operational acceptance

The MVP has not been released or accepted. [Public baseline CI](VALIDATION.md) proves bounded synthetic engineering at a specific revision. Package version 0.1.0 and imported specs do not certify the complete everyday service.

| Foundation | Demonstrated subset | Outstanding acceptance |
|---|---|---|
| Identity/transport/audit | Local accounts/sessions, current grants, HTTPS/Host/Origin/CSRF, restricted DB role and transactional protected audit | Whole-domain profiles, unified UI/private mobile entry, host access/security review |
| State and jobs | Explicit memory/history, scoped Discovery/context, approvals, durable bounded execution/recovery | General coordinator/recurrence, provider handlers and ambiguous-write reconciliation |
| Tasks/reminders | Manual task lifecycle/agenda and creator-private in-app inbox with quiet rules | Calendar read/reconciliation, daily briefing and one authorized external channel |
| Documents | Exact bounded UTF-8 text/Markdown originals, revisions/review, literal search/citations, export/forget | Durable archive, PDF/OCR, local generated answers, forwarded inbox/invoice filing and document old-restore suppression |
| Synthetic Work | Separate workspace/grants/roles, capture/review/confirmation, corrections/forget, meetings/reporting and recovery controls | Real-source/employer/licensing acceptance and independent operational recovery |
| Recovery | Synthetic logical DB restore, session/pending-intent quarantine and Work source/checkpoint/suppression procedures | Originals/configuration/keys, independent clean host, latest-source completeness, measured RPO/RTO and actual-host acceptance |
| Operations/basic goals | Dependency locks and some failure/status safeguards | Installed-service inventory, unified infrastructure/audit views, capacity/alert/upgrade/rollback acceptance and restricted manual financial goals/source capture |

Use the [MVP acceptance matrix](MVP_ACCEPTANCE.md) for closure evidence and the [roadmap](../ROADMAP.md) for dependency-aware batches. Release gates require full exact-main CI, security/key/recovery runbooks, independent monitoring and measured host acceptance. Synthetic development does not activate a provider or production. Existing private installations remain unchanged until separate migration/adoption authorization.

Spec 050 branch work adds optional local disk copies with immutable cleanup obligations, byte verification and retry/forgetting; it retains authoritative DB originals. See [archive limits](DOCUMENT_ARCHIVE.md). This does not close PDF/OCR, validated Synology, clean-host/key/older-backup or whole-MVP gates; merged delivery and host acceptance remain pending.
