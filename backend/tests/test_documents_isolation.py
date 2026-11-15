"""Document and document-answer isolation on SQLite (no database role is involved here).

Behavior and contract references live in ``documents_isolation_support``. The restricted
PostgreSQL runtime-role mirror is ``integration/test_documents_isolation_postgres.py``.
Existing coverage credited rather than repeated one-for-one:
``test_documents.py::test_shared_read_and_private_owner_and_revocation`` and
``test_document_answers.py::test_private_shared_revocation_and_admin_boundaries``.
"""

from contextlib import ExitStack

import documents_isolation_support as support
import pytest


@pytest.fixture
def environment(auth_client, auth_store):  # auth_client installs the SQLite database override
    with ExitStack() as stack:
        environment = support.sqlite_environment(auth_store, stack)
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
