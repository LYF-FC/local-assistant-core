from uuid import UUID

import pytest

from app.work_storage import role_name


def test_storage_role_identity_is_bounded_and_database_workspace_specific():
    workspace = UUID("11111111-1111-4111-8111-111111111111")
    name = role_name(4294967295, workspace)
    assert name == "butler_work_4294967295_11111111111141118111111111111111"
    assert len(name) <= 63
    assert role_name(1, workspace) != role_name(2, workspace)
    assert role_name(1, workspace) != role_name(1, UUID("22222222-2222-4222-8222-222222222222"))


@pytest.mark.parametrize("oid", [0, -1, 4294967296, True, "1", "1; RESET ROLE"])
def test_role_identifier_rejects_untrusted_database_identity(oid):
    with pytest.raises(ValueError):
        role_name(oid, UUID(int=1))


def test_role_identifier_rejects_untyped_workspace():
    with pytest.raises(TypeError):
        role_name(1, "11111111-1111-4111-8111-111111111111; RESET ROLE")
