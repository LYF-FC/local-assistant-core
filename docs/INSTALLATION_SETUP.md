# Installation setup foundation — spec 060

Merged [PR15](https://github.com/LYF-FC/local-assistant-core/pull/15) delivers partial foundations for [INSTALL-01/02/03/06/08](FEATURE_REGISTER.md); exact feature-head CI run42663955214 passed all six jobs. This is a bounded foundation for [configurable installations](CONFIGURABLE_INSTALLATIONS.md), not acceptance of their full contracts. This engineering feature approved no new scope; the separately approved [later review programme](DEFERRED_REVIEW_PROGRAMME.md) now adds six planned supporting references.

## Administrator flow

Use existing trusted local account provisioning and an explicitly granted `technical_admin` scope. There is no public bootstrap, default password or invitation endpoint. Technical administration grants no access to unrelated private content. The navigation entry appears only for administrators; the server independently checks current identity/session, grant, Origin and CSRF on every operation.

Open **Installation setup**. An upgraded empty configuration starts at revision 0 with no installation UUID. Choose an ordered unique list of one to three languages (`en`, `fr`, `es`, first preferred) and a valid IANA timezone, then preview and explicitly apply. These values are setup defaults/templates only: existing user preferences and domain timezones are not rewritten. The UI's unconfigured draft is en/UTC, not an inferred household preference or automatic saved choice.

First apply creates a local random installation UUID. Later edits and template imports preserve it. Preview pins the current UUID/revision and exact normalized payload to the current session for at most five minutes; apply requires explicit confirmation. Edited fields invalidate preview. Expired/changed/conflicting requests need explicit reload/review; there are no automatic mutation retries. Same-value applies audit a no-op without consuming history. Changed applies atomically update configuration, append history and commit metadata audit before releasing a receipt.

History is immutable and limited to100 revisions, five per page. At the limit, changed writes stop; read/history/export and same-value confirmation remain available. Decommission, installation deletion and history compaction require a separately designed lifecycle; no delete route is supplied. Drafts/receipts stay in memory and clear on view/session changes. Denial clears sensitive results; conflicts preserve the draft until the administrator reloads.

## Templates, backups and identity

The downloaded `butler-setup-template-v1.json` is the inner template object:

```json
{"schema_version":1,"defaults":{"languages":["en"],"timezone":"UTC"}}
```

Paste this JSON into **Setup template JSON**, load it into the draft, preview and explicitly apply. Unsupported versions, unknown fields, installation/user IDs, host paths, credentials and feature flags reject. Input is bounded to4096 characters and the server validates schema and IANA timezone independently. The API export envelope marks `export_kind:setup_template` and `managed_copy:false`; the browser downloads only its template member so the file can be imported directly.

Only languages/timezone are exportable. They can still reveal preferences/location, so an administrator must review stored values and acknowledge unmanaged copy limits. No installation/member/workspace IDs, revision/actor timestamps, operational records, endpoint/path/model identifiers, secrets or receipt tokens enter the template. Downloads cannot be revoked or tracked. No data leaves except an explicitly downloaded template; this feature makes no outbound provider requests.

A setup template is not a backup. Independent initialization from it creates a different installation UUID and requires separately provisioned users/credentials. Logical backup/restore preserves the original UUID/configuration/history. The independent-dataset test proves this configuration boundary only; it does not certify whole-domain isolation, foreign-backup adoption or complete INSTALL-09 portability.

## Readiness and remaining scope

The static fourteen-capability catalogue has stable keys, known acyclic dependencies and mandatory foundation markers. It distinguishes development availability, setup required, operator setup, environment-disabled, configured-but-unverified and separately authorized live providers. It reads only coarse environment booleans. No filesystem/network health probe or sensitive configuration value is returned. Every entry explicitly has `activation_control:not_provided` and `live_verified:false`.

Readiness is informational. Existing environment controls, grants and worker startup remain authoritative. There are no switches, cascading disable semantics, new worker enforcement, dynamic household membership, secure first-owner onboarding, secret management, live integrations, production activation or private-data migration in this batch. INSTALL-04/05/07/09–12 and unfulfilled portions of INSTALL-01/02/03/06/08 remain open. All 149 references and full original outcomes remain retained.

## Migration, recovery and evidence

Migration 0030 creates a sealed singleton and append-only matching revision snapshots. Runtime grants omit deletion/truncation and history updates; database triggers also protect root identity, creation time, revision progression, shape/size, current administrator attribution and snapshot correspondence. A dedicated fixed-purpose membership-lock function permits only `technical_admin`; task scope authority is not widened. Fresh migration creates unconfigured revision 0, not an initialized installation.

Take and verify a protected backup before any separately authorized upgrade. Downgrade drops installation configuration, identity and history; restore the reviewed pre-upgrade backup if rolling back. Continued settings writes by older binaries are not certified. Database dumps remain private and need the existing restore/quarantine procedures; a setup template cannot recover identity or domain records. No existing private installation is upgraded by this work.

[Spec060](../specs/060-installation-config/spec.md) and [convergence](../specs/060-installation-config/convergence.md) record acceptance and exact local checks. Native integration/restore uses the fixed postgres owner, while fresh Compose HTTPS testing uses default butler and restricted butler_runtime. Browser fixture provisioning proves actual users-table ownership and runtime refusal before privileged seeding. Required hosted CI is full because this batch changes application, authorization and schema; local passes are not exact-main or production acceptance.
