"""Document and document-answer isolation through the restricted PostgreSQL runtime role.

The same behavior as ``test_documents_isolation.py`` runs here. Privileged sessions
(``postgres_engine``) only provision synthetic users and change grants; every request under test
is served by a client whose database session is bound to ``runtime_engine``, the restricted
runtime role. Markers, users and (private) scopes are unique per test because committed
synthetic rows are retained across tests in the disposable database.
"""

from contextlib import ExitStack

import documents_isolation_support as support
import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.runtime_role import ROLE

pytestmark = pytest.mark.integration


@pytest.fixture
def environment(postgres_engine, runtime_engine):
    admin = sessionmaker(bind=postgres_engine, expire_on_commit=False)
    with ExitStack() as stack:
        environment = support.postgres_environment(admin, runtime_engine, stack)
        yield environment
        environment.cleanup()


def test_private_documents_are_withheld_from_every_non_creator_operation(environment):
    support.behave_private_document_operations(environment)


def test_shared_documents_follow_the_shared_reader_and_owner_only_rules(environment):
    support.behave_shared_document_operations(environment)


def test_pagination_and_export_cursors_exclude_foreign_private_documents(environment):
    support.behave_pagination_and_export(environment)


def test_answers_exclude_foreign_private_sources_alone_and_mixed(environment, monkeypatch):
    support.behave_answers(environment, monkeypatch)


def test_grant_revocation_withholds_documents_and_answers_on_a_live_session(
    environment, monkeypatch
):
    support.behave_grant_revocation(environment, monkeypatch)


def test_replaying_a_logged_out_session_credential_releases_nothing(environment, monkeypatch):
    support.behave_session_revocation(environment, monkeypatch)


def test_requests_under_test_use_the_restricted_runtime_role(
    environment, runtime_engine, postgres_engine
):
    """The clients above are served by ``runtime_engine``; show that engine is the restricted role."""
    with postgres_engine.connect() as privileged:
        assert privileged.scalar(text("SELECT current_user")) != ROLE
        assert privileged.scalar(text("SELECT rolsuper FROM pg_roles WHERE rolname=current_user"))
    with runtime_engine.connect() as runtime:
        assert runtime.scalar(text("SELECT current_user")) == ROLE
        assert not runtime.scalar(text("SELECT rolsuper FROM pg_roles WHERE rolname=current_user"))
    with runtime_engine.connect() as runtime, pytest.raises(DBAPIError):
        runtime.execute(text("SELECT count(*) FROM audit_events"))  # runtime has no audit SELECT
    statements = []

    def count(*arguments):
        statements.append(arguments[2])

    event.listen(runtime_engine, "before_cursor_execute", count)
    try:
        owner = environment.actor("owner", {support.SHARED, support.PRIVATE})
        document = support.create(owner, support.PRIVATE, support.new_mark("rr"))
        assert support.perform(owner, "read", document).status_code == 200
    finally:
        event.remove(runtime_engine, "before_cursor_execute", count)
    assert any("document_records" in statement for statement in statements)
