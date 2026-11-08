# Context

Local Assistant Core is the primary generic software development repository for a local-first household/professional assistant. No tenant profile is embedded. Structured records own operational truth; replaceable models interpret or propose within current application permissions. Deterministic reminders, jobs, backups and failure state must work without inference.

The retained product scope includes an everyday MVP and later household, care, connected-life, education/NOMAD, professional, creative, financial and governed platform capabilities. The [scope](docs/SCOPE.md), [complete register](docs/FEATURE_REGISTER.md) and [MVP contract](docs/MVP_ACCEPTANCE.md) preserve that breadth; the [roadmap](ROADMAP.md) orders dependencies without reducing scope.

[Baseline verification](docs/VALIDATION.md) demonstrates synthetic engineering, while [readiness](docs/V0_1_READINESS.md) records remaining operational gates. All current development uses synthetic data. Existing private repositories/deployments stay unchanged; tested upstream releases may be adopted only through separately reviewed private conversion/backup/rehearsal/rollback. No real integration, production activation, private-data migration or outbound AI is authorized by this planning work.

See [architecture](ARCHITECTURE.md), [decisions](DECISIONS.md), [operations](OPERATIONS.md), [setup](SETUP.md) and [publication boundary](PUBLICATION.md).

Spec 050 local original archive merged in [PR #2](https://github.com/LYF-FC/local-assistant-core/pull/2) at `8c6794b31ce2f0458beb1ffe26cdb0ca81ea113a`; its main CI passed all six jobs. Current branch [spec 051](docs/PDF_INGESTION.md) extends that lifecycle with isolated bounded PDF text extraction. OCR, live adapters and operational acceptance remain open.

## Configurable installations — scope extension

The shared core is intended for independent households, each owning its configuration, credentials, records, hardware and backups. INSTALL-01–12 define secure onboarding, configurable household identities, optional feature lifecycle and versioned adoption. See [contract](docs/CONFIGURABLE_INSTALLATIONS.md). These are approved requirements, not delivered capabilities; the existing private installation stays unchanged.

## Model research scope

RND-04/05 investigate task-specific local models and dense-versus-MoE trade-offs against measured single-model baselines. Different conversation/coding/document tasks can be evaluated independently; selection preserves current permissions and local-first isolation. See [contract](docs/LLM_RESEARCH.md). Research is approved; no runtime model or routing feature is delivered.
