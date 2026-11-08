# Memory interface — development/test

Spec 008 adds a human-facing Memory section after HTTPS sign-in. The API/UI are merged through #28/#29; main 75b0141 also includes manual Discovery feedback #30. Synthetic browser tests pass. No inference, imported profile, source fetch, work scope or Discovery collector is enabled.

## Using it

- Filter current entries by assigned access and type; page forward/back in bounded groups of 25. Explicit owner-only expired/forgotten filters are available. Empty/loading/error/busy states are visible.
- Add an explicit title, text details, kind, access, source/reference, assessment and optional local-time expiry. Temporary context requires expiry. Scope choices exclude technical administration and unimplemented work scopes. Sources are displayed as text and never fetched.
- Select an entry to inspect current details, assessment, source, revision and expiry. Shared readers have no edit/history/forget buttons; server authorization remains mandatory even if a client is modified.
- Owners can correct title/details/source/assessment/expiry. Access and kind remain immutable. Complex objects created by other features are displayed safely and preserved in full when correcting metadata; feature-specific detail editing remains with that feature.
- View owner history in read-only pages of ten, oldest first. Historical snapshots are not current retrieval context. A stale edit shows an explicit conflict, retains the unsaved draft and requires discard/reload before saving; it never silently changes the expected revision or retries an overwrite.
- Download this page creates a private JSON file containing the current authorized page and filters, at most 25 entries. It is not an all-records or globally consistent archive; use next pages explicitly. Keep exported content outside Git.
- Forget opens a modal describing live current/history scrubbing and the fact that existing exports/older backups can retain copies. Cancel preserves the entry. Confirmed success clears all displayed payload/history/editor state; errors never claim the operation succeeded. Default listing omits the tombstone.

## Session and privacy behavior

Memory and CSRF stay in page memory; there is no localStorage/sessionStorage, URL payload, automatic source-link fetching or HTML insertion. Content is rendered through React text nodes. Sign-out or session refresh unmounts the panel and aborts its requests. Every post-await state change and export side effect checks cancellation. Unauthorized/gone/forbidden or invalid-response paths clear payload caches and abort older requests so a late list cannot resurrect data after denial. Ordinary server/validation failures preserve an unsaved draft; they do not imply a successful write. Session expiry returns to sign-in.

Owner labels/buttons are convenience, not a security boundary. Scope/ownership/version/expiry and audit remain enforced by spec 007 on every server request. Changing filter/paging is disabled while an editor is open to avoid silently discarding a draft. Existing backups, previously downloaded exports and any copies outside live memory are not retroactively erased by the forget button; production deletion/recovery gates remain open.

## Evidence and limits

Client tests cover contract validation, current revision and CSRF, bounded export/history, malformed data, safe errors and no implicit conflict retry. Real Chromium through the trusted local TLS edge covers create/correct/history/download/forget/cancel, owner-expired inspection, structured-content preservation, stale edits, private ownership even with a shared scope grant, shared-reader controls, plain-text XSS handling, sign-out/late-export and denial/late-list races. Browser fixtures are synthetic and guarded to the disposable container database.

Exact-head evidence is maintained in the interface PR. Actual M2/Safari/iPhone and production acceptance remain separate. Follow LOCAL_HTTPS.md and POC_ACCEPTANCE.md for the local CA and host procedure. Manual Discovery proposal/feedback now reuses this memory authority through merged #30; full collectors and topic inference remain future scope.

CI may retain only explicitly captured synthetic Memory/Discovery editor/desktop/mobile screenshots for one day in synthetic-records-ui. No password form, trace, auth storage or real records are included. Screenshots are test artifacts, not host acceptance.


## Simpler capture and later enrichment — merged prior implementation review/spec 044

Spec 044 shortens only the new-entry flow: visible editable first-line title, content/access/type, visible manual/Tentative defaults, progressive provenance and optional expiry. Temporary context expiry remains required on the main form. Existing correction metadata and source-maintained structured content are preserved. The separate Context API remains authoritative for confirmed ordinary candidates; the Memory availability flag is not a dispatch decision. See [capture guide](SIMPLER_CAPTURE.md).
