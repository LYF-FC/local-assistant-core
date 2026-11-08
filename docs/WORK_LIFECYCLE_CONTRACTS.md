# Work record lifecycle — executable synthetic contracts

Spec 018 provides an immutable, deterministic contract library and synthetic tests in `app.work_lifecycle`. It prepares the next storage increment. It is **not** a work-content database, route, UI, debrief recorder, source authorizer, retention scheduler or real export/deletion service. No family/work/employer records or keys are created, imported or processed. Nothing leaves the local process. Existing five Work content gates remain pending; the optional spec 017 adapter still reads only its fixed synthetic validation table.

## Record and transition contract

A synthetic record carries a stable record/workspace/policy UUID, revision, kind (observation/question/decision/action), draft/confirmed/forgotten state, synthetic marker, up to ten distinct source UUIDs, nullable owner/deadline, explicit retain-until, actor UUID and aware creation/update times. Marker/source fields are omitted from model representations. Frozen models and tuples avoid accidental in-place changes; Python objects are not a hostile-code security boundary. Synthetic-prefix validation does not detect actual employer content disguised with a prefix, so no content ingress is opened.

| Operation | Preconditions | Projection/result |
|---|---|---|
| Create | Typed server metadata; explicit workspace-bound retention policy; aware server time; positive bounded expiry | New server-allocated UUID/revision 1, draft, unknown owner/date/source preserved |
| Confirm | Expected current revision; live draft; selected source references | New revision marked human-confirmed; payload unchanged; no assignment/tool/execution approval |
| Correct | Expected revision; live current record; same kind; no retention extension | New draft revision requiring review again; previous snapshots preserved |
| Expiry | Evaluated server time >= retain-until | Unavailable to confirmation/correction/export preview; no scheduler/physical deletion implied |
| Forget | Expected current revision; same workspace; aware monotonic time, even after expiry | Redacted projection of every revision plus a terminal tombstone; repeated forget returns the same projection |
| Export preview | One workspace, <=25 distinct current histories, aware time | In-memory current records only; expired/forgotten omitted; drafts excluded unless explicitly requested |

The pure helper receives record UUID/time from trusted server metadata; it does not call a clock/random generator or perform I/O. The future adapter allocates IDs outside the untrusted payload. Owner UUIDs refer to future workspace-local work parties/entities, not implicit links to household users or global colleague records. Non-null owners require current workspace validation before any assignment. A source UUID is provenance metadata, not proof of source access. Future storage must check each source in the current workspace under fresh identity/grant authority before confirming or exporting. A caller-supplied actor/workspace UUID is not authentication. No lifecycle route accepts these objects; the future service must resolve actual user/session/workspace permissions using the merged registry transaction guard. Family/private/admin membership alone grants no work-content access.

## Explicit retention and unknowns

There is no installed retention policy or default TTL. Every creation requires an explicit workspace-bound policy ID and maximum age; retain-until must lie within it. The synthetic contract's maximum-age ceiling is one year, not an approved production retention duration. Tests use example values only. Choose actual raw-recording/transcript/draft/confirmed-note/source/derived/export/backup retention separately with the owner and relevant employer policy before capture.

Unknown owner/deadline/source is represented as null/empty draft provenance, never guessed or converted into done/not-required. Confirmation of an action note does not invent an assigned owner/date or make a commitment. Correction resets human review and cannot renew the original retention deadline. Retention renewal, holds/exceptions and access-policy changes need separate explicit operations and audit; none is supplied here.

In-memory history is bounded to 100 live revisions, plus one terminal forget revision. Reaching the live history bound must not prevent forgetting. Future durable storage must support bounded/paged review and atomic set-based redaction without assuming all historical payloads fit in process memory.

## Transactional persistence requirements — next increment

The library models optimistic revision checks; it does not implement database concurrency. Future storage must provide all of these in one reviewed boundary:

1. Resolve current user/session/active workspace/source grants with the existing registry lock order, before leasing a work connection. No client-supplied authority, cached permission or cross-workspace source lookup.
2. Require an explicit human review action before calling confirmation; model confidence or merely invoking a Python function is not evidence of human approval. Validate any non-null work-party owner reference within the same workspace.
3. Lock the current composite `(workspace_id, record_id)` row, compare expected revision atomically, and reject stale writes. Request retries need a separately specified payload-bound idempotency contract; no blind retry after ambiguous commits.
4. Persist current state, correction history, expiry/forget tombstone and minimal work audit transactionally; expose no response until required work and identity commits succeed. Independent commits retain the existing honest prepared-event semantics.
5. Enforce workspace RLS and explicit least-privilege column/function grants for every new table. Existing synthetic marker roles do not automatically receive new domain grants. Avoid cross-scope existence leaks through foreign keys/errors.
6. Keep payload/title/transcript/owner details out of shared logs and immutable audit. Work audit review/export gets its own current permission contract.
7. Check expiry again before payload release and after connection cleanup. No confirmed decision/action silently executes a tool, sends a message, creates a family reminder or invokes a model.

No migration, table grant, key bootstrap or capture endpoint is delivered in spec 018. The pure helper is not added to the live broker; wiring it in before the storage/source/audit acceptance would bypass these requirements.

## Forgetting, derived copies and restore suppression

The forget function returns a new redacted history: markers, source associations, owner/deadline and retention payload fields are cleared across every supplied revision. IDs/revisions/kind/actor/time metadata remain for the synthetic tombstone/audit contract. Its returned value does not erase prior Python references, stored blobs, caches, indexes, exports, process memory or backups. It does not cryptographically prove deletion.

Future forgetting must atomically redact the current row and all revision payloads, clear source joins and any payload-derived hashes, and persist a minimal workspace/record suppression tombstone. Inventory and reconcile derived summaries, prompt/history/cache, embeddings/search, queued jobs, attachments and tracked exports; stale work must be denied while purge/rebuild is pending. A correction likewise invalidates derived material before it can claim current evidence. No automatic bridge into family Memory/Discovery, care/finance, business, notifications or NOMAD.

Restore must reconcile suppression tombstones newer than the restored backup before enabling readers or rebuilding indexes. Restoring an older database must not silently resurrect forgotten payloads. Offline backups/export copies may retain material until their separately chosen expiry; do not claim immediate deletion of inaccessible copies. Tombstone/backup/export retention, revocation of restored sessions and key recovery need independent operational acceptance (#5).

## Namespace and key design — specified, not implemented

Reserve a work-only logical namespace keyed by immutable workspace UUID for content, documents, indexes, cache/context, jobs, exports, audit and backup manifests. Human employer/workspace slugs are labels, not filesystem traversal or encryption-key selectors. No global family+work retrieval collection or shared document credential is allowed by this design.

Document encryption keys must have a workspace-specific lifecycle, key ID/version, locked access, rotation/recovery/revocation and restore policy reviewed independently of PostgreSQL login passwords. The optional adapter secret volume stores a database login secret; it is **not** a document-encryption key store. Filesystem permissions and logical schema isolation do not by themselves deliver encrypted-at-rest storage or independent key recovery. Do not choose/activate a cryptographic implementation or destroy keys as a deletion shortcut in this increment.

## Export preview limits

`export_preview` returns a versioned in-memory envelope for one workspace and bounded selected histories. It validates lineage/revision order, stable identity/kind/policy, monotonic clocks, non-extending retention, confirmation payload preservation and full-history redaction. Only each supplied current revision is projected; source authorization and proving that a history is the actual latest stored history remain future storage responsibilities. Cross-workspace, duplicate, malformed or oversized selections fail instead of being silently truncated. Owner/date unknowns remain null.

No file/download/export job or encrypted manifest is created. Future exports need explicit current permissions, a preview, schema/provenance/timestamps, approved destination, local audit and tracked expiry/deletion; exporting is not authority to import into another boundary.

## Verification and delivery

Unit tests cover strict server-field rejection, immutable snapshots, unknown preservation, explicit policy/time/workspace binding, grounding/confirmation, correction reset and retention non-extension, stale revisions, malformed lineage, expiry boundaries, terminal full-history redaction including the history limit, and bounded current-only export. Existing API tests retain five pending content gates and reject absent record/debrief routes. Full existing PostgreSQL/migration/restore/TLS and synthetic adapter checks must remain green.

ROADMAP.md marks merged prior implementation review Done with its delivering PR; lifecycle contracts remain In progress until this PR merges. Next is transactional work draft/source/history/forget persistence with synthetic fixtures and negative tests, followed by isolated context/jobs and a synthetic debrief/action pilot. No employer content, automatic recording, external models or production deployment is authorized by these contracts.
