# Development setup

Use Docker/Compose, Python 3.12, uv 0.13.4 and Node 22. The platform is development/test only. Keep separate databases, projects, credentials and ports for unrelated environments.

Review `.env.example` and `infra/core/compose.yml`. `bash scripts/first-run.sh` creates a private local `.env`, generates distinct database/runtime secrets when needed, starts the development stack and exports only its public development CA. It does not import that CA into host trust. Review each host/trust action separately. Do not expose the service outside the reviewed loopback setup.

See [HTTPS](docs/LOCAL_HTTPS.md) and [identity/provisioning](docs/IDENTITY.md). Use hidden credential prompts, a migration account for trusted administration and the restricted `butler_runtime` account for the API. Never commit `.env`, private keys or runtime records. [Development commands](docs/DEVELOPMENT.md) and [test gates](docs/TESTING.md) describe synthetic verification.

Normal updates use explicit reviewed migrations and role setup; backup first. Do not deploy this snapshot into an existing installation just because the source is public. API/database scope IDs are generalized. Use a fresh project and database; existing private installations require a separate reviewed conversion. Role setup refuses databases missing generic scopes before changing any role. No automatic data conversion or owner-host acceptance is provided. Production remains separately gated.

AI/speech installers are optional, disabled development helpers. No model is installed as a publication side effect. Preserve non-commercial restrictions for any CC BY-NC speech model and review other model licenses separately.

Online migrations also reject an existing scope table without the generic namespace before executing migration DDL. This is a refusal, not a conversion tool. Review any offline SQL manually; publishing code does not authorize changes to an existing installation.
