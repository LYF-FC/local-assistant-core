"""The route-classification completeness control for the whole-MVP leakage suite (Gate 1).

Every registered non-authentication operation has exactly one explicit classification; swept entries
name an operation the adapters really provide; credited entries name existing test functions that
really exist; excluded entries carry a specific reason. The control fails when a new non-authentication
operation is registered without a classification.
"""

import ast
from pathlib import Path

import mvp_leakage_inventory as inventory
import mvp_leakage_support as lk
import pytest

TESTS = Path(__file__).parent
SPECIAL = {("operations", "admin"), ("installation", "admin"), ("reminders", "preferences")}


def operations():
    return {op for op in lk.registered_operations() if not op[1].startswith(inventory.AUTH_PREFIX)}


def classified():
    return inventory.classified(operations())


def unclassified(registered, entries):
    return sorted(registered - set(entries))


def stale(registered, entries):
    return sorted(set(entries) - registered)


def assert_complete(registered, entries):
    missing = unclassified(registered, entries)
    assert not missing, f"registered operations without a classification: {missing}"
    extra = stale(registered, entries)
    assert not extra, f"classifications for operations that are not registered: {extra}"


def test_every_non_authentication_operation_has_exactly_one_classification():
    assert_complete(operations(), classified())


def test_authentication_routes_are_the_only_unclassified_prefix():
    auth = {op for op in lk.registered_operations() if op[1].startswith(inventory.AUTH_PREFIX)}
    assert {path for _, path in auth} == {
        "/api/v1/auth/login",
        "/api/v1/auth/logout",
        "/api/v1/auth/me",
        "/api/v1/auth/scopes/{scope}",
        "/api/v1/auth/session",
    }
    assert not auth & set(classified())


def test_a_new_unclassified_operation_fails_the_control():
    entries = classified()
    registered = operations()
    assert_complete(registered, entries)  # passes before the simulated addition
    with pytest.raises(AssertionError, match="without a classification"):
        assert_complete(registered | {("POST", "/api/v1/brand-new-content")}, entries)
    with pytest.raises(AssertionError, match="not registered"):
        assert_complete(registered - {("GET", "/api/v1/memory")}, entries)


def test_swept_entries_name_an_operation_the_adapters_provide():
    for (method, path), entry in classified().items():
        if entry.kind != "swept":
            continue
        where = (method, path, entry.adapter, entry.what)
        if (entry.adapter, entry.what) in SPECIAL:
            continue
        adapter = lk.ADAPTERS[entry.adapter]
        kind, _, name = entry.what.partition(":")
        if kind == "mutation":
            assert name in adapter.mutations, where
        elif kind == "view":
            assert name in adapter.views(), where
        elif kind == "by_id":
            assert name in adapter.extra_by_id, where
        elif kind == "create":
            assert (
                type(adapter).create is not lk.Adapter.create
                or type(adapter).create_row is not lk.Adapter.create_row
            ), where
        elif kind in {"listing", "export"}:
            assert adapter.has_listing, where
        else:
            assert kind in {"read", "history", "export_one"}, where
            assert callable(getattr(adapter, kind)), where


def function_names(path):
    return {
        node.name
        for node in ast.walk(ast.parse((TESTS / path).read_text()))
        if isinstance(node, ast.FunctionDef)
    }


def test_credited_entries_name_existing_test_functions():
    for key, entry in classified().items():
        if entry.kind != "credited":
            continue
        assert entry.tests and len(entry.reason) > 40, key
        for selector in entry.tests:
            file, _, name = selector.partition("::")
            assert name in function_names(file), (key, selector)


def test_excluded_entries_carry_a_specific_reason_and_work_names_its_suites():
    work = 0
    for (method, path), entry in classified().items():
        if entry.kind != "excluded":
            continue
        assert len(entry.reason) > 30, (method, path)
        if path.startswith("/api/v1/work"):
            work += 1
            for suite in inventory.WORK_SUITES:
                assert (TESTS / suite).exists(), suite
    assert work == 16


def test_the_classification_is_summarised_for_review():
    counts = {}
    for entry in classified().values():
        counts[entry.kind] = counts.get(entry.kind, 0) + 1
    uncovered = sorted(
        path for (_, path), e in classified().items() if e.reason.startswith("uncovered limitation")
    )
    print("classification:", counts, "uncovered limitations:", len(uncovered))
    assert sum(counts.values()) == len(operations())


def test_every_listing_route_has_a_pagination_classification():
    entries = classified()
    table = inventory.pagination(entries)
    listing_routes = {
        key
        for key, entry in entries.items()
        if entry.kind == "swept" and entry.what.partition(":")[0] in {"listing", "export", "view"}
    }
    assert listing_routes <= set(table)
    boundary = {key for key, (kind, _) in table.items() if kind == "boundary"}
    assert boundary, "no listing route has boundary cases"
    for key in boundary:
        adapter = lk.ADAPTERS[entries[key].adapter]
        assert adapter.boundary_model is not None, (
            key,
            "classified as boundary-covered without a model",
        )
    uncovered = sorted(key for key, (kind, _) in table.items() if kind == "uncovered limitation")
    print("pagination:", len(boundary), "boundary-covered routes; uncovered:", uncovered)
    assert uncovered == [("GET", "/api/v1/discovery"), ("POST", "/api/v1/discovery/inbox")]
