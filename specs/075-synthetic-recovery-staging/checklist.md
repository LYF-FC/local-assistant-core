# Spec 075 review checklist

Prepared for the authorized first synthetic slice. Entries remain unchecked; this list is not owner acceptance or independent verification.

- [ ] Scope/authority: only synthetic helper/tests/disposable restore; no real operations, C4 or public operations CLI.
- [ ] Contract: exact staged consumed bytes, actual restored installation singleton and exact Alembic head are distinct requirements.
- [ ] Trust: explicit expected fingerprint/hash/identity/schema; no self-anchored manifest; unchanged Spec 074 assurance.
- [ ] Filesystem: private exclusive stage, bounded copying, no-follow regular single-link files, overlap and cleanup protections.
- [ ] Snapshot: protected digest/count validation before immutable callback handoff; source/stage mutations before versus after snapshot distinguished; consumer uses callback bytes directly; target isolated through final check.
- [ ] Database: valid disposable target, fail-closed missing/extra/wrong rows/heads and query errors; no automatic correction.
- [ ] Forgetting: structural success still refuses release/use; non-Work reconciliation not claimed.
- [ ] Evidence: actual disposable PostgreSQL/drill plus meaningful positive and negative tests; mocks not substituted.
- [ ] Secrets/data: synthetic fixtures only, no material/private path/raw-row disclosure, no external side effect.
- [ ] Reporting: actual checks recorded by revision; branch/merge/verification/acceptance kept separate; gate/register counts unchanged.
