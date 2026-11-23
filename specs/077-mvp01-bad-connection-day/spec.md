# Spec 077 — MVP-01 "the bad-connection day" (Mac-local rehearsal, synthetic)

## Authority, scope and outcome

On 22 November 2026 the owner approved the next journey in its recommended form (decisions D1–D8, relayed by A1; the repository record is A1's separate documentation commit, not this branch). Authorization is not evidence of implementation, integration, testing, verification or acceptance; [PROJECT_MASTER.md](../../PROJECT_MASTER.md) owns status. This contract owns behavior and limits of the extension only. It extends — and does not rewrite — [046](../046-manual-tasks-agenda/spec.md), [047](../047-task-reminders/spec.md), [053](../053-scoped-document-answers/spec.md), [054](../054-calendar-briefing/spec.md), [056](../056-invoice-review/spec.md)–[058](../058-offline-email-intake/spec.md), [062](../062-daily-overview/spec.md), [069](../069-invoice-filing-execution/spec.md), [070](../070-calendar-recurrence-briefing/spec.md), [071](../071-unified-attention-inbox/spec.md), [073](../073-overdue-stalled-work/spec.md) and [076](../076-mvp01-synthetic-invoice-journey/spec.md).

Outcome: on the already-accepted single rehearsal stack, one synthetic adult keeps a usable day while a *simulated* outage is in force (assistant stopped, filing destination unreachable, calendar source offline), receives a second invoice, requests its filing, sees an honest waiting state with a reason, survives a SIGKILL restart without a duplicate effect, and sees the filing resolve to Filed with exactly one new effect when the outage ends. The second adult sees none of it.

## Owner decisions and exclusions

D1 a new batch may start before the Spec 074 review is resolved (that review stays pending; no Spec 074/075 code is touched). D2 journey, slice and exclusions as briefed. D3 capacity exhaustion is **excluded**. D4 **no migration, no new filing state, no spec 069 change**: reason text only. D5 the administrator hat is off (no `technical_admin` grant). D6 switching Wi-Fi off is an optional owner-only action with no tooling. D7 the single stack `local-assistant-core-mvp01-owner` is reused. D8 acceptance wording stays with the owner.

Excluded: migrations, new filing states, security protections/grants/triggers/rate limits/clocks, real providers, private data, outbound AI, any model choice, host reboot, clean-host recovery, a destination quota/pause, scheduled alerting.

## Requirements

| ID | Requirement |
|---|---|
| R1 | **Second fixture.** `scripts/mvp01-owner-fixtures/invoice-002.eml` (Message-ID `<mvp01-outage-002@example.invalid>`, invoice `MVP01-2026-002`, 245.60 EUR, due date left Unknown, same line positions as F1) with a published SHA-256 checked before it is copied. |
| R2 | **One owner-runnable outage.** `bash scripts/mvp01-owner.sh outage on\|off` composes only existing controls: the simulated answer-model container is stopped (a real connection refusal) and the ledger gets `lookup-unavailable` plus one armed `timeout-before-effect`. The calendar source is marked offline by the owner with the existing control. `status` shows outage, model, ledger controls and calendar-source state. start/rebuild/restart keep the model stopped while the outage flag is set. It is a **simulated switch**, not a real failure. |
| R3 | **Honest reason text** (`frontend/src/filing-reasons.ts`) in the filing panel and the Attention inbox card for a waiting, unknown, failed or cancelled filing: waiting is not failed, an unconfirmed outcome loses nothing and is never written a second time blindly, three failed attempts are final even when the destination was only unreachable. Text only; no server state or contract changes. |
| R4 | **Reachable without hunting.** The filing panel reads its own filings when it appears (read-only) and offers the request form only once it knows whether the exact request already exists; the invoice panel tells the owner where the filing panel appears. The accepted load behaviour of the invoice review is unchanged. |
| R5 | **Stopped answer service.** A connection-refused answer service yields the existing explicit `unavailable` answer ("Local model unavailable · source excerpts remain available"); manual records, reminders, documents and import continue. |
| R6 | **Checker.** `scripts/mvp01-owner-check.py` gains `outage-journey`, `outage-end` and `peer`: live peer-side negatives (filing query/history/cancel/request and document list refused in the owner's scopes; the peer's own inbox sources, briefing and document list show nothing of the owner's; positive control: the peer sees its own marker task) and a ledger +1-effect check (counts supplied from `status`). |
| R7 | **Rehearsal safety unchanged** (spec 076 R6–R8): fixed subnet and single stack, public CA only, `reset` guarded, ≤ 3 owner sign-ins for the whole journey (limit 5 per account per 15 minutes, never cleared), the Mac must stay awake. |

## Characterised limits (tests, no behaviour change)

- **S4 (repeated write timeouts).** A destination that answers lookups ("absent") but times out on *every write* ends the filing terminal `failed` (`attempts_exhausted`) after exactly three attempts although it was only unreachable (spec 069). The composed outage never reaches that state: lookups are unavailable too, so the filing stays `unknown` (never retried blindly, never failed) until the outage ends, then retries once and files with one effect. Ending the write-only case differently needs a spec 069 change (for example a different terminal wording or a longer bound) and is an owner option, not part of this slice. The UI says the three-attempt end is final (R3).
- **S10 (reminder while the restricted worker is killed).** Delivery is one database transaction: killed before commit the reminder stays `scheduled` and the next pass delivers it once (late, not lost); killed after commit it stays `delivered`; never twice.

## Validation mapping

| Criterion (A5 plan) | Evidence |
|---|---|
| C1 outage on: status, calendar offline/stale, no free-day claim | `scripts/test_mvp01_owner.py` (outage on/off/restart), live checker `outage-journey`, existing `daily-overview` wording |
| C2 model stopped: explicit unavailable; tasks/reminder work | live checker, `mvp01-outage.spec.ts`, PostgreSQL connection-refused test, S10 tests |
| C3 invoice 2 twice, plan only, exact request | live checker, fixture checksum test |
| C4 waiting with reason, inbox card, never failed/filed | `filing-reasons.test.ts`, `attention-inbox.test.ts`, live checker, `mvp01-outage.spec.ts` |
| C5 `restart --kill` keeps waiting state, no effect | live run (script copy; real SIGKILL of the application and workers), S10 subprocess SIGKILL tests; the S4 PostgreSQL tests use fresh in-process worker objects and kill nothing |
| C6 outage off: Filed, ledger +1, third import replays | live checker `outage-end` (waits up to 17 minutes: while unreachable the destination is asked again only every 15 minutes, the spec 069 back-off), PostgreSQL S4 composed-outage test (forces the row due) |
| C7 peer sees none of it (live) | live checker `peer`; PostgreSQL peer tests of spec 076 |
| C8 inbox empty only when every source loaded and empty | existing spec 071 tests (unchanged) |
| C9 admin hat | excluded (D5) |

## Limits

Simulated: answer model, calendar, filing destination (metadata ledger) and the outage itself. The live peer check needs the synthetic peer's password replaced for one command, which is a fixture credential change; it was done only on a disposable verify stack (the owner's own stack is the owner's decision). A non-owner *editor* (same scope, different user) is covered by PostgreSQL tests only because the fixture has no third household user. No host reboot or clean-host recovery is exercised. Single stack only.

## Acceptance

None claimed. Human verification and owner acceptance are pending; see [plan](plan.md), [tasks](tasks.md), [checklist](checklist.md), [analysis](analysis.md), [convergence](convergence.md).
