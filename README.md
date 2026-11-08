# Local Assistant Core

Local-first assistant software built with FastAPI, PostgreSQL and React/TypeScript. This is a **development/test source snapshot**, not a supported production release. It ships no personal profile, private records, live credentials, models or external-provider activation.

Implemented engineering includes HTTPS identity/session controls, explicit scoped Memory and Discovery, selected local context, manual tasks/agenda, private in-app reminders, bounded text/Markdown document originals/version history/review/search/citations, and an optional synthetic Work review/recovery pilot. Staging/production API startup remains refused. No public application service is deployed by publishing this source.

## Start here

- [Setup](SETUP.md), [architecture](ARCHITECTURE.md), [security](SECURITY.md).
- [Development](docs/DEVELOPMENT.md), [tests](docs/TESTING.md), [CI](docs/CI_COMPUTE.md).
- [Document library](docs/DOCUMENT_LIBRARY.md), [optional local archive](docs/DOCUMENT_ARCHIVE.md), [tasks](docs/MANUAL_TASKS_AGENDA.md), [reminders](docs/TASK_REMINDERS.md).
- [Full scope](docs/SCOPE.md), [feature register](docs/FEATURE_REGISTER.md), [MVP acceptance](docs/MVP_ACCEPTANCE.md), [roadmap](ROADMAP.md).
- [Planned configurable installations](docs/CONFIGURABLE_INSTALLATIONS.md): onboarding, private configuration and feature controls are scope, not delivered setup.
- [Planned model research](docs/LLM_RESEARCH.md): task-specific local models and dense/MoE evaluation; no model selected.
- [Publication boundary](PUBLICATION.md), [validation state](docs/VALIDATION.md).

Run `make check` using Python 3.12, uv 0.13.4 and Node 22. Dependencies are locked. Real database tests need an explicitly disposable `butler_test` database; container acceptance uses separate synthetic stacks. Never supply real household/employer records or production secrets for tests.

This snapshot intentionally has fresh Git history. Historical private planning, discussions, acceptance records and CI logs are not included. Scope IDs and display labels are generic. This snapshot is for fresh installations; switching an existing private database requires a separate reviewed conversion. No open-source license is added by this preparation; license selection remains a separate owner decision. Existing dependency notices remain intact.

The internal application and environment prefix currently use the generic software name Butler; this repository name does not embed a household identity.
