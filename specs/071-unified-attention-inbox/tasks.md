# Tasks

Planning state only. No implementation task is started, and checking a box below records no implementation, verification or acceptance of any feature or gate.

- [x] Specify: [spec.md](spec.md) drafted for the bounded first slice; revised after owner review (approvals evidence-only, task mapping, audit evidence).
- [x] Clarify: owner decisions 1–3 recorded in the spec; requirement mappings CORE-10, DOC-03, CORE-11, REM-01 and ORG-03 confirmed by the owner.
- [x] Plan / analyze: [plan.md](plan.md) written with constitution, data and permission analysis.
- [ ] Owner review of spec, plan and tasks; owner confirms the slice is ready to implement. (Does not approve the five-priority order.)
- [ ] Checklist: confirm acceptance scenarios A–S in the spec are measurable and traceable before implementation.

Implementation (not started; one coherent batch, one grouped push):

- [ ] Recheck at implementation time that no migration or code restricts `public.audit_events.event_type`; fix the final event name (`approval.query` is proposed) and pin it with a test; add a migration only if a constraint is found.
- [ ] Backend: `POST /api/v1/approvals/query` (pending, unexpired, bound; allow-listed fields; `requested_by_you`; cursor paging; no row writes; one audit event per request; audit failure withholds results).
- [ ] Backend tests: allow-list, visibility, status/expiry/unbound exclusion, paging, audit shape and failure, CSRF/Origin/session/scope denials, no mutation.
- [ ] PostgreSQL integration with the real `butler_runtime` role: memberships, timeouts, concurrent decision versus list, audit insert and induced failure.
- [ ] Client: typed adapter for the eight reads with strict parsers, deduplication, expiry and denial clearing; unit tests.
- [ ] Client: Inbox view in the records workspace, sections, status/evidence/uncertainty, per-source retry, empty-state wording, non-atomic notice, search entry, existing destinations only; approvals evidence-only with no control.
- [ ] Check whether the existing task response identifies routine origin; show origin only if it already does.
- [ ] Playwright workflows at 390×844, including the no-state-changing-request network assertion and storage/URL privacy checks.
- [ ] Contract document, master gate entry, register rows and regenerated overview/dashboard in the same PR, without changing any acceptance criterion; Gate 2 remains the owner's to accept.
- [ ] Required local checks once, one grouped push and one PR, then stop without merge. Final convergence per [convergence.md](convergence.md).
