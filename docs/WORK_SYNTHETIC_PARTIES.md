# Synthetic parties and explicit note owners

Spec 023 introduces a private synthetic party registry before authenticated capture. A party UUID represents an explicitly selected work owner; actor_id remains the human who authored/reviewed a note. Null owner_id means unknown. Never infer an owner from the user, note text or family profile.

Only synthetic development/test storage is supported. No real colleague names, email, employer source, connector, model or external transfer. This adds trusted local primitives and a local command, with no party UI/API writer, background process or new API/runtime/workspace-role party privileges. Standard M2 update needs no special activation; migrations run normally. Existing API previews may expose an explicitly stored owner UUID, never a copied party label or inferred assignment.

## Explicit local procedure

Use the existing environment/Compose configuration, active synthetic workspace, retention policy and trusted migration connection. Keep existing users, CA, secrets and volumes. The command requires the configured environment to match `--environment` and a disposable butler_test database in test mode. Run from a short-lived migration container; never put its credentials in API.

```sh
docker compose -f infra/core/compose.yml run --rm -T migrate \
  python -m app.work_parties --environment development --workspace WORKSPACE_UUID \
  create --policy POLICY_UUID --marker synthetic:example-party \
  --retain-until AWARE_ISO_TIMESTAMP
```

Replace workspace/policy/time placeholders with current synthetic values. Retention must be future, timezone-aware and within that workspace policy. Output contains only party UUID, revision and state. Creation starts active revision 1. The synthetic marker is immutable; replacement requires a new identity, never renaming an existing owner.

```sh
docker compose -f infra/core/compose.yml run --rm -T migrate \
  python -m app.work_parties --environment development --workspace WORKSPACE_UUID \
  retire --party PARTY_UUID --expected-revision 1

docker compose -f infra/core/compose.yml run --rm -T migrate \
  python -m app.work_parties --environment development --workspace WORKSPACE_UUID \
  forget --party PARTY_UUID --expected-revision 2
```

An active party can also be forgotten directly with expected revision 1. Retired/forgotten parties cannot reactivate. Retire preserves the synthetic label for historical inspection; forget scrubs the label, retaining minimal UUID/policy/time/state/revision metadata and content-free audit. Unknown/expired/retired/forgotten/foreign-workspace parties cannot be newly assigned, corrected into a note, or used for confirmation. An already queued confirmation becomes denied if its selected party is retired/forgotten before local execution. No assignment means no owner; it never defaults to the author.

Historical note reads preserve the original UUID even after party retirement/forgetting; they do not authorize a new assignment. No label is copied into note revisions, review hashes, public audit, family context or derived stores. Existing note forgetting remains available after party retirement and scrubs owner UUIDs from current payload and all historical snapshots. These are different operations: forgetting a party label does not erase an independently retained note or its historical owner UUID. Expiry ends eligibility; physical retention cleanup and independent backup expiry remain separate gates.

## Transaction and recovery boundary

Local commands require an explicit READ COMMITTED transaction with the actual clean table-owner login. Assumed roles, ordinary runtime credentials and non-synthetic workspaces fail closed. SQL guards enforce the party lifecycle even for direct owner SQL. Current party eligibility is enforced at both Python and SQL note-write boundaries. Party mutations take the existing exclusive registry barrier before row changes, serializing against note/read/confirmation transactions. Private party audit, mutation and minimal public operator audit share one transaction; errors roll everything back. No human session or work capability is created by a local operator action.

Back up identity, parties and notes together. Existing versioned note exports preserve an owner UUID; there is no new application party export. Full database backup/restore retains the party mapping, states, label redaction, immutable audit and workspace/role isolation. Normal role provisioning still grants no party access. CI's explicit synthetic read inspector is separate from deployed grants.

Before downgrade, stop local party/note writers and take a verified backup. Migration 0013 refuses while any current or historical note snapshot contains owner_id. Correcting a current note to unknown does not erase its earlier reference. Deliberately forget affected notes using existing lifecycle controls first. Downgrade then removes party/audit tables and restores the null-owner constraint; it is destructive and not an erasure shortcut. Independent keys/derived/older-backup/full-host recovery, retained M2 acceptance and real content remain open.

Next: authenticated synthetic capture using explicit source/policy/party validation; then remaining isolation/recovery acceptance before a debrief pilot.

Spec 030 adds an explicit bounded expired-data cleanup path while a synthetic workspace is disabled; see [WORK_RETENTION](WORK_RETENTION.md). There is still no automatic deletion schedule or independent older-backup suppression.
