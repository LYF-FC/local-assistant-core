# Verification

Run `make check`: locked dependency sync, backend Ruff/format/unit tests, frontend client tests/build, repository invariants and CI scope/gate contracts. The fixture target must be development/test; production/staging startup is refused.

For actual PostgreSQL evidence, explicitly opt in with `BUTLER_RUN_DB_TESTS=1`, `BUTLER_ENV=test` and a disposable `BUTLER_POSTGRES_DB` beginning with `butler_test`. Use the intended local PostgreSQL host/port and synthetic credentials, then run `uv run --locked pytest -m integration --allow-hosts=127.0.0.1 --durations=30` from backend. Do not weaken socket/target guards or reuse an owner database. Explicit migration round trips and runtime-role/idempotence tests remain included.

`scripts/test-db-restore.sh` requires the exact disposable `butler_test` database and an unambiguous `BUTLER_CI_POSTGRES_CONTAINER`; it exercises actual dump/isolated restore, original/history/tombstone preservation, session/access quarantine and existing recovery procedures. It is destructive test infrastructure.

`scripts/test-containers.sh` validates fresh synthetic non-root containers, HTTPS/Origin/proxy boundaries, general browser scenarios and an independent optional Work phase plus recovery drills. `test-ci-browser.sh` imports a synthetic public CA only in a disposable Linux runner. It must never modify an owner trust store or bypass certificate validation. No private records or real services are needed.

The new public repository must obtain its own exact-head selected/full CI evidence. Prior private runs and local verification do not become new hosted passes.
