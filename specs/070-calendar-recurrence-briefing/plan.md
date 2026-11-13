# Plan / analyze

Seven grouped commits on one branch: (1) all-day placement fix, (2) recurrence engine, provider contract and synthetic SQLite provider, (3) migration 0035, models, grants and database guards (stopped for an independent audit, including the F1 floor/origin decision), (4) sync protocol, worker, forgetting and export, (5) briefing v2, routes and frontend with explicit truncation, (6) PostgreSQL concurrency/failure/restart evidence, restore fixture and one-shot worker, (7) this spec, the documentation and the status refresh.

Constitution analysis: deterministic local code, no outbound AI, no credential or egress, no external write; owner authority is rechecked under lock at every claim and at every apply; each guard has a negative test against real PostgreSQL as the restricted runtime role. The F1 audit accepted a database-enforced floor/origin coupling; the evidence is in [the audit](../../docs/BATCH3_F1_AUDIT.md).

Evidence plan: unit tests (recurrence, DST, planner, sync on SQLite, briefing v2, frontend parsers and wording), disposable PostgreSQL tests (schema guards with SQLSTATE and constraint names, the page algorithm under the guards, crash subprocesses, real threads, injected failures), the logical restore drill with a resumed sync, and the exact-test-ID baseline comparison against the base commit.
