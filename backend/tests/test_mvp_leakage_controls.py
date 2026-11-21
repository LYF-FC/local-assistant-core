"""Sensitivity controls for the whole-MVP leakage harness (Gate 1).

Each control feeds the harness a deliberately simulated failure and shows that the harness fails
for the intended reason, then that it passes when the same input is clean. The simulations are
test doubles (a fake response object, a subclass of a surface adapter inside this module, a log
record built here). No application route is changed and no production code is made vulnerable.
"""

import logging
from contextlib import ExitStack

import mvp_leakage_support as lk
import pytest


class Fake:
    """Just enough of a response for the harness: status, JSON body, text and headers."""

    def __init__(self, status, body, headers=None):
        self.status_code = status
        self._body = body
        self.headers = headers or {}

    def json(self):
        return self._body

    @property
    def text(self):
        import json

        return json.dumps(self._body)


class Stub:
    name = "stub"


def rec(shared=False, mark="stub-mark-0123456789ab", ident="00000000-0000-4000-8000-0000000000aa"):
    return lk.Rec(Stub(), lk.PRIVATE, mark, {"id": ident, "owner_id": "owner-uuid"}, shared)


# ---------------------------------------------------------------- unit controls (no database)


def test_a_body_carrying_a_foreign_canary_is_detected_and_a_clean_body_passes():
    withheld = rec()
    clean = Fake(404, {"detail": "Access denied"})
    lk.assert_no_leak(clean, [withheld], "control")
    for leaking in (
        Fake(404, {"detail": f"{withheld.mark} not found"}),
        Fake(404, {"detail": withheld.id}),
        Fake(403, {"detail": "Access denied"}, {"X-Debug": withheld.mark}),
    ):
        with pytest.raises(AssertionError, match="needle in (body|headers)"):
            lk.assert_no_leak(leaking, [withheld], "control")


def test_a_leaked_total_is_detected_and_a_matching_total_passes():
    lk.assert_counts_match(Fake(200, {"items": [], "total": 0}), 0, "control")
    lk.assert_counts_match(Fake(200, {"items": [1, 2], "total": 2}), 2, "control")
    with pytest.raises(AssertionError, match="count differs from the visible set"):
        lk.assert_counts_match(Fake(200, {"items": [], "total": 7}), 0, "control")
    with pytest.raises(AssertionError, match="has-more flag with nothing visible"):
        lk.assert_counts_match(Fake(200, {"items": [], "has_more": True}), 0, "control")


def test_a_leaked_cursor_is_detected_and_an_opaque_cursor_passes():
    forbidden = ["00000000-0000-4000-8000-0000000000aa"]
    lk.assert_cursors_clean(["opaque-token"], forbidden, "control")
    with pytest.raises(AssertionError, match="continuation token carries a foreign id"):
        lk.assert_cursors_clean([{"after": forbidden[0]}], forbidden, "control")
    with pytest.raises(AssertionError, match="empty continuation token"):
        lk.assert_cursors_clean([""], forbidden, "control")


def test_a_log_line_with_a_foreign_canary_is_detected_and_a_clean_log_passes():
    def record(message):
        return logging.LogRecord("app.control", logging.WARNING, __file__, 1, message, None, None)

    lk.assert_logs_clean([record("request refused")], ["stub-mark-0123456789ab"])
    with pytest.raises(AssertionError, match="canary in a log record"):
        lk.assert_logs_clean(
            [record("lookup stub-mark-0123456789ab failed")], ["stub-mark-0123456789ab"]
        )
    structured = record("request refused")
    structured.detail = "stub-mark-0123456789ab"  # a structured field, not the message
    with pytest.raises(AssertionError, match="canary in a log record"):
        lk.assert_logs_clean([structured], ["stub-mark-0123456789ab"])


# ------------------------------------- end-to-end controls: the real sweep over a leaking double


@pytest.fixture
def world(auth_client, auth_store):
    with ExitStack() as stack:
        env = lk.support.sqlite_environment(auth_store, stack)
        world = lk.build_world(env)
        yield world
        lk.cleanup(world)


class LeakyBody(lk.Tasks):
    """The peer's denial for the owner's private task names the task (a leaked body)."""

    def read(self, caller, record):
        response = super().read(caller, record)
        if caller.kind == lk.PEER and response.status_code == 404:
            return Fake(404, {"detail": f"Task {record.mark} is private"})
        return response


class LeakyTotal(lk.Tasks):
    """The peer's listing reports a total larger than the peer's visible set."""

    def listing(self, caller, scope, cursor=None):
        response = super().listing(caller, scope, cursor)
        if caller.kind == lk.PEER and response.status_code == 200:
            return Fake(200, {**response.json(), "total": 99})
        return response


class LeakyCursor(lk.Tasks):
    """The peer's first page continues with a token that is the id of one of the owner's records."""

    foreign = None

    def listing(self, caller, scope, cursor=None):
        if caller.kind == lk.PEER and cursor == self.foreign:  # the continuation page is empty
            return Fake(200, {"items": [], "next_cursor": None})
        response = super().listing(caller, scope, cursor)
        if caller.kind == lk.PEER and cursor is None and response.status_code == 200:
            return Fake(200, {**response.json(), "next_cursor": self.foreign})
        return response


class LeakyLog(lk.Tasks):
    """The adapter's request path logs the task title (a log line with a foreign canary)."""

    def read(self, caller, record):
        logging.getLogger("app.control").warning("refusing %s", record.mark)
        return super().read(caller, record)


def prepared(world, adapter):
    seeded = lk.seed(world, adapter)
    lk.revoke(world)
    return seeded


def test_the_sweep_catches_a_leaked_body(world):
    seeded = prepared(world, LeakyBody())
    with pytest.raises(AssertionError, match="needle in body"):
        lk.sweep_by_id(world, LeakyBody(), seeded)
    lk.sweep_by_id(world, lk.ADAPTERS["tasks"], seeded)  # the same records pass when nothing leaks


def test_the_sweep_catches_a_leaked_total(world):
    seeded = prepared(world, LeakyTotal())
    with pytest.raises(AssertionError, match="count differs from the visible set"):
        lk.sweep_lists(world, LeakyTotal(), seeded)
    lk.sweep_lists(world, lk.ADAPTERS["tasks"], seeded)


def test_the_sweep_catches_a_leaked_cursor(world):
    adapter = LeakyCursor()
    seeded = prepared(world, adapter)
    adapter.foreign = seeded.owner_private[0].id
    with pytest.raises(AssertionError, match="continuation token carries a foreign id"):
        lk.sweep_lists(world, adapter, seeded)
    lk.sweep_lists(world, lk.ADAPTERS["tasks"], seeded)


def test_the_sweep_catches_a_leaked_log_line(world, caplog):
    caplog.set_level(logging.DEBUG)
    adapter = LeakyLog()
    seeded = prepared(world, adapter)
    lk.sweep_by_id(world, adapter, seeded)
    with pytest.raises(AssertionError, match="canary in a log record"):
        lk.assert_logs_clean(caplog.records, lk.content_marks([seeded]))
    caplog.clear()
    lk.sweep_by_id(world, lk.ADAPTERS["tasks"], seeded)
    lk.assert_logs_clean(caplog.records, lk.content_marks([seeded]))


# ------------------------------------- page-boundary controls: an in-memory listing, correct or not


class FakeAdapter:
    name = "fake"
    boundary_page = 25


def paged(sc, actor_visible, mode):
    """A listing over the scenario's keys. ``actor_visible`` are the keys the actor may see; the
    others are foreign. ``mode`` selects a correct keyset listing or one deliberate defect."""
    everything = sorted(sc.visible + sc.foreign)
    page = sc.page

    def fetch(cursor):
        after = int(__import__("uuid").UUID(cursor)) if cursor else 0
        if mode == "filter_after_limit":
            window = [n for n in everything if n > after][: page + 1]
            rows = [n for n in window if n in actor_visible]
        else:
            greater = (lambda n: n >= after) if mode == "duplicate" else (lambda n: n > after)
            rows = [n for n in everything if greater(n) and n in actor_visible][: page + 1]
        more = len(rows) > page
        if mode == "has_more_from_unfiltered":
            more = len([n for n in everything if n > after]) > page and len(rows) >= 1
        shown = rows[:page]
        following = None
        if more and shown:
            last = rows[page] if mode == "skip_one" and len(rows) > page else shown[-1]
            following = sc.uid(last)
        return [sc.uid(n) for n in shown], following, None

    return fetch


def check(mode, visible_count=26):
    sc = lk.scenario(FakeAdapter(), 1, "control", visible_count)
    pages = lk.fetch_pages(paged(sc, set(sc.visible), mode), sc.start)
    lk.verify_pages(sc, pages, sc.visible, ("control", mode))


def test_the_boundary_check_passes_a_correct_listing_and_catches_each_paging_defect():
    check("correct")
    check("correct", 25)  # exactly one page: no continuation although foreign keys follow
    with pytest.raises(AssertionError, match="sequence differs"):
        check(
            "filter_after_limit"
        )  # visibility applied after the limit: short pages, skipped records
    with pytest.raises(AssertionError, match="continuation leads to an empty page"):
        check("has_more_from_unfiltered", 25)  # a continuation caused by a foreign key
    with pytest.raises(AssertionError, match="sequence differs"):
        check("skip_one")  # the continuation token skips the first record of the next page
    with pytest.raises(AssertionError, match="(duplicated|sequence differs)"):
        check("duplicate")  # the boundary record is listed twice


def test_the_scenarios_would_expose_filtering_after_the_limit():
    for count in (25, 26):
        sc = lk.scenario(FakeAdapter(), 1, "control", count)
        assert lk.naive_first_page(sc) != sc.visible[:25]
        foreign = sc.foreign
        around = [
            n
            for n in foreign
            if sc.visible[23] < n < sc.visible[24] + 2
            or n in (sc.visible[24] - 1, sc.visible[24] + 1)
        ]
        assert around, "foreign keys sit immediately beside the page-boundary key"
