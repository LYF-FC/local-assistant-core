# Spec 075 preimplementation analysis

19 November 2026 source baseline: `9b7279b86b1b357c47121fb3e3f95bf631ee4884`. Read `AGENTS.md`, constitution, project master, Spec 074, existing `scripts/test-db-restore.sh`, verifier references and current recovery-assessment boundaries. This is design/source analysis, not test or independent-verification evidence.

| Finding | Required treatment |
|---|---|
| Current drill verifies a synthetic copy but restores a separate `$DUMP` pathname. | A dedicated dump-only subdrill uses the new immutable snapshot/callback path. The original full-archive drill retains its prior gap unless separately changed; do not imply new evidence covers it. |
| Spec 074 section 8 expressly excludes later consumed-byte assurance. | Add separate helper/drill behavior; do not change the verifier's output contract or claim path re-verification removes the gap. |
| `verified_references` contains dump SHA only after successful integrity/authenticity/expectations. | Require successful complete verification plus explicit expected manifest hash for this slice; missing/malformed reference fails. |
| Actual installation relation is `public.installation_config`, singleton `id=1`; existing drill uses `LIMIT 1`. | Query exact cardinality and value; restored declaration mismatch must fail even if a manifest is HMAC-valid. |
| Existing schema-head comparison alone cannot reject arbitrary multiple/missing rows robustly. | Require exactly one matching Alembic head and fail on query/missing-relation errors; no restamp/migration. |
| Existing Work reconciliation is domain-specific. | No generic reuse claim. Keep all structural results blocked for release/use; future non-Work reconciliation is still open. |
| A pathname can change after verification; a pinned inode can still be changed in place. | Capture a bounded immutable snapshot, compare its digest/count to authenticated verified references before handoff, then use only callback bytes. After capture, pathname/inode mutation cannot change the snapshot; arbitrary consumer substitution is outside the helper's enforcement and must be prevented by reviewed harness wiring. |
| A PostgreSQL dump can contain executable SQL. | Trusted synthetic test input only; isolated disposable service is not a hostile-SQL security sandbox or operational restore authorization. |

No constitution conflict identified for this bounded synthetic-only design. Implementation and evidence review must still assess actual interfaces/races/cleanup, safe errors, real PostgreSQL results and required CI; absence of a design conflict is not convergence or acceptance.

## Source alignment review — 20 November 2026

The original authorization remains dated 19 November. Source review on 20 November confirms `stage_synthetic_dump` creates/verifies a private dump-only stage, reads a bounded immutable snapshot, checks SHA-256 and length against authenticated verifier references/`member_bytes`, and removes the disk stage before returning. `VerifiedDump.consume` checks the bytes before/after invoking its callback; the dedicated PostgreSQL fixture passes those callback bytes directly to subprocess standard input. This is a trusted internal handoff, not enforcement against an arbitrary malicious callback. The caller can construct Python objects directly; a `VerifiedDump` object is not an unforgeable authorization token.

`inspect_restored_binding` uses qualified public metadata relations, reads at most two rows to reject non-singletons, checks integer singleton ID 1 and expected identity/head, and leaves quarantine/ineligibility fixed. Tests use tiny synthetic metadata databases; they do not prove complete Butler recovery. Expected domain errors are safe/fixed; consumer errors and unexpected programming exceptions propagate and are not claimed sanitized. Staging inherits Linux `O_PATH`; macOS cannot supply that execution evidence. Actual test/run results are recorded separately in convergence only after observation.
