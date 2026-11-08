# Plan and analysis

1. Keep one document lifecycle. Add optional extraction metadata and immutable request identity to current records; adapt version seals to validate PDF raw-byte provenance without rewriting old snapshots. Calculate byte quotas from original bytes plus UTF-8 source/derived text.
2. Add a minimal standalone Poppler worker and a bounded Unix-socket client. Confine native parsing with Linux seccomp, resource/time/output bounds and network-free read-only container isolation. No third-party Python dependency or parent-process parsing.
3. Extend authorized upload/replacement/re-extraction, review checks, original filenames, page citations and idempotent creation. Preserve exact originals and existing archive boundaries.
4. Extend strict client parsing and responsive UI, explicit states/retry, review gating and one upload key per deliberate draft. Keep failed/ambiguous requests retryable without duplicate creation.
5. Add synthetic fixtures, unit/parser fault checks, actual PostgreSQL permission/seal/migration tests, separate parser confinement/container/browser phases and PDF restore sentinels. Update canonical scope/delivery evidence. Finish focused checks before one final complete verification and batch push.

No constitution conflict or production authority. Parser output remains untrusted data. Re-extraction is a versioned derivation, not a model answer. The parent container can access no database/archive through the worker, and parser children cannot modify its control socket or create a persistent process. Old-backup/key suppression, durable NAS and generated answers stay open.

Primary interface references: [Poppler pdftotext manual](https://manpages.debian.org/bookworm/poppler-utils/pdftotext.1.en.html), [libseccomp API](https://github.com/seccomp/libseccomp/blob/main/include/seccomp.h.in). Distribution package versions are recorded in the worker image; no unsupported provider/API assumption is introduced.
