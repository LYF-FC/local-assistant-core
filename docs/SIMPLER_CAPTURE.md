# Simpler manual capture and later enrichment

Spec 044 is merged in prior implementation review. It addresses the Memory/Discovery form friction reported in issue #33 (historical private reference omitted). It adds an honest evidence-free idea stage and later editing, rather than filling hidden fields with invented evidence or dates. No research, model, source fetch, installation, experiment or approval is triggered.

## What changed in the forms

| Field | Initial capture | Later detail / existing records |
|---|---|---|
| Memory content | Explicit required text | Full text is preserved |
| Memory title | Visible editable excerpt of first nonblank line | Existing title preserved; corrections remain explicit |
| Memory access and type | Visible existing assigned choices | Scope/type stay locked during correction |
| Memory source/assessment | Visible summary: manual, Manually entered, Tentative | Expand source/assessment details to choose or correct; existing assessments preserved |
| Memory expiry | Optional disclosure for ordinary records | Temporary context expiry stays visible and required |
| Discovery idea | Summary, visible editable title and private access | Optional topic starts as unclassified |
| Discovery evidence | Empty, explicitly labelled no evidence | Supply title, inert public HTTPS reference and actual observed date when available |
| Discovery assessments | Not assessed; experiment Not proposed | Optional disclosure; no inferred values |

Title suggestions are deterministic excerpts, not summaries. They respect the existing 160-unit client title bound without splitting a Unicode code point. The full content is not truncated. An edited title is never silently regenerated. Drafts remain in browser memory; no localStorage or autosave is added.

## Memory capture

Choose Add memory, enter Details and review the suggested title, access and type. New entries default to Tentative. Expand source/assessment details when you want to supply another reference or explicitly confirm your own assessment. This changes only the new-form default; existing records are not reclassified. Temporary context still needs an explicit expiry. The existing Memory availability flag is not a complete Context eligibility decision: the separate Context service requires confirmed ordinary records and excludes module envelopes. The browser acceptance test checks that actual candidate service.

Corrections retain the existing revision/owner/scope, preserve source-maintained structured content and leave existing assessments untouched until you change them. History, page export, forgetting and their separate backup/export-copy limits remain unchanged. See [Memory interface](MEMORY_INTERFACE.md).

## Capture an idea, then enrich it

Choose Add idea in Discovery, enter the idea and review its excerpt title/private access. No evidence date or URL is required because this is an idea, not an evidenced proposal. The saved record explicitly has stage idea, no evidence, tentative assessment, topic unclassified unless chosen, and unassessed fields. It appears in the normal owner-private list with an Idea - no evidence label. Interest is still interest only.

When you have a source, open the idea and choose Add evidence and enrich idea. Supply topic, summary and 1–5 manually reported evidence references, with each source's title, public HTTPS URL and explicit observed date. Existing validation rejects private/credential-bearing URLs, invalid/future/naive dates, overflow and extra authority fields. URLs remain inert text and are never fetched. Optional assessments and experiment can stay unknown.

Save reviewed details checks the exact displayed revision and promotes the idea to a version-2 manually reported proposal. It preserves feedback, scope, owner, expiry and the existing record assessment. A canonical no-evidence source reference is changed to the manually reported unverified-proposal reference; an owner's custom source metadata stays intact. Confirmed record assessment is an explicit owner's assertion, not source verification. The old idea snapshot and subsequent changes remain in Memory history.

Add proposal remains available for fully evidenced initial entry. Existing version-1 proposals still list/read/rank/receive feedback as before and can use Edit proposal details. The editor loads every evidence row, supports explicit add/remove up to five, and preserves the exact original offset/fractional timestamp when that row's observed date is not edited. Editing another field does not silently round an observed date. Blank assessments mean Not assessed; an experiment remains Not proposed.

## Conflict, privacy and authority

Details and feedback share the existing row lock and expected-revision boundary. Concurrent writes cannot overwrite each other. A conflict keeps the local details or feedback draft, disables its submit and requires explicit discard/reload. Access/session denial clears cached private form/list/detail data. Session changes, sign-out and navigation unmount abort requests and suppress late UI side effects. Cancelling or leaving before submission does not save a draft; aborting after deliberate submission cannot undo a transaction already committed by the server.

Both new endpoints remain owner-private and require current scope/session/Origin/CSRF. They reuse Memory transactions, minimal audit, revision history and full live-history forgetting. Audit or commit failures roll back content/history. No new scopes, grants, schema, jobs, approvals, provider, connector or external send is added. Existing Work source/policy/retention choices are not defaulted away; real Work content and independent owner-host/recovery acceptance remain separately gated.

## API, storage and updating

`POST /api/v1/discovery/ideas` accepts title, summary, private scope and optional topic. `PUT /api/v1/discovery/{id}/details` accepts displayed expected_revision plus typed title/topic/summary/evidence/optional assessments, without owner/scope/feedback overrides. The existing fully evidenced create and feedback contracts remain valid.

Content envelopes retain record_type discovery_proposal. Version 1 stays unchanged; version 2 requires an explicit idea or proposal stage. Idea evidence must be empty; proposal evidence must contain 1–5 references. Invalid/mixed/unknown envelopes fail closed. Memory JSON export/history naturally carries the versioned content; no SQL migration or separate report/content store exists.

Update API and web from the same checked commit and rebuild the existing stack while preserving its project, users, volumes and host CA trust. Older clients do not understand version-2 content and must not be paired with the new API. No new flag, credential or dependency is needed. Test fixtures belong only on disposable synthetic test stacks.

## Verification and acceptance

New backend tests cover idea unknowns, v1 compatibility, later evidence/feedback preservation, provenance, history/export/forgetting, strict envelopes, invalid input, private ownership/current-scope/session/Origin/CSRF/expiry, stale writes and audit/commit rollback. Four new real PostgreSQL cases plus the existing two Discovery cases verify restricted-runtime persistence, concurrent feedback/details, rollback and revocation. The actual logical dump/restore now checks v2 ideas, enriched evidence, feedback and pre/post-enrichment history alongside all existing recovery drills.

Twelve new client cases cover title bounds and v1/v2 transport/parser behavior. Six new real HTTPS cases cover minimal capture, progressive controls, explicit evidence/enrichment, multiple-source and fractional/offset timestamp preservation, conflicts, injected denial, held actual-response cancellation, temporary expiry and draft discard. All 13 focused Memory/Discovery browser cases pass; desktop/mobile screenshots are inspected. Local browser CA trust lives only inside disposable Linux containers. Existing guards were not relaxed for testing.

Final exact-head four-job CI is recorded in the PR without an evidence-only source push. The roadmap stays unchecked until merge. Issue #33 remains open pending merged delivery and the owner's UX assessment; this is not full Discovery-agent or owner-host/production acceptance.

## Merged delivery

Merged prior implementation review (historical private reference omitted) at `historical-source-reference-omitted`. Exact head `historical-source-reference-omitted` passed all four jobs on attempt 1 in run 42405172034 (historical private reference omitted): 721 backend, 573 PostgreSQL, 224 client and 45 browser tests, plus complete restore/TLS/container checks. Six commits, one push and one PR CI run delivered simpler capture and later evidence enrichment. Issue #33 remains open for owner UX assessment; independent operational and real Work gates remain open.
