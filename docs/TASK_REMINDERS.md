# Task reminders and private inbox — spec 047 candidate

Open your own task in **Tasks and agenda**, then choose **Schedule reminder**. Pick a future local date/time within 365 days. The reminder time is independent of the task's due date. **My reminders** shows the private in-app inbox: refresh to see new deliveries, filter one task area and state, acknowledge, reschedule/snooze, cancel or inspect history. Acknowledgement does not mark a task done. Delivered means available in Butler, not read by a person, a phone alert or an email.

A reminder is private to the task creator even when the task is shared. A household reader can read current shared tasks but cannot inspect or schedule another creator's reminder. Only household_shared, member_a_private and member_b_private are supported. No assignment directory or Work/business/care/finance reminder policy is introduced.

## Preferences and lifecycle

My reminder preferences apply across your task areas. Defaults are enabled, Europe/Paris, quiet hours 22:00–08:00 and at most five deliveries per local day. You can pause delivery, select an IANA timezone, set quiet start/end and a limit from one to twenty. Equal start/end turns quiet hours off. Pausing preserves pending requests; preferences do not start the reminder service.

Quiet hours and daily limits defer rather than discard a reminder. The server records the reason and next check time. Daylight-saving gaps/folds follow real UTC instants converted through the chosen timezone. Day counts use immutable delivery events in the current timezone, including a 25-hour local day. Acknowledgement and snoozing cannot erase a prior delivery from that day's count. Changing preferences causes due deferred requests to be reconsidered under the new revision.

Each task has one reminder record. Explicit scheduling/rescheduling advances its schedule cycle; every change advances its revision. States are scheduled, delivered, acknowledged and cancelled. Conflicts retain the draft until discard/reload. After uncertain network failures, reload before repeating a change. No mutation is automatically retried.

Task title/detail/due corrections preserve the reminder time. Reminder screens resolve current authorized task text rather than saving another copy. Closing or forgetting a task cancels scheduled/delivered reminders in the same API transaction. Reopening does not reactivate them. The worker independently checks current account, selected scope and task eligibility, including after lock waits. Revoked/inactive owners and closed/forgotten tasks cannot receive a due delivery; their pending request is cancelled when checked. The worker uses the explicitly saved intent and current permissions rather than a browser session, so normal session expiry does not stop an authorized future reminder.

## Service update and explicit activation

This is development/test functionality. Follow the existing [HTTPS update procedure](WORK_ACCESS_FOUNDATION.md), keep the same project/configuration/users/volumes/trust, stop any existing reminder service, retain a verified backup, apply migration **0021_task_reminders**, run the matching restricted-role setup and rebuild API/web together. A web-only update is insufficient. Migration downgrade to 0020 **drops all reminder records, history and preferences**; use it only on disposable data or under deliberate verified recovery with a matching application rollback.

The normal Compose stack does not start the reminder service. After reviewing the checked commit and updating the stack, the existing `butler-poc` development project can explicitly validate one pass and then elect to start the loop:

```sh
export COMPOSE_PROJECT_NAME=butler-poc
# Use the existing project's .env and checked repository; do not create a new project/volume.
docker compose --env-file .env -f infra/core/compose.yml --profile reminders build reminder_worker
docker compose --env-file .env -f infra/core/compose.yml --profile reminders run --rm -T --no-deps reminder_worker python -m app.reminder_worker --once
docker compose --env-file .env -f infra/core/compose.yml --profile reminders up -d --no-deps reminder_worker
```

Use the actual existing project name if it differs. The service requires the already-initialized database and current runtime grants. The loop checks bounded batches of up to 100 every 30 seconds; it has no provider connection and only joins the private data network. One pass prints counts, without task text, identifiers, SQL or credentials. A failed one-shot exits nonzero; the loop rolls back failed records and retries on later passes. A running container or enabled preference alone is not a delivery-health certificate.

Stop it before a schema update, rollback or restore:

```sh
docker compose --env-file .env -f infra/core/compose.yml --profile reminders stop reminder_worker
```

Stopping the service preserves stored intent. Restart catches up eligible due requests under current permissions, quiet hours and limits. A crash before commit leaves no delivery or event; another pass can retry. Concurrent workers serialize each recipient and cannot deliver the same cycle twice in one database timeline.

**After an older-backup restore, keep reminder consumers stopped**, as with existing job/Work consumers. An older database can contain a request that was later cancelled, acknowledged or delivered. Review/cancel restored pending intent and complete the existing authority/recovery gates before explicitly restarting. This feature does not supply a cross-restore delivery ledger, automatic startup fence or full-host recovery certificate. No real owner stack is activated by development or CI.

## History, export and forgetting

Reminder history is owner-only, versioned and paged in batches of 25. It records schedule/delivery metadata, cycle/revision, task and preference revisions, actor (you or reminder service), reason and timestamps. It stores no task title, details or source text. The stored task revision is the version seen at scheduling or the latest service check; a fresh current-task object can have a newer revision. Policy changes have versioned metadata audit; runtime cannot read the general audit journal.

Download this reminder page requires acknowledgement of unmanaged copies. It freshly reauthorizes up to 25 reminders, current authorized task details and preferences. It preserves the owner ID even for an empty page, stable record IDs, task provenance and timestamps but is a live page, not all reminders or a coherent whole-collection backup. History is available separately through its paged JSON endpoint. Pages can be sparse if concurrent changes invalidate candidates; an advancing cursor can still lead to another page.

Forgetting a task scrubs its normal task content/history and cancels active reminders atomically. Reminder history retains minimal scheduling/actor/reference metadata without copied task text. Inbox/export omits forgotten task text. Existing downloads and older backups can retain previous content/state; no retroactive erasure is implied.

Drafts, selected history and copy acknowledgement are held only in component memory. Scope/session/navigation/denial discard them; aborted or late responses cannot repopulate an old screen. An already committed request cannot be undone by cancelling a view.

## Data and engineering boundaries

Migration 0021 adds task_reminders, task_reminder_events and reminder_preferences. PostgreSQL guards seal identity, revision/cycle progression, valid status timing, metadata snapshot ownership/content shape and immutable history; ordinary deletes/truncates are denied. Runtime receives SELECT/INSERT/UPDATE on the two current-state tables and SELECT/INSERT only on events. It retains audit read and scope administration denial. Application policy enforces owner visibility; these public platform tables are not per-user RLS.

The worker reads only task eligibility metadata, not task text, and locks recipient user exclusively, then membership, task and reminder, through delivery/event/system-audit commit. Human paths retain current user/session/CSRF/scope authority and expected revisions. First preference writes serialize on the user; daily counts serialize across scopes. Transactional task hooks preserve the same lock order. Complete column ACL resets are grouped by table for fewer setup round trips, with stale column-grant negatives retained.

Portable IANA rules come from the locked tzdata dependency. There is no new secret or outgoing data flow. No model, device/OS push, email, recurrence, calendar connector, general provider executor or production activation is supplied. Windmill/Home Assistant/NOMAD and native accelerated compute decisions are unchanged.

Local evidence and scope analysis are in [spec 047](VALIDATION.md). Full four-job exact-head CI evidence belongs in the delivering PR metadata. Merge delivery, actual M2/mobile, independent backup/key/restore and production acceptance remain separate.
