# Local identity — development/test increment

Status: development/test API and trusted local administration are merged; HTTPS browser identity is delivered through #27 and used by Memory/Discovery #28–30. Production startup remains blocked. No real accounts or family data are installed by the repository; unimplemented domain/speech routes stay closed.

## Architecture

See ADR 0001. Use Argon2id password hashes and random opaque sessions. Only SHA-256 session/CSRF digests are stored; a successful login returns a secure HttpOnly SameSite=Strict __Host cookie and a CSRF token to the same-origin caller. Sessions expire after 8 hours absolute or 30 minutes idle and can be revoked in the database. A new login rotates a supplied previous session. User disablement, password replacement and scope changes take effect without model/server restart. technical_admin grants no automatic access to family-private scopes.

## API

- POST /api/v1/auth/login: JSON slug/password, exact configured Origin, HTTPS. Returns user_id and csrf_token; sets __Host-butler_session only after transaction commit.
- GET /api/v1/auth/me: HTTPS plus valid cookie; returns current identity and current scope keys.
- GET /api/v1/auth/scopes/{scope}: HTTPS plus valid cookie; returns allowed=true only for an assigned canonical scope. Unknown/unassigned scope returns generic 403. This exposes capability metadata, not domain records.
- POST /api/v1/auth/logout: HTTPS, exact Origin, valid cookie and X-CSRF-Token from login; revokes the session and clears cookie.

Missing/invalid/revoked identity: generic 401. TLS requirement: 400. Origin/CSRF/scope denial: generic 403. Attempt budget: 429 with Retry-After. DB/audit/commit failure: sanitized 503. Invalid request bodies do not echo input secrets. No permissive CORS, public enrollment, password recovery or permission-administration API.

The HTTP shell cannot sign in; spec 006 adds loopback HTTPS sign-in/current-access UI. TLS must be observed by ASGI; do not trust arbitrary X-Forwarded-Proto headers or enable proxy trust globally. Production host/TLS/proxy/UI integration is a later reviewed task. BUTLER_AUTH_ORIGIN defaults to https://localhost:8443 and must be an exact HTTPS origin without a path. Secure cookies are never disabled for convenience. The client must retain the login CSRF token in memory for sign-out; the merged browser UI resumes sessions through the audited JSON bootstrap below.

## Trusted local administration

Run only from an authorized local host terminal, with explicit environment matching BUTLER_ENV and the intended database. Passwords are entered interactively using getpass, never as command arguments or environment variables. Apply migrations first. Example synthetic development account:

```sh
docker compose --env-file .env -f infra/core/compose.yml run --rm migrate python -m app.manage --environment development create-user --slug synthetic-user --display-name 'Synthetic user' --scope household_shared
```

Run this from the trusted host against its development stack, with Compose’s interactive terminal enabled. It uses the privileged migration container’s private DB connection; do not publish PostgreSQL to provision users. A standalone `uv run python -m app.manage` is suitable only for an explicitly configured isolated test/development database.

Other actions: set-password, disable-user, enable-user, grant-scope and revoke-scope; each requires --slug, and scope changes require exactly one --scope. None is exposed as a web API. Administration records the trusted-host-operator identity and target/changes without secret values. No actual user/account commands are run by CI or setup automatically.

## Audit and attempt controls

Identity reads/denials, session changes and administration are minimally audited. Session mutations and their audit entries share one transaction. The merged audit/approval increment adds DB guards and a restricted API role; see docs/APPROVALS.md. Production archival/host/retention assurance remains open.

Budgets persist across process restarts: 30 attempts per observed source and 5 per account per 15-minute fixed window, consumed atomically before verification. Forwarded IP headers cannot select a different source. Password verification concurrency is bounded per process. Proxy-aware source policy, broader abuse controls, retention/cleanup and production resource tuning remain future gates.

## Reload bootstrap

POST /api/v1/auth/session accepts an empty JSON object only with exact HTTPS Host/Origin and valid session cookie. It atomically rotates CSRF, touches idle time and audits before returning current identity/scopes plus csrf_token. It does not renew absolute expiry. This endpoint intentionally uses Origin+JSON for bootstrap, since the old token was in page memory; future unsafe operations still require CSRF. Old-tab tokens fail after rotation; refresh session before retrying logout. See LOCAL_HTTPS.md.
