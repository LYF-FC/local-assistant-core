# Discovery review inbox and reviewed digest

Spec 045 is merged in prior implementation review (historical private reference omitted). It groups private inbox search/facets, explicit selected review, cited Markdown copies and current authority/privacy checks into one capability. This is a manual local review workflow, not a collector, notification digest, research result or permission to act.

## Find records in the private inbox

Apply a literal title/summary search, exact topic, evidence stage and current-interest filter. All filters intersect with the current user's assigned private scopes and ownership. A percent sign or underscore is literal text, not a wildcard. Stage distinguishes evidence-free v2 ideas from v1/v2 manually reported proposals. Unanswered means no current interest choice; a feedback note alone does not imply interest.

Search runs on the server over authorized records, not just the displayed page. Pages remain live, bounded at 25, ranked by the existing explicit interest scores. They are not a complete or stable global inventory. Filter changes and feedback restart paging. Covered/not-relevant records still require Include dismissed proposals, even when selecting that interest filter. Reset returns to the default view.

The new inbox uses a CSRF/Origin-bound POST body so private search text does not appear in URLs or audit metadata. The existing GET listing remains compatible for older callers. No generalized topic preference or inferred interest is created by filtering.

## Review an explicit selection

Choose Prepare a Discovery digest. Select one private access area and one to ten records from the current page, then preview. Changing private access clears the selection. No automatic paging, cross-scope combination or partial fallback occurs. The title is a browser-only annotation; it is not sent to the API or represented as server-signed business state.

Review every selected idea/proposal, summary, topic, current interest, assessment/unknowns, feedback, manually reported sources/observed dates, record UUID/revision, source metadata and expiry. Source URLs are inert text. An idea's missing evidence and observed date remain Unknown; assessments are not invented. A confirmed record assessment is the owner's assertion, not independent source verification. Interest never authorizes collection, file access, an experiment, installation or deployment.

A preview lasts at most 60 seconds, bounded further by session expiry and the earliest selected record expiry. The server checks current owner/private scope/session/CSRF, locks identity/membership/selected records through preparation and audit commit, and binds an immutable metadata receipt to the exact ordered content, scope and current session. Records are locked in UUID order but rendered in your selection order. Missing/forgotten/expired/invalid/stale/cross-owner/cross-scope or over-budget selections refuse as a whole.

## Keep a reviewed copy

Acknowledge the separate-copy limits before downloading. Download must supply the exact committed preview reference/hash and acknowledgement. The server checks the receipt, re-reads all selected records, checks current authority/content/revisions and rechecks time/session after lock waits. A slow commit cannot release an expired bundle. Fresh response metadata has a new export ID; only that freshly checked response is used to build Markdown. Repeated explicit downloads may reuse a still-current review within its lifetime; this is read preparation, not a one-time action approval.

The document includes stable record/source citations, current interest/unknowns, source/version provenance, timestamps and the selected copy-expiry boundary. Evidence URLs use literal code spans, including references containing Markdown delimiters; the client generates no source links or executable HTML. JSON is limited to 64 KiB and Markdown to 128 KiB, without truncation. Select fewer records if over budget. Filenames use a public export UUID, not a private title.

A downloaded file is unmanaged. Butler cannot recall it after forgetting, expiry, access revocation or a correction. If any selected record has an expiry, the earliest applies to the whole copy. If none states an expiry, the file explicitly says so rather than inventing a retention date; manage it yourself. Preparation receipts prove neither actual saving/deletion nor source truth, complete/latest inbox coverage or human approval. A trusted database owner can forge metadata; these hashes are not independent signatures or a recovery certificate.

## Private-state lifecycle

Title/selection changes invalidate preview and acknowledgement. Filtering, paging, reading another record, creating/editing/saving feedback, refreshing or closing the review clears it. Expiry, refusal, session changes and navigation abort outstanding requests and suppress late payload/file side effects; Blob URLs are revoked. Drafts and previews use browser memory only, with no localStorage/autosave. A stale digest is handled separately from a feedback/details conflict so it cannot trap an unrelated draft. Refresh the inbox before reselecting a changed revision.

Aborting a request cannot undo preparation already committed by the server, and it cannot recall an already requested file. The audit describes preparation only. Original/source/latest/key/other-derived/full-host/retained M2 and real Work acceptance stay separate; the digest cannot cross into Work data.

## Database and update requirements

Migration `0019_discovery_digest_checks` adds two fixed-search-path, non-public SECURITY DEFINER helpers. One locks the selected private membership; the other verifies one exact actor/session/scope/hash/count preview and returns only its deadline. Runtime setup grants EXECUTE on those two helpers. The application still cannot SELECT audit_events or UPDATE user_scopes. There is no new content table, broad table grant, provider, secret or dependency. The narrow helpers are part of current application authority, not transferable content permissions.

Update API and web from the same checked commit, run the normal migrations and restricted role setup, and preserve the existing project/users/volumes/host CA trust. No new environment flag or credential is needed. A web-only update cannot provide the new endpoints, and an old role setup cannot grant the new narrow helper calls. Migration downgrade removes the helpers without altering saved ideas/proposals or audit history; stop consumers and use a reviewed matching application rollback rather than mixing versions.

Existing logical backups carry preview metadata, not a stored digest body. The restore drill verifies metadata preservation with the originating session retired and private grant removed; copied receipts do not restore current authority. Existing global restored-session quarantine and independent full-host/key/recovery acceptance remain necessary. Never run synthetic fixtures on the owner's POC or real records.

## Engineering verification

Local make check passes 760 backend and 250 client tests, Ruff/format, production build and policy. Thirty-nine new backend cases cover filters, exact receipt/content/session/deadline/order/size binding, strict input, owner/scope/session/CSRF/Origin/refusal, audit/commit rollback and slow-commit expiry. Fourteen focused PostgreSQL cases pass (eight new plus existing Discovery cases), including actual row waits, session/review expiry, raw scope/user revocation fencing and proof that only the narrow helpers execute while audit reads and scope writes still refuse. Migration upgrade/downgrade/upgrade was exercised on a separate disposable database.

The complete logical dump/restore passes at head 0019, including digest receipt metadata/retired-session checks and all existing RLS/forgetting/session/credential/source/recovered-key/dual-receipt/post-reconciliation checks. Full final 581-case integration remains required in hosted CI. Twenty real HTTPS Memory/Discovery cases pass, including seven new inbox-to-file/filter/invalidation/stale/injected-denial/held-actual-response/expiry/unmount cases. Existing capture/evidence precision, structured correction, ownership/XSS/history/export/forget/conflict/sign-out regressions remain. Desktop/mobile screenshots are inspected. Local browser trust stays in disposable Linux containers, not the owner's CA store.

Twenty-six new client cases verify strict parsing/transport, annotation exclusion, literal references/citations/unknowns/copy limits and output caps. Final exact-head four-job hosted evidence belongs in the PR, without an evidence-only source push. ROADMAP remains unchecked until merge. Full Discovery collectors/preferences/deduplication/scheduling/notification/adoption and owner-host acceptance are not completed by this manual feature.
