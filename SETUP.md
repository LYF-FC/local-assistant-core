# Development setup

Use Docker/Compose, Python 3.12, uv 0.13.4 and Node 22. The platform is development/test only. Keep separate databases, projects, credentials and ports for unrelated environments.

Review `.env.example` and `infra/core/compose.yml`. `bash scripts/first-run.sh` creates a private local `.env`, generates distinct database/runtime secrets when needed, starts the development stack and exports only its public development CA. It does not import that CA into host trust. Review each host/trust action separately. Do not expose the service outside the reviewed loopback setup.

See [HTTPS](docs/LOCAL_HTTPS.md) and [identity/provisioning](docs/IDENTITY.md). Use hidden credential prompts, a migration account for trusted administration and the restricted `butler_runtime` account for the API. Never commit `.env`, private keys or runtime records. [Development commands](docs/DEVELOPMENT.md) and [test gates](docs/TESTING.md) describe synthetic verification.

**Database account convention:** Compose defaults to `butler` for migrations/privileged setup; API and DB-backed workers use `butler_runtime`. The separate disposable PostgreSQL integration/restore job uses `postgres`. Container fixtures must verify actual required ownership rather than hard-code `postgres`. Read the [fixture role matrix and preflight](docs/TESTING.md#database-users-container-tests-and-postgresql-tests-differ) before adding or running synthetic fixtures.

Normal updates use explicit reviewed migrations and role setup; backup first. Do not deploy this snapshot into an existing installation just because the source is public. API/database scope IDs are generalized. Use a fresh project and database; existing private installations require a separate reviewed conversion. Role setup refuses databases missing generic scopes before changing any role. No automatic data conversion or owner-host acceptance is provided. Production remains separately gated.

AI/speech installers are optional, disabled development helpers. No model is installed as a publication side effect. Preserve non-commercial restrictions for any CC BY-NC speech model and review other model licenses separately.

Online migrations also reject an existing scope table without the generic namespace before executing migration DDL. This is a refusal, not a conversion tool. Review any offline SQL manually; publishing code does not authorize changes to an existing installation.

The [optional original archive](docs/DOCUMENT_ARCHIVE.md) uses an explicitly selected development overlay and an empty private volume initialized once. Base setup stays disabled. Provision only a new isolated synthetic stack; do not attach an existing private NAS/share or deployment. PostgreSQL originals remain authoritative and parser/production gates stay closed.

The [optional PDF worker](docs/PDF_INGESTION.md) adds `infra/core/pdf-ingestion.override.yml` to a fresh isolated synthetic stack. It requires Linux seccomp, a shared private Unix-socket volume and UID 10001. No host networking, database credentials or original-file mount is granted to the worker. Without the overlay, PDF originals can be retained but extraction reports unavailable.

## Explicit bounded OCR — spec 052

No extra host dependency, network, credentials or automatic OCR is enabled. The optional PDF-worker overlay includes packaged Tesseract English/French/Spanish data; use **Run OCR (up to 2 pages)** only in the new isolated synthetic stack. Base/unconfigured extraction remains unavailable. Existing private deployments stay untouched. See [OCR setup and limits](docs/PDF_OCR.md).

## Planned reusable onboarding

The [INSTALL-01–12 scope](docs/CONFIGURABLE_INSTALLATIONS.md) adds future household-specific setup, private configuration, protected credential provisioning and optional feature/dependency controls. Each household needs supported hardware and independent storage/backups. Future templates create fresh identities and contain no reusable credentials or personal records. Current first-run helpers and fixed synthetic/example scopes are development tools, not the completed onboarding system. Do not use this requirement as authority to convert an existing database or configure a real service.

## Planned model evaluation

[Task-model and dense/MoE research](docs/LLM_RESEARCH.md) adds no installation dependency or default model. Verify hardware/runtime/license fit and approve bounded synthetic experiments before obtaining weights or enabling inference. Task-specific selection, if justified, will use versioned private configuration and feature controls; missing local models never imply cloud fallback. Existing setup and private-deployment protections remain unchanged.

## Scoped source answers — spec 053

Base document answers use source-only mode and never contact a model. The explicitly selected `answers-synthetic.override.yml` is only a disposable test fixture: fixed synthetic model, local loopback service, no weights or host runtime. No real model is selected/downloaded/activated by this batch. Future authorized activation requires an explicit local model tag/manifest digest, approved local endpoint and separately verified runtime/license/quality/resource/privacy gates. See [configuration](docs/DOCUMENT_ANSWERS.md).

## Calendar and briefing — spec 054

Use Calendar and briefing with synthetic normalized JSON as described in [calendar guide](docs/CALENDARS.md). Existing migrations/role setup include 0026; no calendar credential, provider endpoint, parser dependency, background poller or model is configured. Do not supply real accounts/data or alter an existing installation from this development batch.

## Recurring routines — spec 055

Existing migration/runtime-role setup now includes 0027 and the optional `routines` profile. The development UI previews finite plans and requires explicit future-task/private-reminder authorization; saving never starts a service. No credentials, provider or real deployment configuration is added. Review [routine guide](docs/RECURRING_ROUTINES.md) before any separately authorized update/activation; do not alter a private installation from this development batch.

## Invoice field review — spec 056

Existing migration/runtime-role setup now includes `0028_invoice_review`. No package, model, credentials, service or provider configuration is added. Use synthetic reviewed documents through document-detail invoice review. Follow the [fixture-owner matrix](docs/TESTING.md): Compose owner `butler`, isolated native integration/restore owner `postgres`, API/workers `butler_runtime`. Private installation adoption remains separately authorized. See [guide](docs/INVOICE_REVIEW.md).

## Reviewed invoice filing plans — spec 057

No migration beyond 0028, new dependency, configured root, provider, secret or worker is introduced. Use synthetic reviewed invoices and logical destinations through document detail. Approval never authorizes a filesystem root or future execution. Keep the fixture-owner matrix and private deployment protections unchanged. [Workflow](docs/INVOICE_FILING_PLANS.md).

## Offline email intake — spec 058

Existing migration/runtime-role setup now includes 0029. No package, mailbox account, secret, provider endpoint, background poller, model or filing root is added. Use synthetic `.eml` files through Documents; the constrained MIME format is explicit in the [intake guide](docs/OFFLINE_EMAIL_INTAKE.md). Preserve the fixture-owner matrix: default Compose owner `butler`, native PG/restore owner `postgres`, application/worker `butler_runtime`. Private installation/adoption remains separately authorized.
