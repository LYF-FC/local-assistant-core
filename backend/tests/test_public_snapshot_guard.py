"""The fresh public namespace must refuse unrelated databases before role mutation."""

import pytest

from app.runtime_role import ROLE, configure

GENERIC = {
    "member_a_private",
    "member_b_private",
    "parents_child",
    "member_business",
}


class Probe:
    def __init__(self, scopes, owner="postgres"):
        self.scopes = scopes
        self.owner = owner
        self.statements = []

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, query, args=None):
        self.statements.append(str(query))
        assert str(query).startswith(("SELECT current_user", "SELECT key FROM public.scopes")), (
            "Role mutation attempted before namespace rejection"
        )

    def fetchone(self):
        return self.owner, "butler_test"

    def fetchall(self):
        return [(scope,) for scope in self.scopes]


@pytest.mark.parametrize("missing", ["member_a_private", "member_business"])
def test_missing_generic_namespace_refuses_before_role_ddl(missing):
    probe = Probe(GENERIC - {missing})
    with pytest.raises(ValueError, match="fresh generic-scope database"):
        configure(probe, "synthetic-runtime-password-only-0123456789")
    assert len(probe.statements) == 2


def test_runtime_cannot_use_the_migration_entry_point():
    probe = Probe(GENERIC, owner=ROLE)
    with pytest.raises(ValueError, match="privileged migration connection"):
        configure(probe, "synthetic-runtime-password-only-0123456789")
    assert len(probe.statements) == 1
