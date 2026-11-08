"""Shared disposable PostgreSQL workspace/login fixture; never used by application code."""

from contextlib import contextmanager
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models import WorkWorkspace
from app.work_manage import administer
from app.work_storage import provision

PASSWORD = "synthetic-storage-harness-only-0123456789"


def connect(user=None, password=None):
    return psycopg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
        user=user or settings.postgres_user,
        password=password or settings.postgres_password.get_secret_value(),
        connect_timeout=5,
    )


@pytest.fixture
def storage_case(postgres_engine, runtime_engine):
    assert settings.env == "test" and settings.postgres_db.startswith("butler_test")
    maker = sessionmaker(bind=postgres_engine)
    cases = {}
    for letter in ("a", "b"):
        slug = "synthetic-" + uuid4().hex
        login = "butler_test_storage_" + uuid4().hex
        with maker.begin() as db:
            administer(db, "create-workspace", slug)
            workspace = db.query(WorkWorkspace).filter_by(slug=slug).one()
            workspace_id = workspace.id
        with connect() as db:
            role = provision(db, slug)
            db.execute(
                sql.SQL(
                    "CREATE ROLE {} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}"
                ).format(sql.Identifier(login), sql.Literal(PASSWORD))
            )
            # Test-only login can assume just this one storage role. It is never deployed.
            db.execute(
                sql.SQL("GRANT {} TO {} WITH INHERIT FALSE, SET TRUE").format(
                    sql.Identifier(role), sql.Identifier(login)
                )
            )
        cases[letter] = {"workspace": workspace_id, "slug": slug, "role": role, "login": login}

    @contextmanager
    def session(letter="a"):
        case = cases[letter]
        with connect(case["login"], PASSWORD) as db:
            db.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(case["role"])))
            yield db

    cases["session"], cases["maker"] = session, maker
    try:
        yield cases
    finally:
        # Only random roles created by this fixture in the opted-in disposable database.
        with connect() as db:
            for letter in ("a", "b"):
                case = cases[letter]
                db.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(case["login"])))
                db.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(case["role"])))
                db.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(case["role"])))


def insert(case, letter="a", identifier=None, marker="synthetic:marker"):
    identifier = identifier or uuid4()
    with case["session"](letter) as db:
        db.execute(
            "INSERT INTO work.validation_records (workspace_id,id,marker) VALUES (%s,%s,%s)",
            (case[letter]["workspace"], identifier, marker),
        )
    return identifier
