# Manual Discovery feedback — development/test

Spec 009 is the first manual slice of draft 004. Merged #30 adds the private proposal review view on top of the memory API/UI; main 75b0141 has green CI. No model, collector, feed, external request, schedule, installation or experiment is activated.

## Human workflow

1. Sign in over the existing local HTTPS edge and choose Discovery. Assigned member_a_private/member_b_private scopes are available; shared/finance/technical/work scopes are excluded from this pilot. Another user with the same private grant cannot see the owner's proposal.
2. Add a title, stable topic slug, summary and a manually reported source title/HTTPS URL/date. The UI captures one source; the API permits up to five. Optional benefit, privacy, maturity/license, hardware/cost, alternatives/dependencies and experiment text remain explicitly unknown/unproposed if blank. The date is a reported observation, not source verification. URLs/content stay inert text and are never fetched/opened/executed.
3. Save interest: very interested/investigate further (100), later (10), unanswered (0), already covered (-10), not relevant (-20). Order is priority descending then UUID ascending. Dismissed entries are hidden unless included. Feedback is per owner and proposal only; it does not infer another topic/person's preference or authorize files, installation, experiments, jobs or deployment.
4. Correct or clear feedback. Each successful write creates a memory revision. Clear removes the current choice/note but retains prior history. Stale revision 409 keeps the unsaved draft and disables save until explicit discard/reload. Ordinary validation/server errors keep drafts. Changing feedback restarts pagination. Live cursor pages are bounded at 25 (API maximum 50), not a stable snapshot across concurrent changes.
5. Switch to Memory for full structured provenance, owner history, metadata correction, current-page JSON export or confirmed forgetting. One record ID and one revision history serve both interfaces. Forgetting scrubs live content/all saved revisions, not old backups or downloaded exports. Switching views unmounts the old panel, clears its data and aborts requests; returning refetches current records. Unsaved drafts are discarded when switching tabs.

## Storage and trust

A strict versioned `discovery_proposal` envelope lives in existing owner-private `MemoryRecord(kind=experience)` content. It contains proposal fields and optional feedback with a server-recorded timestamp. Audit remains content-free; existing guarded memory snapshots, row locking, runtime role and transactional commit apply. No migration/new runtime grant/dependency is required. The namespace/version is a typed format, not a substitute for owner/current-scope checks. Generic memory writes that produce invalid/expired/forgotten envelopes are rejected by Discovery and cannot acquire ranking/action authority. An invalid candidate blocks its bounded result page with a sanitized validation error; inspect/correct/forget through Memory. Valid unrelated memory is not listed as Discovery.

All requests retain exact HTTPS Host/Origin, session, CSRF, no-store, redirect rejection and cancellation. Sign-out/session refresh unmounts the workspace. Access denial clears payload and aborts earlier requests; post-await guards prevent stale responses repopulating another session. No local/session browser storage, payload URLs, HTML rendering, approval or job creation. Simple URL validation is an inert-reference input check, not a future collector's SSRF/egress protection; collectors remain absent.

## API

- `POST /api/v1/discovery`: title, private scope, topic, summary, 1–5 evidence objects (title/url/aware observed_at) and optional assessments/experiment. Unknown fields/feedback injection are rejected.
- `GET /api/v1/discovery`: bounded priority pages; `include_dismissed`, `limit`, and a paired `after` UUID + `after_priority` from `next_cursor`. Current per-proposal scores are explained, not AI confidence.
- `GET /api/v1/discovery/{id}`: current authorized valid proposal.
- `PUT /api/v1/discovery/{id}/feedback`: expected_revision, choice (very_interested/later/covered/not_relevant/null), note (at most 500 chars). Null choice + empty note clears current feedback. The returned memory ID/revision works with existing history/export/forget routes.

Existing memory exports contain the envelope and are private. No automatic real preference is populated from source code. The already-documented photo-classification research priority remains product scope; no photos are accessed or scanned.

## Verification and limits

Synthetic tests cover explicit feedback/clear/history, ordering/cursors/dismissals, private ownership/revocation, CSRF/origin, unknown/oversized/date/reference input, malformed generic envelopes, forgetting and atomic rollback. PostgreSQL adds restricted-role JSON ordering/forgetting and a distinct-session feedback race. Chromium/TLS adds manual creation, safe untrusted text, feedback/dismissal/clear, conflict draft preservation, Memory forgetting and delayed-list sign-out. Hosted exact-commit results/convergence live in the PR. Synthetic editor/desktop/mobile screenshots may be retained for one day; no credentials, traces, auth storage or real records are captured.

Actual M2/Safari/iPhone and production recovery/retention acceptance remain separate. Full Discovery source collectors, provenance verification/deduplication, topic-wide preferences/suppression, source staleness/outage monitoring, budgets/digests and measured adoption remain open in draft 004. Work isolation and finance research are separate future contracts.


## Simpler capture and later enrichment — merged prior implementation review/spec 044

Spec 044 adds an explicit evidence-free idea stage and later expected-revision detail editing. Existing v1 proposals remain valid; new v2 idea/proposal stages distinguish missing evidence from manually reported sources. Feedback, owner/scope, history, export and forgetting stay authoritative; no collector/source verification/action permission is introduced. Optional assessments move behind disclosure. See [capture guide](SIMPLER_CAPTURE.md).


## Discovery review inbox and selected digest — spec 045 candidate

The broader spec 045 candidate adds private server-side literal search/topic/stage/interest facets, current-page selection and a short-lived exact reviewed cited digest. Existing feedback/ranking/staged idea/enrichment semantics remain, including interest-only authority and manual sources. No generalized preferences, collector, notification, deduplication or adoption flow is completed. See [review inbox guide](DISCOVERY_REVIEW_INBOX.md).
