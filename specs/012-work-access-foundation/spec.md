# Spec 012 — Work access registry and disabled-runtime status

First bounded implementation of spec 005, not completion of Work Companion isolation.

FR-01: store only workspace identity (UUID, synthetic slug, active flag) and explicit per-user `work_private` grants in the platform identity registry. Existing household, personal and admin scopes never imply membership. Do not add work to the seven family scopes.
FR-02: authenticated HTTPS read-only API lists at most 25 active assigned workspaces per page; a selected workspace status rechecks active membership. Unknown and unassigned IDs have the same denial. No workspace names/grants are exposed through family identity, Memory, Discovery, Context or public health.
FR-03: privileged local CLI creates/enables/disables synthetic registry entries and grants/revokes membership; API runtime role cannot mutate registry. No implicit grants or automatic provisioning.
FR-04: status always reports ingestion/model/execution disabled and outstanding isolation gates; no work text, transcript, task, file, content export or connector endpoint is introduced. No data leaves the existing local authenticated origin.
FR-05: append content-free identity audit and commit before releasing metadata; audit/commit failures return sanitized unavailability. Audit UUIDs, not workspace slugs or text.
FR-06: UI explicitly loads assigned workspace metadata only on request, clears prior status during refresh/selection/denial/unmount/sign-out, and never stores work data in browser persistence.

Acceptance: positive explicit membership; family/admin-only denial; cross-workspace denial; revocation, disabled user/workspace/session; bounded pagination; read-only database grants; no implicit family work scope; no data-ingestion route; API/client/browser checks and migration round trip. Real work content remains blocked until separate roles/storage, retrieval/context/cache, jobs, work audit, export/key/retention and recovery boundaries pass their own tests.
