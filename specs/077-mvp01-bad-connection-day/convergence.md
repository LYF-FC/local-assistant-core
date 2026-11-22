# Spec 077 convergence record (22 November 2026)

Engineering evidence on the **unmerged, uncommitted** branch `work/mvp01-bad-connection/a3-implementation`, base `f88fd5c575cbdf252facbcd0b25cbca9319aac0b`. Implementation, integration, testing, verification and acceptance are separate: **not merged, not reviewed, not verified, not accepted, not tried by the owner.** Nothing here is CI evidence.

## Results (author's Mac, Darwin, Docker 29.9.3; synthetic only)

| Check | Result |
|---|---|
| ruff check / format check (backend) | pass |
| Disposable PostgreSQL 17 (own container, fresh DB, `BUTLER_ENV=test`): `test_mvp01_bad_connection` (6: S4 x3, S10 x2, connection refused), `test_mvp01_journey`, `test_filing_restart`, `test_notification_restart`, `test_mvp03_journey`, `test_filing_fence`, `test_task_reminders` | 109 passed before the connection-refused test was added; the new file alone 6 passed afterwards (the other modules were not re-run after that one added test, which touches only that new file) |
| Ledger unit tests | 14 pass |
| Frontend typecheck / full suite / build | pass / 853 pass (incl. `filing-reasons.test.ts`, 5, and 2 new inbox wording tests) / built |
| `scripts/test_mvp01_owner.py` | OK, 17 tests, **4 skipped** (the owner's running rehearsal holds loopback ports 18081/18444; those cases skip rather than disturb it) — includes outage on/off, restart persistence, F2 checksum |
| `check_repository.py`, `test_ci_scope.py`, `build_feature_overview.py --check` | see the final report for the run after this file existed (the master links here) |
| Live, **patched copy** of script/compose (project `local-assistant-core-mvp01-verify`, ports 18091/18454, subnet `172.29.245.0/28`; torn down afterwards; the owner's stack untouched): `outage on`, `outage-journey` (14 checks incl. offline calendar with no free-day claim, explicit unavailable with the model container stopped, invoice 2 imported twice, waiting `unknown`, inbox source listing, history), `restart --kill` (outage kept, model stayed stopped), `peer` (20 checks incl. refusals in both owner scopes, nothing of the owner in the peer's inbox sources/briefing/documents, positive control), `outage off`, `outage-end` (Filed, one request, history, ledger +1 effect from counts read off `status`, third import replays, answers work again) | passed |
| Live browser (Linux Playwright container, public CA only, no bypass, mobile-width no-overflow check): `mvp01-outage.spec.ts` against the waiting filing | passed after two findings below; `mvp01-owner.spec.ts` journey and resume on a fresh stack (regression of the spec 076 flow) | passed |

## Findings made while implementing (all fixed or stated)

- The filing panel did not read its own status when it appeared and offered the request form even for an existing request: it now reads when it appears and withholds the form until the listing is known (R4).
- A question before any reviewed document returns `no_sources`, not `unavailable`: the checker and guide order the question after review.
- A connection-refused answer service already maps to `unavailable` (confirmed live and by test); no backend change.
- S4 and S10 characterised without behaviour change (spec 077 limits).

## Not run / limits

Not run: the full 1207-test PostgreSQL suite (only the modules above), the real `scripts/mvp01-owner.sh start` or any command against the owner's stack, a Linux run of `scripts/test_mvp01_owner.py` (CI), the macOS-only `recovery_*` backend unit modules (Linux-only `os.O_PATH`; known), a host reboot, clean-host recovery, a real Wi-Fi-off run. The live runs used a patched copy (other subnet/ports/project). The ledger +1 check takes the counts as arguments from `status`; the live peer step replaced the synthetic peer's password on the disposable stack only. A non-owner editor is covered by PostgreSQL tests only. The calendar was marked offline through the API route of the existing control, not by clicking it. Sign-in limit 5 per 15 minutes was respected, never cleared.
