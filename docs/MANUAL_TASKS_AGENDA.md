# Manual tasks and agenda — merged prior implementation review/spec 046

In Local records choose **Tasks and agenda**, choose one access area, then **Add task**. Record a title, optional details and due date, the source/reference and either Me or Unknown / unassigned. A blank date means unknown. Dates use the browser's local timezone and are stored as aware instants. Past dates are allowed. Without a model Butler can still store, edit, finish and organize these tasks.

Shared household members can read current shared tasks. Only the creator can edit, mark done, cancel, reopen, inspect history or forget. Private tasks also require ownership, even when another account has the same scope. No directory/delegation, care/finance/business/work task policy is enabled by this feature.

## Agenda and status

Use status, literal title/details search and Any date / Overdue / Next seven days / Unknown date filters. Overdue and next seven days include **open tasks only**. The window uses server time: overdue is strictly before checked_at; upcoming is from checked_at inclusive until seven days later exclusive. Due views organize tasks; reminder notifications are not delivered by this module. Statuses in text are never inferred or executed.

Pages contain at most 25 current tasks in stable UUID order. Next page is a live keyset request, not a snapshot of the whole collection. Reload returns to the first page. The screen states the check time and number on the current page, never a global total. Concurrent changes can alter later pages. Blank results only mean no tasks match the chosen view.

Done and cancelled are explicit owner choices. Reopen returns either closed state to open; changing done directly to cancelled is refused. Correcting details preserves closure timestamps; reopening clears current timestamps while historical snapshots retain prior status. Every successful mutation advances the displayed revision. A stale revision is rejected without overwriting a newer task. Discard/reload before trying again. After an uncertain network failure, reload to check whether the change committed. Cancelling a view cannot undo a committed request.

## History, copies and forgetting

Owner history records sequential revision, actor, operation, timestamp and the full task snapshot including source, assignment, due and status. It is owner-only even for shared tasks. More history loads another bounded page. Historical status is not a claim about current progress.

Download this task page requires an explicit acknowledgement. The server rechecks current authority and the current filters/cursor. The downloaded version can differ from an older screen. JSON includes schema_version, checked_at, filters, stable IDs, owner/scope, revision, source, due, assignment and timestamps. It is an unmanaged copy of **up to 25 current tasks**, not all tasks, a history export or a backup. A creator can inspect complete history through paged history; logical backups preserve the revision journal.

Forget requires a separate confirmation. It scrubs the live title, details, source, assignment, due/status timestamps and every historical content snapshot. Minimal ID, owner/scope, revision and created/updated metadata and operation history remain. Forgotten records cannot be restored through this API. Earlier downloads and older backups can retain content; no ordinary task old-backup reconciliation or automatic copy erasure is claimed. Keep restored consumers stopped and follow the existing recovery process before acceptance.

Drafts, history views and acknowledgements exist only in component memory. Navigation, scope/session changes and access denial discard them; late/aborted results cannot repopulate an old view. A conflict retains an edit draft until explicit discard. No mutation retries are automatic. Task text is rendered as inert text; references are not fetched.

## Data and update contract

Migration **0020_manual_tasks**, after 0019, creates manual_tasks and manual_task_revisions. They are independent of the existing internal tasks table referenced by approvals/audit/jobs. SQL guards seal owner/scope/identity, revision progression, status transitions, history and deletion/truncation. Forgetting permits only null snapshot redaction after the parent tombstone. Runtime receives SELECT/INSERT/UPDATE on manual_tasks, SELECT/INSERT plus snapshot-only UPDATE on history, and EXECUTE on the fixed-search-path, non-public butler_lock_task_scope(uuid,text) helper. It still cannot administer scopes, read the shared audit journal, delete/truncate these tables or access Work content through this feature. SQL guards protect integrity; current-user visibility is enforced by application policy rather than per-user RLS.

All API operations use same-origin HTTPS JSON POST with CSRF; literal search stays in the request body. Routes are /api/v1/tasks, /query, /export and /{id}/read|correct|transition|history|forget. Only the three named scopes are accepted; unknown fields, naive datetimes and noninteger expected revisions fail closed. User, session, selected membership and selected records remain locked through audit/state commit. Session deadlines are rechecked after actual row waits. Audit metadata contains IDs/revisions/state/status/counts, not task content or search text. A failed commit releases no protected result.

Stop consumers, retain a verified backup and update migration, restricted-role setup, API and web together from the same checked commit. Use the existing Compose update/rebuild procedure preserving the project, users, volumes and host trust. A web-only update is insufficient. Downgrading to 0019 **drops both new task tables and their history**, so it is a disposable test operation or requires deliberate verified recovery and a matching application rollback. No new environment flag, dependency, secret or external service is required.

## Engineering evidence and limits

Local checks pass: make check (790 backend and 282 client tests), 33 restricted PostgreSQL task cases, the actual logical restore drill with task sentinels, migration down/up and schema comparison, dependency/security checks, and nine real HTTPS task flows with inspected desktop/mobile screenshots. Final four-job exact-head CI belongs in the delivering PR metadata. These are synthetic development/test checks; they do not establish actual owner-host/mobile recovery, reminders, external integration or production readiness. No data leaves automatically and no model, provider, job, approval or notification is dispatched.

The general/default-disabled and optional Work browser acceptance phases use independent disposable stacks so suite growth cannot exhaust a shared login-source budget across unrelated phases. Each phase retains real HTTPS and the unchanged login limiter; no counters are cleared and no tests/jobs are skipped.


Spec 047 adds the private in-app reminder candidate with explicit schedule/acknowledge/snooze/cancel, quiet/day preferences and an optional restricted service. Task due dates still do not schedule a reminder automatically; phone/email/OS delivery remains separate. See [task reminders](TASK_REMINDERS.md). Earlier statements about no delivered reminder service describe the prior implementation review baseline.
