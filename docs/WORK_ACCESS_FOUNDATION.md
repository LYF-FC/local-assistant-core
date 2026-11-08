# Work access foundation — development/test, synthetic only

Spec 012, merged through #34, is the first implementation step toward SHARED Work Companion (spec 005, issue #25). It is an identity registry and disabled-runtime status, **not full work isolation or a debrief pilot**. No work text, documents, recordings, models, connectors, exports or actions are enabled. No new dependency or external data transfer is introduced.

## Boundaries implemented

- Migration 0006 adds `work_workspaces` and `work_access_grants` to the platform identity registry. Entries contain only UUID, synthetic slug, active flag and timestamps; grants bind a user to one workspace and `work_private` capability. No workspace is seeded and no existing user receives a grant.
- Keep the seven family scopes unchanged. `member_a_private`, `technical_admin` and the user's name confer no work membership. Family identity output does not expose workspace metadata. Memory/Context/Discovery do not retrieve this registry as content.
- The restricted `butler_runtime` role has SELECT only on both registry tables. Grant/create/revoke/enable/disable require the trusted local migration connection. This is administration metadata on the shared identity connection; it is not the future dedicated work-content role/schema.
- HTTPS/session/Host checks and active-user checks precede SQL membership filtering. Lists contain only active assigned workspaces (1–25 per page, UUID cursor); selected missing/unassigned/disabled IDs return identical 404 responses.
- Successful reads and denied attempts are audited and committed before metadata is returned. Audit contains event/actor and authorized workspace UUID, never slug, transcript or source text. Existing identity administration audit rights apply to this registry only; separate work-content audit remains a prerequisite.
- Revocation and user/workspace/session disablement take effect on subsequent requests without signing in again. Already-observed registry metadata is a snapshot, not a content permission or real-time revocation guarantee.

## Update an existing M2 checkout over HTTPS

Run from the existing checkout, with the same local Docker project and `.env`. This returns a pinned/detached reinstall checkout to the tracking main branch, preserves named volumes and rebuilds the application. Do not recreate existing POC users.

```bash
(
  set -euo pipefail
  test -f .env
  test -z "$(git status --porcelain)" || { echo 'Commit or preserve local changes before updating.'; exit 1; }
  git remote set-url origin historical private reference omitted.git
  git -c protocol.ssh.allow=never fetch origin
  git switch main
  git merge --ff-only origin/main
  git branch --set-upstream-to=origin/main main
  export COMPOSE_PROJECT_NAME=butler-poc
  export BUTLER_LOCAL_CA_FILE="$HOME/Butler/exports/butler-poc-root.crt"
  bash scripts/first-run.sh
  bash scripts/healthcheck.sh
  git log -1 --oneline
)
```

Main includes this Work Companion screen through merged #34. If you used its preview branch, the main procedure above now safely returns to a tracking main containing migration 0006. For any newer migration-bearing candidate, remain on its checked branch until main includes that migration; do not rebuild an older main against a newer database. Any rollback needs a separately reviewed backup/downgrade and role-grant procedure.

Updating source alone does not rebuild the served container; run first-run and healthcheck, then reload the browser. Keep the two exports for each subsequent terminal. Never use `down -v` or volume prune for an update. Existing CA volume/user trust is retained.

## Synthetic workspace acceptance

After migration/build on the checked candidate (or merged green main), sign in as `poc-owner`, choose Work Companion and press **Load assigned workspaces**. Initially it should report no active workspaces. The panel makes no work request until explicitly loaded.

In the same checkout/terminal with both exports above, use the trusted local operator commands:

```bash
docker compose --env-file .env -f infra/core/compose.yml run --rm migrate python -m app.work_manage --environment development create-workspace --workspace synthetic-poc
docker compose --env-file .env -f infra/core/compose.yml run --rm migrate python -m app.work_manage --environment development grant --workspace synthetic-poc --slug poc-owner
```

Reload the assigned list and select `synthetic-poc`: explicit grant confirmed, ingestion disabled and five remaining isolation gates displayed. The viewer sees no assigned workspace even with the same family scopes. No family scope changes are needed.

Revoke the owner while signed in, then select/refresh again:

```bash
docker compose --env-file .env -f infra/core/compose.yml run --rm migrate python -m app.work_manage --environment development revoke --workspace synthetic-poc --slug poc-owner
```

Expected: prior selected status clears, access is unavailable, reload shows no assigned workspace. Re-grant to restore the synthetic check. `disable`/`enable` with `--workspace synthetic-poc` disable/enable that workspace without changing grants. Membership administration does not enable work processing.

## Still required before professional content

Dedicated least-privilege work content namespace/connection and workspace enforcement; isolated documents/keys and retrieval/context/history/caches; workspace jobs/credentials; content audit/observability; retention/export/deletion and isolated backup/restore. Then a synthetic text-debrief/review pilot with grounded unknown owners/dates. Real employer access and work policies remain separately authorized. Technical operators share the host/admin failure domain.

No route accepts debrief content. The generic family Memory API cannot classify arbitrary text pasted into a family scope: users must not place employer records there. A status check or grant is never authority for a future content API or model dispatch. No production readiness is claimed.

## Next storage boundary

Spec 013 candidate adds private synthetic storage validation without enabling ingestion or application connections. See [WORK_STORAGE_ISOLATION](WORK_STORAGE_ISOLATION.md). Current five content gates stay disabled/pending; schema probes do not constitute real content acceptance.
