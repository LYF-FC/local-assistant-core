# Spec 075 first-slice convergence record

Prepared 19 November 2026. This records actual branch evidence only; no gate/task/status is promoted. Implementation authorization, test execution, integration, independent verification and owner acceptance remain separate.

## Observed branch evidence — 20 November 2026

Source baseline: `9b7279b86b1b357c47121fb3e3f95bf631ee4884`. The two new internal helpers, unit/integration tests and dedicated dump-only subdrill are implemented on this branch. This is not merged delivery. Required exact-head hosted CI is recorded separately in the draft PR metadata; no hosted result is inferred from these local runs.

The Linux runner used Python 3.12.16 and the locked development dependencies, with PostgreSQL 17 in a separate disposable test container. Checkout inputs were mounted read-only; a Python site-path entry made isolated child interpreters import the checkout, and an init process reaped orphaned children. These are local runner setup details, not repository/workflow changes. No production service was selected. Staging itself inherits Spec 074's Linux `O_PATH` requirement.

| Criterion | Evidence disposition |
|---|---|
| A1 private verified stage / consumed-byte positive | `tests/test_recovery_staging.py`: 41 passed, zero skipped. Private stage cleanup, authenticated digest/count, identical immutable callback bytes and post-snapshot source replacement are asserted. |
| A2 trust/path/mutation pre-restore negatives | Same 41-case module: malformed trust makes zero filesystem calls; wrong trust anchors, unsafe source/scratch paths, aliases, archive presence, cap violation, copy/stage mutation and invalid verifier references refuse handoff. |
| A3 snapshot/callback and singleton/schema failures | Unit cases cover forged/truncated/extra snapshots, callback failure, stage symlink substitution and cleanup failure. `integration/test_recovery_staging_postgres.py`: 20 passed, zero skipped, covering public singleton metadata, missing/malformed/multiple rows, wrong identity/head, query errors and opt-in/target guards. |
| A4 actual disposable PostgreSQL positive/mismatch cases | `scripts/recovery-staging-fixtures.py` passed with actual custom `pg_dump`/`pg_restore`: restore consumes callback bytes after the source is changed; authenticated installation/head declarations inconsistent with restored contents are rejected; invalid dump format fails. Targets are dropped, never activated. |
| A5 existing guarded full drill | `bash scripts/test-db-restore.sh` completed with exit 0 in the disposable Linux/PostgreSQL environment, including the new subdrill and existing full-archive/application/Work checks. The separate original archive path retains its earlier point-in-time gap; the new dump-only proof is not transferred to it. |
| A6 release refusal and no-secret outputs | Unit assertions pin quarantine/ineligibility on staged/consumed wrappers and redact snapshot/key/path representations; PostgreSQL reports retain the same refusal. No general restore executor or activation path is added. Arbitrary callback exceptions are not claimed sanitized. |
| A7 locked quality gates and required exact-head CI | Ruff/format, Bandit, backend dependency audit, repository policy, shell syntax and 23 scope-policy cases passed. Frontend: 824 tests/33 files, build and unchanged high-level audit passed (zero findings at that check). Generated overview check passed: 155 references/99 named, no snapshot change. Broad local suite failures and successful rechecks below remain explicit; exact-head hosted CI is pending publication, with final evidence in PR metadata. |

## Broad local runs and limitations

- First backend runner attempt: **9 failed, 2809 passed, 2 skipped**. Eight failures were isolated child imports without an installed source path; the calendar process-reaping test also failed with the test process as container PID 1. Runner setup was corrected without changing project code or assertions.
- Corrected CI-shaped backend command: `pytest -m 'not integration' --allow-unix-socket --cov=app --cov-report=term-missing -p no:cacheprovider -q -rs`: **1 failed, 2817 passed, 2 skipped, 1157 deselected**, 81% coverage. The failure was existing `test_jobs.py::test_worker_audit_failure_rolls_back_completion`: `jobs.claim()` returned `None` before the intended audit-failure assertion. Its precise cause was not established; a clock/fixture explanation is only a hypothesis. Fresh `test_jobs.py` plus the staging module recheck: **62 passed**. Do not describe the broad run as green.
- Full PostgreSQL command: `pytest -m integration --allow-hosts=127.0.0.1 --durations=30 -p no:cacheprovider -q -rs`: **2 failed, 1155 passed, 2820 deselected**. An existing slow-HTTP answer test returned an unrecorded error response instead of the expected answer object; its exact status/body and cause are unknown. Its skipped document cleanup left a reviewed source visible to a subsequent existing document test. On a fresh database, the answers, documents and new binding modules together passed **69 cases** (6 + 43 + 20), with zero skips. This recheck does not turn the earlier full run into a pass.
- The two backend skips were existing root-dependent permission cases in `test_recovery_set_format.py` and `test_recovery_set_publish.py`. No new staging/binding case skipped. The hosted non-root run is separate evidence.
- A diagnostic rerun was stopped after reproducing/resolving runner setup; no partial run is counted as a full-suite pass. No unrelated worker/document runtime or tests were modified to make this slice green.

These local failures are review evidence and must remain visible in PR metadata. A passing required hosted run at the published exact head is still needed; it is not a substitute for explaining the limits of the local observations.

## Stable source hashes

SHA-256 of the reviewed implementation/test inputs (before publication; final PR head pins their committed content):

```text
ba3f94657913abe51d2e12b9cf16e05356c9e6fde87f72567f105aa3b1b2c9cf  backend/app/recovery_staging.py
7cca578a6bbb83f191a4c0084b50774935a9dab2ad4a920fa84697017f10d450  backend/app/recovery_staging_binding.py
286b3c50489235de9ed442745dfec33e392ffe79d3e2620a8baf7d47f7a9b009  backend/tests/test_recovery_staging.py
15f2035c50fb5a3606d6b13a430131e615b48177a87130e9714a4453232aa2aa  backend/tests/integration/test_recovery_staging_postgres.py
c4e763651fe80918d64ee9f47827d2fa19c9ef99ea127a6b76f364d76e22277a  scripts/recovery-staging-fixtures.py
bec578444f08c6a933f8ccbccf505cd05480d4201a17c1f2648fbf679c6aeac7  scripts/test-db-restore.sh
```

Required hosted-CI convergence remains pending its exact-head result in PR metadata. No merge, independent verification, Spec 074/075 completion or owner acceptance is claimed. Non-Work reconciliation, archive staging/installation, clean-host readiness and actual recovery use remain outside and blocked. Existing task/reviewer/acceptance checkboxes and operational statuses are unchanged.

## Post-merge reconciliation — 20 November 2026

Added after merge. The sections above are the pre-merge record and are preserved unchanged, including their statements that hosted CI was pending; those statements were true when written and are not restated as post-merge evidence.

- Pull request: #59, `feat(spec-075): add bounded synthetic recovery staging and database binding`.
- Merge commit: `a547f412b5048e0bd7c3aef7e3649d87c7e8fd0f` (merged 20 November 2026).
- Implementation head: `23330405c787173c3bb6802e7a6abcec7fb75b7d`.
- Hosted CI: all six exact-head jobs passed at the implementation head.
- Local failures remain as recorded above and are not superseded by hosted CI: the first runner attempt (9 failed), the corrected CI-shaped backend run (1 failed: `test_jobs.py::test_worker_audit_failure_rolls_back_completion`, cause not established), and the full PostgreSQL run (2 failed: slow-HTTP answer test with unrecorded response, and a document cleanup interaction). Targeted reruns (62 passed; 69 passed on a fresh database) did not turn those runs into passes, and their causes remain unresolved.
- Not provided by the merge: independent verification and owner acceptance. No MVP gate, task, reviewer or register status is promoted.

Retained deferred work and limitations: non-Work older-backup forgetting reconciliation (DOC-X02); archive staging and installation; large dumps and a general operational restore CLI; real keys, key custody and ceremonies; NAS and production access; capacity measurements; clean-host recovery and RPO/RTO claims; whole-Spec-075 completion; Spec 074 Phase C completion. All restored results remain quarantined and ineligible for release/use.
