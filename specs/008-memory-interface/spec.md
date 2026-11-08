# Spec 008 — inspectable memory interface

Status: development/test increment based on merged HTTPS and scoped-memory API. No inference, import, model/provider, work scope or production deployment.

U01: authenticated HTTPS users can page/filter current memory, inspect sources/assessment/expiry, create explicit text entries and view owner history. Scope choices come from assigned family/business scopes; technical_admin/work scopes are unavailable.
U02: only owners see edit/history/forget controls; server remains authoritative. Corrections send the displayed expected revision and full mutable data, preserving structured content from other features instead of flattening it.
U03: expired entries require explicit owner inspection; forgotten entries show minimal tombstones only. Historical content is read-only and never presented as current context.
U04: forgetting requires a clear confirmation describing live revisions and old backup/export limits. Success clears list/detail/editor/history caches; denial or conflict must never imply the operation completed.
U05: bounded JSON download exports the current page/filter only, validates its response and uses a fixed safe filename. No claim of full/snapshot export.
U06: requests use same-origin cookies, no-store, redirect rejection and CSRF for writes; content is plain text, never executable/link-fetched HTML. No memory/token persistence in browser storage or URLs.
U07: session change/refresh/sign-out unmounts and aborts memory requests; late responses and downloads cannot restore old-user content. Access-denied/gone responses clear stale payload; 409 preserves an explicitly unsaved draft without silently retrying a new revision.
U08: accessible labeled forms, busy/error/empty states, modal forget confirmation, bounded pagination and mobile layout. Synthetic client/browser tests cover CRUD/history/export/forget, conflict, private/shared permissions, XSS and sign-out request races.

Backend API/DB policy stays spec 007; add no new scope or permission grant. Actual M2/Safari/iPhone/production acceptance remains separate from hosted Chromium evidence.

Spec 044 candidate simplifies new-entry forms with a visible editable title excerpt, Tentative default and progressive optional fields, retaining explicit access/type/context expiry and all correction/provenance/structured-content/current-authority boundaries. See ../044-simpler-capture.
