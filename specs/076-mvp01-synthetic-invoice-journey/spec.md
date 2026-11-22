# Spec 076 — MVP-01 synthetic invoice journey (Mac-local rehearsal)

## Authority, scope and outcome

On 22 November 2026 the owner approved one bounded journey and Mac-local rehearsal scope (recorded in [DECISIONS.md](../../DECISIONS.md#22-november-2026--approve-the-mvp-01-synthetic-invoice-journey-and-mac-local-rehearsal)) and authorized implementation by the Lead Engineer (A3) after the independent A5 validation contract (reproduced as ACs below) was finalized. Authorization is not evidence of implementation, integration, testing, verification or acceptance: [PROJECT_MASTER.md](../../PROJECT_MASTER.md) owns status; this file owns behavior and limits of the extension only.

Outcome: one synthetic adult can, on the owner's Mac against a named disposable local stack, sign in privately (desktop and mobile viewport), review an agenda, import the exact same invoice `.eml` twice without duplication, review its source, ask an authorized cited question, schedule an in-app reminder, review invoice fields and a logical filing plan, **separately** authorize the exact plan for a **synthetic metadata destination**, see execution status and history, and resume after a controlled application/worker restart with preserved records and no duplicate effect.

This extends — it does not rewrite — the frozen contracts it builds on: [046](../046-manual-tasks-agenda/spec.md), [047](../047-task-reminders/spec.md), [053](../053-scoped-document-answers/spec.md), [054](../054-calendar-briefing/spec.md), [056](../056-invoice-review/spec.md), [057](../057-invoice-filing-plans/spec.md), [058](../058-offline-email-intake/spec.md), [062](../062-daily-overview/spec.md), [069](../069-invoice-filing-execution/spec.md) (see its [operating note](../../docs/FILING_EXECUTION.md)). Spec 069's backend request/cancel/query/history routes, plan-only approval (`execution_authorized: false`) and revision-fenced worker are unchanged; this spec adds the missing browser controls and a durable synthetic collaborator.

Historical Spec 074/075 decisions and the pending Spec 074 review remain preserved and are **not** the next automatic task because of this work.

## Exclusions

Live mailbox/calendar/model/notification providers, private records, a real NAS/file-copy destination or any real filesystem filing result, payments, outbound AI, operational recovery, capacity/key ceremonies, a general approvals redesign, semantic search, deployment and production access. No security protection, role grant, append-only trigger, rate limit or clock is changed. A synthetic capability is never described as a real integration.

## Requirements

| ID | Requirement |
|---|---|
| R1 | **Source-bound filing controls.** After the plan is approved, the document view offers a *separate* "Request synthetic filing" action bound to the exact document, source revision, review/plan revision, logical path and original SHA-256, with two explicit acknowledgements (synthetic destination; exact plan). The browser uses only the existing exact-revision endpoints (`/filing/request`, `/query`, `/history`, `/cancel`). It never retries a conflict, treats the server as the authority and strictly validates every response (owner, scope, document, revision, state, bounded attempts, ordered history). |
| R2 | **Honest status.** Pending, unknown (outcome not yet known; looked up, never blindly repeated), filed, failed and cancelled are distinguished with their reasons; an earlier source/plan is labelled; an unstarted request can be cancelled; the simulated, metadata-only destination and its limits are stated beside the request. Plan approval alone never starts anything. |
| R3 | **Opt-in durable synthetic destination.** `python -m app.filing_worker --destination durable` writes keyed metadata entries (filing key, canonical logical path, original SHA-256, byte size) to a marked ledger directory (`app.synthetic_ledger`), independent of the worker process and its database transaction. Default `--destination memory` keeps the spec 069 behavior. Entries never contain invoice or email bytes. |
| R4 | **Ledger guards.** Development/test only; absolute, non-symbolic directory carrying the exact marker created by explicit `init` in an empty directory; a forged, missing or foreign marker, a production environment or a corrupt/foreign entry is refused with a fixed message. Publishing is exclusive (`os.link`), fsynced and never overwrites; a conflicting existing path is a refusal (`collision`). |
| R5 | **Restart and failure semantics unchanged and proven.** Kill before the effect, kill after the effect before the result, timeouts before/after the effect and an inconclusive lookup behave as spec 069: bounded safe retry only when absence is conclusive, reconciliation without re-effect when present, unknown stays unknown without blind retry; terminal outcomes stay terminal. |
| R6 | **Owner-runnable rehearsal.** `bash scripts/mvp01-owner.sh start\|status\|rebuild\|restart [--kill]\|stop\|reset` (plus `scenario` ledger controls) operates the fixed, single-stack project `local-assistant-core-mvp01-owner` (database `butler_test_mvp01_owner`, loopback HTTP 18081 / HTTPS 18444, origin `https://localhost:18444`). See [docs/MVP01_OWNER_REHEARSAL.md](../../docs/MVP01_OWNER_REHEARSAL.md). |
| R7 | **Rehearsal safety.** Generated private config (0600, distinct migration/runtime credentials, hidden prompt for the synthetic sign-in); only the **public** dev CA is exported with its fingerprint and deliberate Keychain instructions (never auto-imported, no TLS bypass); preflight refuses port conflicts and subnet collision with the fixed `172.29.243.0/28` (naming the conflicting network/project, stopping nothing); `stop`/`rebuild`/`restart` preserve the database, certificates and ledger; `reset` is separately explicit, confirms the exact project name, checks project prefix/DB/synthetic marker and uses no prune. |
| R8 | **Idempotent coherent fixture.** One synthetic installation: an owner, a peer with a private marker record, one manual task and one calendar snapshot on a stated day/timezone, and the byte-exact `invoice.eml` with published SHA-256. The invoice is never pre-imported. |

## Validation contract (A5, design) and mapping

The A5 contract is design, not an executed result. "Evidence" names where each criterion is exercised; execution results and gaps are in [convergence.md](convergence.md). Browser = `frontend/e2e/mvp01-owner.spec.ts`; PG = `backend/tests/integration/test_mvp01_journey_postgres.py` (with the existing `mvp03_journey_postgres`, `filing_restart_postgres`, `notification_restart_postgres`); Unit = `backend/tests/test_synthetic_ledger.py`, `frontend/src/filing-api.test.ts`; Live = `scripts/mvp01-owner-check.py` against the running rehearsal.

| AC | Journey step / failure class | Evidence |
|---|---|---|
| AC1 | Start named rehearsal, synthetic credentials, HTTPS sign-in; identified installation/project, correct scopes, no certificate bypass | Owner script (`start`, `status`), Live (TLS only via exported public CA), Browser, existing HTTPS container tests |
| AC2 | Agenda for the fixture day/timezone: event and task once; freshness explicit; no peer-private record | Live, Browser, existing daily-overview tests |
| AC3 | Same `.eml` twice: one document/envelope, visible replay, original title and review preserved, email lineage | PG, Live, Browser |
| AC4 | Source review, authorized cited exact quotation with document/revision/hash/line, current-source navigation; simulated selector labelled | Live, Browser, existing answer tests |
| AC5 | In-app reminder delivered once by the restricted worker; pending/delivered/acknowledged distinct; acknowledgement does not complete the task | Live, existing `notification_restart_postgres`/reminder tests |
| AC6 | Candidates, intentional unknown, contained plan approval; originals and decisions visible; approval alone causes no effect | PG, Live, Browser |
| AC7 | Separate exact authorization with shown bindings and metadata-simulation limit; server enforces current authority; one request; auditable status/history | Unit (client), PG, Live, Browser |
| AC8 | Supported application/worker restart; same installation, records, review, lineage, history; no duplicate reminder/effect; terminal stays terminal | PG (real worker processes, SIGKILL), Live (`restart`, `restart --kill`, `verify`), Browser |
| AC9 | Failure before effect / after effect before result / inconclusive lookup | PG (kill points, `timeout-*`, `lookup-unavailable` controls), Unit, `scenario` command |
| AC10 | Peer/revoked grant or session/stale document or plan/missing acknowledgements/reused or concurrent request/malicious path/conflicting destination fail closed; revision fences, idempotence, audit confidentiality preserved | PG (grant revocation by scope, signed-in peer, stale/unacknowledged/reused/concurrent/malicious-path/conflicting destination), Unit (client strictness), Live (owner-side refusals only), existing `filing_fence_postgres`. Session revocation is **not** exercised by the new tests (existing identity/session suites cover it generally). |
| AC11 | Simulated model unavailable: explicit unavailable; agenda/manual records/reminder still useful; no outbound AI | Live, Browser |
| AC12 | Stop/restart preserves records/ledger/CA; confirmed reset targets only the rehearsal | Owner-script exercise; reset refusal/guard cases in [convergence.md](convergence.md) |

AC1–AC8 are the ordered owner journey. AC9–AC11 have automated negative/restart coverage plus selected owner-visible scenarios (`scenario`). AC12 is required local operation, not production recovery.

## Limits (stated, not hedged)

- The destination is a metadata simulation in a Docker named volume. It is not a filing adapter, not a copy of the invoice, not a real folder or NAS, and not evidence about any real destination. Its durability is bounded to the volume (survives process kill, container restart and Docker/host restarts that preserve volumes; deleted by `reset`; no backup or replication).
- "Exactly once" is conditional on the destination accepting the filing key and answering a keyed lookup; the ledger does. With a destination that cannot be asked the honest result stays "at most once with a visible unknown".
- In-process tests are not restart proof; the real-process, SIGKILL and container-restart evidence is labelled as such. A host reboot and a clean-host recovery are not exercised and are not claimed.
- The simulated model is a fixed script that echoes a cited source line; it is not a model-quality or no-egress proof for a real model. The calendar is one manual snapshot imported through the real API.
- Single stack only: the fixed proxy-trust subnet and Caddy address cannot be shared; names and ports alone do not isolate concurrent stacks. Proxy trust is not loosened.
- Ledger crash windows: an entry is published by an exclusive `os.link` and is the only authority. A crash after the link but before the `effects.log` append leaves a correct entry whose diagnostic counters (`effects`, `calls`, `lookups`, which are appended, not authoritative) under-report; a crash between the temporary write and the link leaves an unused file in `tmp/` that is never read (not cleaned automatically). Lookup scans at most 5000 entries and refuses beyond that; one ledger is bound to one volume.
- The filing panel lists and shows history for the first 25 entries only and says so; older entries are not paged in the browser. Request/cancel controls are shown only to the document owner (the server refuses everyone else regardless).
- The owner journey needs the owner's personal run; agent evidence is not acceptance.

## Acceptance of this extension

None is claimed. Human verification and owner acceptance are pending and separate; no gate, register count or status is promoted. See [plan](plan.md), [tasks](tasks.md), [checklist](checklist.md), [analysis](analysis.md) and [convergence](convergence.md).
