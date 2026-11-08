# Local HTTPS and browser identity — development/test

Spec 006 adds loopback https://localhost:8443, sign-in/current access, reload bootstrap, refresh and sign-out. Merged evidence is in #27 and subsequent Memory/Discovery PRs #28–30. No production deployment, work data or real external action is unlocked. Actual M2 browser/CA acceptance is still required.

## Trust boundary

Caddy issues a localhost certificate from its private-volume local CA and listens on container port 8443; Compose publishes only 127.0.0.1. HTTP probes remain on 8080, but HTTP shows no credential form and authentication rejects HTTP even with forged headers. Caddy overwrites forwarded scheme/source and removes Forwarded. Uvicorn trusts only Caddy's fixed 172.29.243.2 address on the internal 172.29.243.0/28 app network, outside its dynamic 172.29.243.8/29 allocation range so startup order cannot assign the proxy address to another service. API/PostgreSQL ports are not published. Do not widen that allowlist or use '*'. A VPN/Docker subnet overlap requires a reviewed address change in both Compose and the server command.

The exact BUTLER_AUTH_ORIGIN must match the external HTTPS host/port. Default: https://localhost:8443. If changing BUTLER_HTTPS_PORT, update the Origin too. Do not use a LAN name/IP, change binds or add another proxy as part of this local POC. Production/private-remote access has separate gates.

## M2 setup and CA lifecycle

1. Use the checked/merged HTTPS candidate and existing synthetic development configuration; run scripts/first-run.sh. It starts services, exports only the public root (default ~/Butler/exports/butler-dev-root.crt; spec 010 honors BUTLER_LOCAL_CA_FILE) and verifies TLS with curl --cacert. Use the explicit export-dev-ca.sh destination when selecting a different root path on older commits. No host/browser trust store is changed.
2. Inspect the public root's subject and SHA-256 fingerprint printed by scripts/export-dev-ca.sh. The private CA key stays in the Caddy volume and must never be exported, shared or committed. Do not trust an unrelated downloaded certificate.
3. Deliberately import this public development root into your macOS user Keychain using Keychain Access and authorize trust for this local development CA. This grants that CA certificate-issuing authority in the selected trust domain; keep its private volume protected. Reopen the browser as needed. Other browsers may require their own trust-store procedure.
4. Open https://localhost:8443 without a certificate-warning bypass. Provision only a synthetic account through docs/IDENTITY.md, then sign in, reload, refresh current access and sign out. HTTP must never be used to send credentials.
5. Run scripts/healthcheck.sh. It uses the exported public root, not disabled verification. If trust/export is stale after a disposable stack rebuild, re-export and inspect the new fingerprint before importing it.
6. To retire the POC CA, remove that exact fingerprint's certificate/trust entry from every host/browser store where you imported it, then remove the exported public certificate when no longer needed. Stop containers with compose down; deleting private volumes is a separate destructive reset, not a routine update step.

No model install is needed for identity testing. Standard scripts preserve database/CA volumes on ordinary stop/restart. Do not replace production volumes, keys or trust entries with this development CA.

## Session bootstrap and UI

Session cookie stays __Host-butler_session with Secure, HttpOnly, SameSite=Strict and Path=/. Password clears from the form after submission. CSRF stays in React page memory, never localStorage/sessionStorage or readable cookies. POST /api/v1/auth/session is an authenticated exact-Origin/Host JSON bootstrap: it rotates the stored CSRF digest and audits with state in one transaction; it cannot extend absolute session expiry. Cross-origin callers lack the required Origin and cannot read the response. No CORS allowance or browser identity-header bypass exists.

Reload/Refresh session bootstraps current identity/scopes. Rotation can invalidate another tab's CSRF; refresh that tab before signing out. Failed sign-out keeps a visible error and the session can be refreshed; the UI must not claim revocation when the DB/audit failed. Protected server checks remain authoritative even when an older tab has cached display metadata. Browser endpoints provide no public registration/recovery or user/scope administration.

## Automated acceptance and limits

Unit tests cover bootstrap expiry/CSRF rotation, Host/Origin/authentication and audit rollback. Client tests validate responses and sanitized errors. Container smoke validates the real TLS edge, HTTP edge/direct-network spoof rejection and incorrect-Origin rejection. Playwright Chromium uses a disposable runner NSS trust store with the exported public CA; ignoreHTTPSErrors stays false, with no blanket certificate-error flags. It covers secure cookie flags, reload/sign-out, absent persisted browser tokens, scope revocation and disabled users. CI uses guarded synthetic fixture administration in a disposable butler_test_container database; it has no real accounts or data.

The CI trust helper refuses non-GitHub Linux/test environments and does not change the owner's machine. It removes its imported synthetic CA after the run. No traces, reusable storage state or personal screenshots are retained. Hosted browser acceptance is not proof of M2, Safari, iPhone, LAN/VPN or production readiness.

Reference design: Caddy reverse-proxy/local-PKI documentation, Uvicorn forwarded-allow-ips settings, Playwright browser installation/testing and Chromium Linux NSS documentation. The fixed allowlist and certificate-validating tests are the acceptance authority for this implementation.

Primary design references:

- [Caddy reverse proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy) and [local TLS](https://caddyserver.com/docs/caddyfile/directives/tls).
- [Uvicorn proxy settings](https://uvicorn.dev/settings/).
- [Playwright browser installation](https://playwright.dev/docs/browsers).
- [Chromium Linux NSS trust](https://chromium.googlesource.com/chromium/src.git/+/master/docs/linux/cert_management.md).

Spec 011 CI acceptance also exercises Playwright route.fetch (Node's TLS client, separate from Chromium NSS). The GitHub-Linux/test-only helper verifies an untrusted Node request fails, then supplies the exported synthetic public root via NODE_EXTRA_CA_CERTS to only its health-check/test child processes. NODE_TLS_REJECT_UNAUTHORIZED=0 is rejected; ignoreHTTPSErrors remains false. No owner/system trust store is changed.
