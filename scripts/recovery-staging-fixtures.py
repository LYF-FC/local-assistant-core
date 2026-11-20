"""Spec 075 CI-only custom-dump restoration into never-activated scratch DBs.

Called by the existing disposable restore drill. No production restore command is
provided. All fixtures, keys and PostgreSQL targets below are synthetic and fresh.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "tests"))

from app.config import settings
from app.recovery_set.verify import verifier_chain
from app.recovery_staging import StagingExpectations, stage_synthetic_dump
from app.recovery_staging_binding import inspect_restored_binding
from recovery_set_support import make_key, make_set, private_dir, run_generate


def main():
    container = os.environ.get("BUTLER_CI_POSTGRES_CONTAINER", "")
    if (
        settings.env != "test"
        or settings.postgres_db != "butler_test"
        or os.environ.get("BUTLER_RUN_DB_TESTS") != "1"
        or not container
        or settings.postgres_host != "127.0.0.1"
    ):
        raise ValueError("Explicit disposable synthetic PostgreSQL container required")
    inspected = json.loads(
        subprocess.check_output(
            ["docker", "inspect", "--format", "{{json .}}", container],
            text=True,
            timeout=30,
        )
    )
    ports = inspected["NetworkSettings"]["Ports"].get("5432/tcp") or []
    if (
        inspected["Config"]["Image"] != "postgres:17"
        or "POSTGRES_DB=butler_test" not in inspected["Config"]["Env"]
        or not any(int(port["HostPort"]) == settings.postgres_port for port in ports)
    ):
        raise ValueError("Disposable PostgreSQL 17 fixture container/endpoint required")
    prefix = ["docker", "exec", "-i", container]
    databases = []

    def tool(*arguments, data=None, check=True):
        return subprocess.run(
            [*prefix, *arguments],
            input=data,
            capture_output=True,
            check=check,
            timeout=30,
        )

    def database():
        name = "butler_test_staging_" + uuid4().hex
        tool("createdb", "-U", "postgres", name)
        databases.append(name)
        return name

    def binding(name, staged):
        engine = create_engine(make_url(settings.database_url).set(database=name))
        try:
            with engine.connect() as connection:
                report = inspect_restored_binding(
                    connection,
                    installation_id=staged.installation_id,
                    schema_head=staged.schema_head,
                )
                assert report.quarantined and not report.restore_eligible
                return report
        finally:
            engine.dispose()

    try:
        source = database()
        installation = "11111111-1111-4111-8111-111111111111"
        head = verifier_chain()[-1]
        fixture_sql = (
            "CREATE TABLE installation_config (id integer, installation_id uuid);"
            f"INSERT INTO installation_config VALUES (1, '{installation}');"
            "CREATE TABLE alembic_version (version_num text);"
            f"INSERT INTO alembic_version VALUES ('{head}');"
            "CREATE TABLE recovery_staging_sentinel (value text);"
            "INSERT INTO recovery_staging_sentinel VALUES ('synthetic-staged-bytes');"
        )
        tool(
            "psql",
            "-U",
            "postgres",
            "-d",
            source,
            "-v",
            "ON_ERROR_STOP=1",
            data=fixture_sql.encode(),
        )
        dump = tool("pg_dump", "-U", "postgres", "-Fc", source).stdout
        with TemporaryDirectory(prefix="butler-synthetic-staging-") as temporary:
            root = Path(temporary).resolve()

            def stage(
                name, content, declared_installation=installation, declared_head=head
            ):
                folder = private_dir(root / name)
                synthetic = make_set(folder / "source", archive=False, dump=content)
                key = make_key(folder / "key", installation_id=declared_installation)
                manifest = private_dir(folder / "out") / "manifest.json"
                generated, status = run_generate(
                    synthetic, key, manifest, head=declared_head
                )
                assert status == 0, generated
                expectations = StagingExpectations(
                    installation_id=declared_installation,
                    schema_head=declared_head,
                    key_path=key.path,
                    key_fingerprint=key.fingerprint(),
                    expected_manifest_hash=generated["manifest_hash"],
                )
                staged = stage_synthetic_dump(
                    synthetic.set_dir,
                    manifest,
                    private_dir(folder / "scratch"),
                    expectations,
                )
                return staged, synthetic

            def restore(staged, target, *, check=True):
                consumed = staged.consume(
                    lambda data: tool(
                        "pg_restore",
                        "-U",
                        "postgres",
                        "--exit-on-error",
                        "-d",
                        target,
                        data=data,
                        check=check,
                    )
                )
                assert consumed.quarantined and not consumed.restore_eligible
                return consumed.consumer_result

            staged, synthetic = stage("matching", dump)
            # The source ceases to contain a pg_dump after staging. Restoration
            # consumes the returned immutable bytes, never reopens this pathname.
            (synthetic.set_dir / "database.dump").write_bytes(b"changed-after-staging")
            restored = database()
            assert restore(staged, restored).returncode == 0
            assert binding(restored, staged).binding_valid
            engine = create_engine(
                make_url(settings.database_url).set(database=restored)
            )
            try:
                with engine.connect() as connection:
                    assert connection.scalar(
                        text("SELECT value FROM recovery_staging_sentinel")
                    ) == ("synthetic-staged-bytes")
            finally:
                engine.dispose()

            wrong, _ = stage(
                "wrong-binding", dump, "22222222-2222-4222-8222-222222222222"
            )
            wrong_target = database()
            assert restore(wrong, wrong_target).returncode == 0
            report = binding(wrong_target, wrong)
            assert not report.binding_valid
            assert report.reasons == ("restored_installation_mismatch",)

            wrong_head, _ = stage(
                "wrong-head", dump, declared_head=verifier_chain()[-2]
            )
            wrong_head_target = database()
            assert restore(wrong_head, wrong_head_target).returncode == 0
            report = binding(wrong_head_target, wrong_head)
            assert not report.binding_valid
            assert report.reasons == ("restored_schema_head_mismatch",)

            invalid, _ = stage("invalid-dump-format", b"synthetic-not-a-postgres-dump")
            failed_target = database()
            failure = restore(invalid, failed_target, check=False)
            assert failure.returncode != 0
            report = binding(failed_target, invalid)
            assert not report.binding_valid and report.reasons == (
                "binding_metadata_missing",
            )
        print(
            "Spec 075 synthetic staging: exact staged custom dump restored after source mutation; "
            "restored identity/schema mismatches and invalid dump rejected; all targets quarantined, "
            "no activation or forgetting reconciliation claimed"
        )
    finally:
        cleanup_failed = False
        for name in reversed(databases):
            try:
                cleanup_failed |= (
                    tool("dropdb", "-U", "postgres", name, check=False).returncode != 0
                )
            except subprocess.TimeoutExpired:
                cleanup_failed = True
        if cleanup_failed and sys.exc_info()[0] is None:
            raise RuntimeError("Disposable staging database cleanup failed")


if __name__ == "__main__":
    main()
