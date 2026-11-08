# Spec 006 — local HTTPS and browser identity

Status: development/test implementation contract. Production deployment and real family/work records remain gated.

## Outcomes

A synthetic operator opens the loopback HTTPS dashboard, signs in, sees only their current identity/scopes, reloads safely and signs out. Real TLS and trusted-proxy handling replace the prior HTTP-only host gap. No model, domain action or external account is enabled.

## Requirements

- H01: Caddy serves https://localhost:8443 with a local CA; host publication stays loopback. HTTP remains only for probes/disabled sign-in and cannot authenticate even with forged forwarding headers.
- H02: API trusts forwarding only from a fixed Caddy address on a dedicated internal app subnet. Caddy overwrites forwarded scheme/source and removes Forwarded; API has no published port. Test direct untrusted forwarded headers and edge HTTP spoofing.
- H03: exact HTTPS scheme, configured Host/Origin, secure __Host cookie, HttpOnly/SameSite Strict and CSRF enforcement remain mandatory. No wildcard proxy trust or TLS verification bypass in acceptance tests.
- H04: browser session bootstrap is an authenticated, exact-Origin JSON POST that rotates the hashed CSRF secret and audits atomically; it permits safe reload without localStorage/sessionStorage or readable session cookies. Absolute expiry is unchanged. Old CSRF fails after rotation; tabs can refresh explicitly.
- H05: UI uses same-origin credentials/no-store, clears password after submission, keeps CSRF only in memory, validates response contracts, renders errors without upstream private details and never exposes unfinished domain actions. HTTP shows no usable login form.
- H06: automated browser acceptance uses a real TLS edge, synthetic fixtures, trusted local CA and certificate verification enabled. Cover sign-in/out, cookie flags, reload/bootstrap, revocation/scopes, no browser token persistence and denial paths.
- H07: source/unit, PostgreSQL, browser/container and recovery CI pass on the same candidate. Actual M2 browser/CA acceptance remains an owner-run gate; CI is not evidence of host installation.

## Data and boundaries

No schema migration or new permission grant. Existing local credentials/sessions/audit are authoritative. Bootstrap replaces one CSRF digest, touches idle time and emits minimal audit in one transaction. Public probes and UI assets remain metadata only. CA private keys remain in private Caddy volume, never exported or committed; only its public root is copied for deliberate development trust. Browser tests retain no reusable auth storage or traces. New npm dev-only Playwright dependency is locked.
