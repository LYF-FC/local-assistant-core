# Plan / analyze

Add `notification_deliveries` (current state, sealed transitions) and `notification_delivery_events` (append-only metadata snapshots) in migration 0032, with SELECT/INSERT/UPDATE and SELECT/INSERT runtime grants. Add `notifications.py` (typed documents, synthetic channel double, owner-only query/history) and `notification_worker.py` (enqueue, claim, send, finish, reconcile). The send runs outside any database transaction between two committed phases.

Constitution analysis: deterministic local code only; explicit scopes and current grants checked at each claim; every state change has sealed history and a system audit event committed in the same transaction; no outbound AI, no secret, no data egress; recovery behaviour stays understandable without any model. Locking: user then delivery in claim, finish and reconcile, which avoids the user key-share/row-lock cycle that PostgreSQL showed when finish locked the row first.

Evidence plan: focused SQLite unit tests for lifecycle, retry, ambiguity, deferral, cancellation and isolation; disposable PostgreSQL tests for exact-once under concurrency, claim-before-send visibility, trigger/grant negatives, duplicate cycle, unsent-reminder and unknown-channel refusal and forged history. Full `make check` and integration suite once before the single push.
