# Convergence — unified attention inbox (first slice)

**Not converged. This is a pre-implementation convergence plan, not a report.** Nothing has been implemented, tested or verified for this feature. Every "Evidence" cell below is empty by design and must be filled only from real results after implementation. Drafting this file changes no implementation status, status counts, verification or owner acceptance. Gate 2 stays open (criterion unchanged: "Dashboard exposes agenda, pending approvals, reminders, failures and authorized search."); CORE-08 and UI-01 stay partial; the five-priority order stays unapproved. The constitution requires convergence to report the agreed feature complete before delivery; that happens only after implementation.

## What convergence must show

| Spec requirement | Source | Required evidence | Evidence |
|---|---|---|---|
| Inbox view composing the six sections for one granted scope; search entry reuses spec 067 | spec §Delivers; CORE-08, UI-01 | Client and browser workflow results (A1) | not yet evidenced |
| Approvals list: pending, unexpired, bound only; allow-listed fields; no payload, hash, policy, approver or requester id; paging | spec §Pending approvals; CORE-04 | Backend allow-list, status, expiry, legacy and cursor tests (A2, A4, E1, E2) | not yet evidenced |
| "Requested by you" label; no self-approval restriction implied | owner decision 3 | Label tests (A3) | not yet evidenced |
| One metadata-only audit event per list request; failure withholds results; event name rechecked and pinned | owner decision 2; CORE-05 | Event shape/count tests, real-role PostgreSQL insert and induced failure (U1, U2) | not yet evidenced |
| Approvals evidence-only: no destination, no Open, decide, cancel or consume control, no request to approval operation routes | owner review; CORE-04 | Browser and network-recording assertions (N3, S1) | not yet evidenced |
| Tasks (open overdue) and reminders (delivered) with owner-only and shared-read-only rules; routine-generated tasks also under ORG-03 | REM-01, ORG-03 | Visibility tests (P2, P3); routine-origin check | not yet evidenced |
| Documents needing review | CORE-10 | Unreviewed and extraction-failed selection tests | not yet evidenced |
| Filing and notification failures with uncertainty wording and owner-only visibility | DOC-03, CORE-11 | Failure-state and visibility tests (F1, P2) | not yet evidenced |
| Explicit refresh, 60-second and approval-expiry clearing, non-atomic notice, late-response discard | spec §Refresh | Expiry and clearing tests (E3, E4) | not yet evidenced |
| Source failure never appears as empty; per-source retry; empty-state sentence only when every source loaded | spec §Refresh | Partial-failure tests (F1–F4, U2) | not yet evidenced |
| Authorization denial clears every section; navigation rereads under current authorization; revoked grant handled | spec §Navigation | Denial and revocation tests (N1, N2) | not yet evidenced |
| Duplicate references render once; separate record kinds not merged | spec §Item model | Dedup tests (D1) | not yet evidenced |
| No state-changing request from the inbox | spec | Network-recording test (S1, S2) | not yet evidenced |
| Mobile 390×844, keyboard and live-region behaviour (existing obligations only; REV-03 not claimed) | spec §Mobile | Browser workflow (mobile) | not yet evidenced |

## Carried open items

1. Audit event name `approval.query`: proposed only; recheck for later constraints and pin with a test.
2. Whether the existing task response identifies routine origin (ORG-03 display); show only if it already exists.
3. Approvals have no authorized in-app destination; adding one is a later owner decision.
4. Open overdue tasks only; widening is a reviewer decision.

## Required at convergence (to be recorded, not asserted now)

Exact merged commit and PR number once merged; the local check components that actually ran; PostgreSQL evidence under the real runtime role; browser workflow results; the dashboard and register reconciliation made in the same PR; explicit statements of what was not verified (private host, remote/mobile device acceptance, real providers) and that owner acceptance of Gate 2 is separate. Implementation, integration, testing, verification and acceptance stay separate facts. Branch engineering is not merged delivery.
