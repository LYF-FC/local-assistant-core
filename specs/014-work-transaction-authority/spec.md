# Spec 014 — Transaction-bound work access authority

Continue merged #35 by closing registry authorization/revocation races. No storage credentials, work-content connection/API or debrief runtime is enabled.

FR-01: current work list/status requests bind the cookie's current active user/session and currently assigned active workspace in one identity transaction. User/session authority and registry grants remain stable through minimal audit and commit; no caller-supplied user, grant or reusable capability token.
FR-02: PostgreSQL shared transaction advisory barrier protects work registry snapshots; BEFORE STATEMENT write triggers on both registry tables take its exclusive form. TRUNCATE is rejected outright to avoid table-lock inversion; direct privileged SQL and trusted CLI writes serialize too, without granting UPDATE on registry tables to the API.
FR-03: acquire registry barrier, user row read lock, then session row lock. Trusted work administration takes the exclusive barrier before any row locks. Recheck current clock after SQL waits; timeout, audit/commit error, revocation, disabled user/workspace or expired session releases no protected payload.
FR-04: transaction-bound internal authority handle rejects use after commit/rollback or in another transaction. It is never serialized, cached, persisted or accepted from a client; it does not authorize future storage connection use by itself.
FR-05: return explicit transaction_snapshot mode and checked_at metadata; UI labels the latest check as a snapshot, clears stale status during refresh/denial/sign-out and offers an explicit recheck. Ingestion/model/execution remain disabled.
FR-06: real PostgreSQL separate-connection races demonstrate reader-first commit serialization, writer-first denial, raw-SQL/helper revocation, expiry/disablement during waits and bounded lock failure. Migration/restore preserve barrier triggers and existing work/family safeguards.

No new data leaves the local authenticated origin. No new dependency, family scope, role/login secret or employer data. Work audit/read credential broker and full spec 005 remain future gates; current records are identity metadata only.

READ COMMITTED is required and checked; a repeatable-read pre-wait snapshot must fail closed rather than reuse stale grants after a writer commits.
