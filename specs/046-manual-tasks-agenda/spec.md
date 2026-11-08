# 046 — Manual tasks and agenda

## Specify

A household member can record a task without a model, explicitly choose shared or private visibility, record an unknown or self assignee and an optional due instant, correct details, mark done/cancelled, reopen, inspect owner history, download a bounded current page and forget content. A task's structured status is authoritative; text never executes a task or implies completion. Due views are an agenda, not notification delivery.

## Clarify

- Only household_shared, member_a_private and member_b_private are supported. Shared members read current content; only the creator changes it or reads history. Private records require both membership and ownership. No directory, delegation, business, finance, care or Work integration.
- Assignment is unknown/unassigned or creator only. Missing due dates remain unknown. Due inputs are aware instants; the screen accepts local date/time and sends UTC. Overdue and next seven days show open tasks only, evaluated using server time.
- States open → done/cancelled → open require explicit separate transitions; done ↔ cancelled is rejected. Corrections preserve status timestamps. Revision conflicts never overwrite. Forgotten records are terminal, with content and every historical snapshot scrubbed; minimal ID/owner/scope/revision/timestamps remain.
- Separate manual_tasks tables preserve legacy internal tasks/approval/job semantics. No executions, jobs, approvals, external fetches or model calls.
- Queries use POST bodies for literal search. Stable UUID keyset pages contain at most 25 records; due filters organize agenda, while pages retain stable ID order. Pages are live, not a global snapshot or full export. Each response states checked time, scope, filters and page size, with no misleading global counts.
- Download rechecks current authority and current filter/page, requires an explicit unmanaged-copy acknowledgement, and may differ from a stale screen. JSON preserves IDs, provenance, versions and timestamps. Earlier downloaded copies/backups cannot be recalled by forgetting.
- Current user → session → chosen membership → record locks are held through state/history/audit commit. Recheck session deadlines after record waits. Shared reader queries lock selected records in shared mode; writes lock exclusively. No general audit reads or scope writes granted.
- Browser drafts exist only in component memory, discard on navigation/session/denial, and aborted or late results cannot repopulate them. Conflicts retain drafts until explicit reload/discard. No automatic mutation retries.

## Acceptance

1. Create, correct, transition, reopen and inspect ordered immutable provenance/history with unknown fields explicit.
2. Scope/owner/CSRF/origin/session/expiry denials and concurrent stale writes cannot leak or change records. Audit failure rolls back state and history.
3. Filter status, literal search and open overdue/next-seven-days/unknown due, page and download current results; past dates are accepted and closed tasks do not appear overdue.
4. Forget scrubs all content/history and blocks resurrection; raw SQL cannot change identity, jump revisions, rewrite history or delete/truncate.
5. Restricted PostgreSQL role, migration down/up and actual logical dump/restore preserve intended boundaries and data.
6. Responsive real-HTTPS browser flow and client tests cover corrections, conflicts, history, export, forgetting and draft lifecycle.

Data leaving the private environment: none automatically. An explicit JSON download creates an unmanaged local copy. All development fixtures are synthetic. Production and real integrations remain gated.
