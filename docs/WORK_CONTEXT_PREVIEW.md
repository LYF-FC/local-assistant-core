# Selected synthetic Work context preview

Spec 022 adds a reference-only API preview of explicitly selected confirmed synthetic notes. It follows merged prior implementation review confirmation. No model, automatic selection, family-work bridge, capture writer, party entry or execution is enabled. All content stays local.

Standard M2 update needs no new setup. This experiment is independently disabled. Existing adapter credentials and explicit review read provisioning from WORK_SYNTHETIC_ADAPTER.md and WORK_DRAFT_REVIEW.md are prerequisites. Keep existing users, configuration, CA and volumes. Layer `infra/core/work-context-preview.override.yml` after the base and synthetic adapter overlays when explicitly testing this feature. Review/confirmation flags are needed only to prepare/confirm a note; preview itself needs the adapter and existing read privileges.

Using the current authenticated HTTPS session and CSRF token, POST `/api/v1/work/workspaces/{workspace}/context/preview`:

```json
{
  "selections": [{"id": "confirmed-note-UUID", "expected_revision": 2}],
  "max_bytes": 8192
}
```

Use actual current synthetic note UUIDs/revisions from the explicit confirmation procedure, never employer content. Select 1–10 distinct records in one workspace. The response preserves selection order, with current snapshots/source UUIDs, exact canonical UTF-8 JSON `items_bytes`, generated time and `valid_until`. Default budget is 8192, allowed range 256–16384. Oversized content returns 413 without truncation. Stale revision returns 409; missing/unconfirmed/forgotten/expired/source-ineligible selection returns 404. The entire selection fails together. Default disabled, missing secret or role/configuration failure returns 503. Current user/session/grant/Origin/CSRF restrictions always apply.

Validity is at most 60 seconds, capped by session expiry and note retention. This is a transient snapshot, never an authorization token or saved bundle. Re-run current authorization/revision/retention checks before any future use. No UI, model invocation, prompt assembly or cache is added. Browser/API responses remain no-store.

The request retains the registry barrier through identity commit, fencing grant/workspace/source changes. Sorted draft SHARE locks prevent correction/forget during private preparation. Session and retention are checked again after private commit. Per-note private `draft.read_prepared` audit precedes metadata-only `work.context_preview` identity audit. Both must succeed before response release. A failed identity commit may leave private prepared-read audit; it does not prove content delivery. No note/hash/source content is copied to public identity audit.

No schema/dependency/privilege change. Existing note forgetting/history/export and same-database backups remain authoritative; there is no new persistent context copy to export or erase. Disable by removing the context overlay and recreating API. No migration or worker cleanup is required. Independent keys/derived-copy/older-backup/full-host recovery, real-content isolation and retained M2 acceptance remain open. Next implementation: synthetic capture and party entry.
