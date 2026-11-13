# Tasks

Checking a box below records only that the named work was done on the implementation branch. It records no independent verification or owner acceptance of any feature or gate, and no merged delivery.

- [x] Specify: [spec.md](spec.md) drafted for the bounded first slice; revised after owner review (approvals evidence-only, task mapping, audit evidence).
- [x] Clarify: owner decisions 1–3 recorded in the spec; requirement mappings CORE-10, DOC-03, CORE-11, REM-01 and ORG-03 confirmed by the owner.
- [x] Plan / analyze: [plan.md](plan.md) written with constitution, data and permission analysis.
- [ ] Owner review of spec, plan and tasks; owner confirms the slice is ready to implement. (Does not approve the five-priority order.)
- [x] Checklist: acceptance scenarios A–S in the spec were reviewed against this task list before implementation; none required a change to authority, scope, acceptance criteria, an approvals screen or an unapproved field.

Review follow-up (PR #34) done on the branch: section-specific more-records wording, in-inbox approvals paging, revision-tie fix, real-stack e2e, and the owner-approved record-level navigation (filing failure → related document by identity, notification failure → related reminder via a verified `task_id`; convergence finding 2). Hosted CI run 43521167626 passed on the current head, including the real-stack browser spec. The owner-review box above stays unchecked.

Implementation (one coherent batch, one grouped push). Items marked done were completed and run locally on the branch, and hosted CI run 43521167626 passed all six jobs on head `6488588` (including the real-stack `e2e/inbox.spec.ts`, 4 passed); owner review and acceptance are outstanding:

- [x] Recheck at implementation time that no migration or code restricts `public.audit_events.event_type`; fix the final event name (`approval.query` is proposed) and pin it with a test; add a migration only if a constraint is found. Done: `event_type` is an unrestricted varchar(128); no constraint, so `approval.query` is used and pinned; no migration.
- [x] Backend: `POST /api/v1/approvals/query` (pending, unexpired, bound; allow-listed fields; `requested_by_you`; cursor paging; no row writes; one audit event per request; audit failure withholds results).
- [x] Backend tests: allow-list, visibility, status/expiry/unbound exclusion, paging, audit shape and failure, CSRF/Origin/session/scope denials, no mutation.
- [x] PostgreSQL integration with the real `butler_runtime` role: memberships, timeouts, concurrent decision versus list, audit insert and induced failure.
- [x] Client: typed adapter for the eight reads with strict parsers, deduplication, expiry and denial clearing; unit tests.
- [x] Client: Inbox view in the records workspace, sections, status/evidence/uncertainty, per-source retry, empty-state wording, non-atomic notice, search entry, existing destinations only; approvals evidence-only with no control.
- [x] Check whether the existing task response identifies routine origin; show origin only if it already does. Done: the response does not provide origin, so none is shown and no field was added.
- [x] Playwright workflows at 390×844, including the no-state-changing-request network assertion and storage/URL privacy checks. Harness (mocked) spec done. Review follow-up: a real-stack spec `frontend/e2e/inbox.spec.ts` with `scripts/inbox-browser-fixtures.py` is added and wired into `scripts/test-containers.sh`; hosted run 43521167626 executed it in the `containers` job (4 passed, aggregate result).
- [x] Contract document, master gate entry, register rows and regenerated overview/dashboard in the same PR, without changing any acceptance criterion; Gate 2 remains the owner's to accept.
- [ ] Required local checks once, one grouped push and one PR, then stop without merge. Final convergence per [convergence.md](convergence.md). Local checks ran; PR #34 is open for owner review; hosted CI passed on the current head; owner review, approval and merge are pending and are the owner's.
