# Context

Local Assistant Core is the primary generic software development repository for a local-first household/professional assistant. No tenant profile is embedded. Structured records own operational truth; replaceable models interpret or propose within current application permissions. Deterministic reminders, jobs, backups and failure state must work without inference.

The retained product scope includes an everyday MVP and later household, care, connected-life, education/NOMAD, professional, creative, financial and governed platform capabilities. The [scope](docs/SCOPE.md), [complete register](docs/FEATURE_REGISTER.md) and [MVP contract](docs/MVP_ACCEPTANCE.md) preserve that breadth; the [roadmap](ROADMAP.md) orders dependencies without reducing scope.

[Baseline verification](docs/VALIDATION.md) demonstrates synthetic engineering, while [readiness](docs/V0_1_READINESS.md) records remaining operational gates. All current development uses synthetic data. Existing private repositories/deployments stay unchanged; tested upstream releases may be adopted only through separately reviewed private conversion/backup/rehearsal/rollback. No real integration, production activation, private-data migration or outbound AI is authorized by this planning work.

See [architecture](ARCHITECTURE.md), [decisions](DECISIONS.md), [operations](OPERATIONS.md), [setup](SETUP.md) and [publication boundary](PUBLICATION.md).

Specs 050/051/052 merged through [PR #2](https://github.com/LYF-FC/local-assistant-core/pull/2), [PR #3](https://github.com/LYF-FC/local-assistant-core/pull/3) and [PR #4](https://github.com/LYF-FC/local-assistant-core/pull/4). PR #4 main `232dbc693a3f9aafcc477f638b99508ef560e8e4` passed all six jobs in run 42521890786. Merged [PR #7](https://github.com/LYF-FC/local-assistant-core/pull/7) delivers [spec 053](docs/DOCUMENT_ANSWERS.md); main `6d11ba8dee0bbbea04c6d435effddc9ce06f4acf` passed all six jobs in run 42529896072. It adds scoped source-backed questions, exact quotation answers and a default-disabled local selector. Real-model activation/quality, free-form conversation, structured invoice fields, live adapters and operational acceptance remain open.

## Configurable installations — scope extension

The shared core is intended for independent households, each owning its configuration, credentials, records, hardware and backups. INSTALL-01–12 define secure onboarding, configurable household identities, optional feature lifecycle and versioned adoption. See [contract](docs/CONFIGURABLE_INSTALLATIONS.md). These are approved requirements, not delivered capabilities; the existing private installation stays unchanged.

## Model research scope

RND-04/05 investigate task-specific local models and dense-versus-MoE trade-offs against measured single-model baselines. Different conversation/coding/document tasks can be evaluated independently; selection preserves current permissions and local-first isolation. See [contract](docs/LLM_RESEARCH.md). Research is approved; no runtime model or routing feature is delivered.

Merged [PR #8](https://github.com/LYF-FC/local-assistant-core/pull/8) delivers spec 054: [bounded calendar snapshots and daily briefing](docs/CALENDARS.md) using synthetic complete windows, explicit recurrence identity, timezone/coverage/conflict reconciliation and current task/memory references. Live calendar, full dashboard/needs briefing and installation configuration remain open.

Spec 055 develops [finite recurring routines](docs/RECURRING_ROUTINES.md), atomic task/private-reminder generation and current completion/lifecycle history. External notification, calendar coupling, full recurrence and operational/installation acceptance remain open.

PR #8 main `0324d0002e970fb097df509a0377fe53c3ffeae8` passed all six jobs in run 42593958307. This is engineering evidence, not provider/host/MVP acceptance.
