"""Pure page planner (proposal 7.3.1): reduction, floors, cascades, resolution, order, limits."""

import itertools
from uuid import uuid4

import pytest

from app import calendar_codes as codes
from app import calendar_plan as planner
from app import calendar_recurrence as rec
from app.calendar_plan import PageBlocked, StoredOverride, StoredSeries, plan_page
from app.calendar_provider import ChangePage, ProviderItem

SOURCE = uuid4()
RID = "TZID=Europe/Paris:20260322T090000"
CANON = "2026-03-22T09:00:00"


def body(**extra):
    return {
        "title": "Synthetic",
        "dtstart": "TZID=Europe/Paris:20260315T090000",
        "duration": 3600,
        "rrule": "FREQ=WEEKLY;COUNT=4",
        **extra,
    }


def sitem(uid="s1", sequence=1, op="upsert", **extra):
    return ProviderItem(
        "series", op, uid, sequence, None, body(**extra) if op == "upsert" else None
    )


def oitem(uid="s1", sequence=1, op="upsert", rid=RID, status="cancelled", **extra):
    content = {"recurrence_id": rid, "status": status, **extra} if op == "upsert" else None
    return ProviderItem("override", op, uid, sequence, rid, content)


def page(*items, cursor="v1:9", has_more=False):
    return ChangePage(tuple(items), cursor, has_more)


def stored_series(uid="s1", sequence=1, state="active", **extra):
    content = rec.normalize_series(body(**extra)) if state == "active" else None
    return StoredSeries(uuid4(), uid, state, sequence, content)


def stored_override(
    uid="s1", rid=CANON, sequence=1, state="active", cascade=False, status="cancelled"
):
    content = rec.Override(rid, status, None, None, None) if state == "active" else None
    return StoredOverride(uuid4(), uid, rid, state, sequence, cascade, content)


def run(pg, series=(), overrides=(), since="v1:0", **limits):
    args = {"applied_seq": 0, "series_active": 0, "series_total": 0, **limits}
    args["series_active"] = limits.get("series_active", sum(s.state == "active" for s in series))
    args["series_total"] = limits.get("series_total", len(series))
    return plan_page(
        pg,
        since,
        {s.uid: s for s in series},
        {(o.uid, o.rid): o for o in overrides},
        **args,
    )


def blocked(pg, series=(), overrides=(), **kwargs):
    with pytest.raises(PageBlocked) as caught:
        run(pg, series, overrides, **kwargs)
    return caught.value


def summary(plan):
    return (
        [
            (w.uid, w.op, w.state, w.sequence, w.hash, w.pass_sequence, len(w.cascade))
            for w in plan.series
        ],
        [(w.uid, w.rid, w.op, w.state, w.sequence, w.hash) for w in plan.overrides],
        dict(plan.counters),
    )


# ---------------------------------------------------------------------------------------------
# Determinism: item reordering never changes the result (Step 4)
# ---------------------------------------------------------------------------------------------
def test_every_permutation_of_a_page_gives_the_identical_plan():
    items = [
        sitem("b", 1),
        sitem("a", 2),
        oitem("a", 1),
        oitem("b", 3, rid="TZID=Europe/Paris:20260329T090000"),
        sitem("c", 5, op="delete"),
    ]
    results = {repr(summary(run(page(*perm)))) for perm in itertools.permutations(items)}
    assert len(results) == 1
    series, overrides, _ = summary(run(page(*items)))
    # deletions before upserts, then uid byte order; overrides after their series
    assert [row[0:2] for row in series] == [("c", "delete"), ("a", "upsert"), ("b", "upsert")]
    assert [row[0] for row in overrides] == ["a", "b"]


def test_an_override_before_its_series_in_one_page_is_fine():
    plan = run(page(oitem("s1", 1), sitem("s1", 1)))
    assert [w.uid for w in plan.series] == ["s1"] and [w.rid for w in plan.overrides] == [CANON]


def test_overrides_sort_by_series_uid_then_recurrence_id_in_utf8_bytes():
    other = "TZID=Europe/Paris:20260315T090000"
    plan = run(page(sitem("é"), sitem("z"), oitem("z", 1, rid=RID), oitem("é", 1, rid=other)))
    assert [w.uid for w in plan.series] == ["z", "é"]  # byte order, not locale
    assert [(w.uid, w.rid) for w in plan.overrides] == [("z", CANON), ("é", "2026-03-15T09:00:00")]


# ---------------------------------------------------------------------------------------------
# Step 2: the reduction table
# ---------------------------------------------------------------------------------------------
def test_same_sequence_same_content_collapses_and_different_content_conflicts():
    plan = run(page(sitem("s1", 1), sitem("s1", 1)))
    assert plan.counters["replayed"] == 1 and len(plan.series) == 1
    error = blocked(page(sitem("s1", 1), sitem("s1", 1, title="Other")))
    assert (error.code, error.entity, error.sequence) == ("sequence_conflict", "series", 1)


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        (sitem(sequence=3), {"ignored_stale": 1}),
        (sitem(sequence=5), {"replayed": 1}),
        (sitem(sequence=5, op="delete"), "sequence_conflict"),
        (sitem(sequence=5, title="Changed"), "sequence_conflict"),
        (sitem(sequence=6, title="Changed"), "write"),
    ],
)
def test_an_active_series_against_each_sequence_relation(item, expected):
    stored = stored_series(sequence=5)
    if expected == "sequence_conflict":
        assert blocked(page(item), [stored]).code == "sequence_conflict"
        return
    plan = run(page(item), [stored])
    if expected == "write":
        assert [(w.op, w.sequence) for w in plan.series] == [("upsert", 6)]
    else:
        assert not plan.series and dict(plan.counters) == expected


def test_a_series_tombstone_floor_refuses_resurrection_and_conflicts_at_the_floor():
    tomb = stored_series(sequence=5, state="deleted")
    assert dict(run(page(sitem(sequence=4)), [tomb]).counters) == {"ignored_stale": 1}
    assert blocked(page(sitem(sequence=5)), [tomb]).code == "sequence_conflict"
    assert dict(run(page(sitem(sequence=5, op="delete")), [tomb]).counters) == {"replayed": 1}
    raised = run(page(sitem(sequence=6, op="delete")), [tomb])
    assert [(w.op, w.state, w.sequence, w.hash) for w in raised.series] == [
        ("delete", "deleted", 6, codes.TOMBSTONE_HASH)
    ]
    revived = run(page(sitem(sequence=6)), [tomb])
    assert [(w.op, w.state) for w in revived.series] == [("revive", "active")]


def test_unknown_entity_deletion_creates_a_tombstone_with_a_floor():
    plan = run(page(sitem("new", 4, op="delete")))
    assert [(w.op, w.state, w.sequence, w.stored) for w in plan.series] == [
        ("delete", "deleted", 4, None)
    ]


def test_floor_origin_decides_what_an_item_at_an_override_floor_means():
    series = stored_series(sequence=1)
    delete_origin = stored_override(sequence=4, state="deleted", cascade=False)
    cascade_origin = stored_override(sequence=4, state="deleted", cascade=True)
    # delete-origin floor: a delete is a counted replay, an upsert is a conflict
    assert dict(run(page(oitem(sequence=4, op="delete")), [series], [delete_origin]).counters) == {
        "replayed": 1
    }
    assert blocked(page(oitem(sequence=4)), [series], [delete_origin]).code == "sequence_conflict"
    # cascade-origin floor: any item at the floor is a conflict (no content to prove a resend)
    for item in (oitem(sequence=4), oitem(sequence=4, op="delete")):
        assert blocked(page(item), [series], [cascade_origin]).code == "sequence_conflict"
    # above the floor: a delete raises it, an upsert revives; below: stale
    assert [
        w.op
        for w in run(page(oitem(sequence=5, op="delete")), [series], [cascade_origin]).overrides
    ] == ["delete"]
    assert [w.op for w in run(page(oitem(sequence=5)), [series], [cascade_origin]).overrides] == [
        "revive"
    ]
    assert dict(run(page(oitem(sequence=3)), [series], [cascade_origin]).counters) == {
        "ignored_stale": 1
    }


def test_net_results_collapse_intermediate_versions():
    plan = run(
        page(sitem(sequence=1), sitem(sequence=2, title="Two"), sitem(sequence=3, title="Three"))
    )
    assert [(w.op, w.sequence) for w in plan.series] == [("upsert", 3)]
    assert plan.series[0].content.title == "Three"
    plan = run(page(sitem(sequence=1), sitem(sequence=2, op="delete")))
    assert [(w.op, w.state) for w in plan.series] == [("delete", "deleted")]
    assert plan.change_rows == 1


# ---------------------------------------------------------------------------------------------
# Cascades, revival, supersession (Step 3)
# ---------------------------------------------------------------------------------------------
def test_a_series_delete_cascades_every_active_override_in_recurrence_id_order():
    series = stored_series(sequence=1)
    stored = [
        stored_override(rid="2026-03-29T09:00:00", sequence=2),
        stored_override(rid=CANON, sequence=2),
        stored_override(rid="2026-04-05T09:00:00", sequence=2, state="deleted"),
    ]
    plan = run(page(sitem(sequence=2, op="delete")), [series], stored)
    write = plan.series[0]
    assert (write.op, len(write.cascade)) == ("delete", 2)
    assert [o.rid for o in write.cascade] == [CANON, "2026-03-29T09:00:00"]
    assert not plan.overrides


def test_delete_then_a_higher_upsert_in_one_page_is_a_revive_with_the_cascade_performed():
    series = stored_series(sequence=1)
    plan = run(
        page(sitem(sequence=3, title="Back"), sitem(sequence=2, op="delete")),
        [series],
        [stored_override(sequence=1)],
    )
    write = plan.series[0]
    assert (write.op, write.state, write.sequence, write.pass_sequence, len(write.cascade)) == (
        "revive",
        "active",
        3,
        2,
        1,
    )


def test_a_resent_override_after_a_revive_must_beat_its_floor():
    series = stored_series(sequence=1)
    old = stored_override(sequence=1)
    items = [sitem(sequence=3, title="Back"), sitem(sequence=2, op="delete")]
    # equal to the cascade floor: conflict; above: revives the same row
    assert blocked(page(*items, oitem(sequence=1)), [series], [old]).code == "sequence_conflict"
    plan = run(page(*items, oitem(sequence=2)), [series], [old])
    assert [(w.op, w.sequence) for w in plan.overrides] == [("revive", 2)] or [
        (w.op, w.sequence) for w in plan.overrides
    ] == [("upsert", 2)]
    assert len(plan.series[0].cascade) == 1


def test_overrides_of_a_deleted_series_are_superseded_never_an_error():
    stored = stored_series(sequence=3, state="deleted")
    plan = run(page(oitem(sequence=9), oitem(sequence=10, op="delete")), [stored])
    assert not plan.overrides and not plan.series
    assert dict(plan.counters) == {"superseded_by_delete": 2}
    # deleted in the same page
    plan = run(page(oitem(sequence=1), sitem(sequence=2, op="delete")), [stored_series(sequence=1)])
    assert dict(plan.counters) == {"superseded_by_delete": 1} and not plan.overrides


def test_an_override_of_an_unknown_series_is_an_orphan_with_a_sanitized_detail():
    error = blocked(page(sitem("other", 1), oitem("ghost", 7)))
    assert (error.code, error.entity, error.item_index, error.sequence) == (
        "override_orphan",
        "override",
        1,
        7,
    )
    detail = error.detail(SOURCE)
    assert set(detail) == {
        "code",
        "entity",
        "item_index",
        "sequence",
        "uid_digest",
        "recurrence_digest",
    }
    assert detail["uid_digest"] == codes.uid_digest(SOURCE, "ghost")
    assert (
        detail["recurrence_digest"] is None
    )  # unknown series: the recurrence id cannot be canonicalized


def test_an_override_delete_under_an_active_series_creates_a_tombstone():
    plan = run(page(oitem(sequence=4, op="delete")), [stored_series()])
    assert [(w.op, w.state, w.stored) for w in plan.overrides] == [("delete", "deleted", None)]


# ---------------------------------------------------------------------------------------------
# Membership of the final instance set (5.8) and the stored recheck (R1)
# ---------------------------------------------------------------------------------------------
def test_an_override_outside_the_instance_set_refuses_the_whole_page():
    not_member = "TZID=Europe/Paris:20260323T090000"
    error = blocked(page(sitem(), oitem(rid=not_member, sequence=2)))
    assert (error.code, error.item_index, error.sequence) == ("override_unmatched", 1, 2)
    assert error.detail(SOURCE)["recurrence_digest"] == codes.recurrence_digest(
        SOURCE, "s1", "2026-03-23T09:00:00"
    )


def test_a_cancelled_override_still_has_to_be_a_member():
    error = blocked(
        page(sitem(), oitem(rid="TZID=Europe/Paris:20260323T090000", status="cancelled"))
    )
    assert error.code == "override_unmatched"


def changed_rule_page(**extra):
    return sitem(sequence=2, rrule="FREQ=WEEKLY;COUNT=1", **extra)


def test_a_rule_change_rechecks_untouched_stored_overrides():
    series = stored_series(sequence=1)
    stored = stored_override(sequence=7)
    error = blocked(page(changed_rule_page()), [series], [stored])
    assert (error.code, error.item_index, error.sequence) == ("override_unmatched", None, 7)
    assert error.detail(SOURCE)["recurrence_digest"] == codes.recurrence_digest(SOURCE, "s1", CANON)


def test_only_a_strictly_higher_delete_resolves_a_mismatch_never_an_update_or_stale_delete():
    series, stored = stored_series(sequence=1), stored_override(sequence=7)
    update = oitem(sequence=8, status="tentative")
    assert (
        blocked(page(changed_rule_page(), update), [series], [stored]).code == "override_unmatched"
    )
    stale = oitem(sequence=6, op="delete")
    assert (
        blocked(page(changed_rule_page(), stale), [series], [stored]).code == "override_unmatched"
    )
    equal = oitem(sequence=7, op="delete")
    assert blocked(page(changed_rule_page(), equal), [series], [stored]).code == "sequence_conflict"
    higher = oitem(sequence=8, op="delete")
    plan = run(page(changed_rule_page(), higher), [series], [stored])
    assert [(w.op, w.state) for w in plan.overrides] == [("delete", "deleted")]


def test_the_reported_unmatched_override_is_first_by_series_uid_then_recurrence_id_in_bytes():
    series = [stored_series("b", 1), stored_series("a", 1)]
    stored = [
        stored_override("b", CANON, 1),
        stored_override("a", "2026-03-29T09:00:00", 1),
        stored_override("a", CANON, 1),
    ]
    one_event = {"rrule": "FREQ=WEEKLY;COUNT=1"}  # only 2026-03-15 remains a member
    pg = page(sitem("b", 2, **one_event), sitem("a", 2, **one_event))
    error = blocked(pg, series, stored)
    assert (error.uid, error.rid) == ("a", CANON)  # series "a" before "b"; 03-22 before 03-29


def test_an_unchanged_series_hash_needs_no_recheck():
    series, stored = stored_series(sequence=1), stored_override(sequence=1)
    plan = run(page(sitem(sequence=2)), [series], [stored])  # same content, higher sequence
    assert [(w.op, w.sequence) for w in plan.series] == [("upsert", 2)]


# ---------------------------------------------------------------------------------------------
# Step 1: shape, grammar, cursor, size; error priority
# ---------------------------------------------------------------------------------------------
def test_cursor_progress_table():
    one = page(sitem(), cursor="v1:0")
    assert blocked(one).code == "cursor_no_progress"
    assert blocked(page(cursor="v1:0", has_more=True)).code == "cursor_no_progress"
    assert run(page(cursor="v1:0")).change_rows == 0  # caught up
    assert run(page(cursor="v1:5", has_more=True)).change_rows == 0
    for cursor in ("", "x" * 513, None):
        assert blocked(page(sitem(), cursor=cursor)).code == "cursor_malformed"


def test_page_size_and_item_count_limits():
    assert blocked(page(*[sitem(f"s{i}") for i in range(101)])).code == "page_too_large"
    assert blocked(page(sitem(title="é" * 160, description="x" * 70000))).code in {
        "page_too_large",
        "item_malformed",
    }


@pytest.mark.parametrize(
    "item",
    [
        ProviderItem("event", "upsert", "s1", 1, None, body()),
        ProviderItem("series", "merge", "s1", 1, None, body()),
        ProviderItem("series", "upsert", "", 1, None, body()),
        ProviderItem("series", "upsert", None, 1, None, body()),
        ProviderItem("series", "upsert", "s1", -1, None, body()),
        ProviderItem("series", "upsert", "s1", True, None, body()),
        ProviderItem("series", "upsert", "s1", 1, "x", body()),
        ProviderItem("series", "upsert", "s1", 1, None, None),
        ProviderItem("series", "delete", "s1", 1, None, body()),
        ProviderItem("override", "upsert", "s1", 1, None, {"status": "cancelled"}),
    ],
)
def test_malformed_items_block_with_item_malformed(item):
    error = blocked(page(item))
    assert error.code == "item_malformed"
    detail = error.detail(SOURCE)
    assert detail["recurrence_digest"] is None and detail["code"] == "item_malformed"


def test_grammar_errors_carry_the_item_and_never_the_recurrence_digest():
    error = blocked(page(sitem(), sitem("s2", rrule="FREQ=SECONDLY")))
    assert (error.code, error.entity, error.item_index) == ("freq_unsupported", "series", 1)
    error = blocked(page(sitem(), oitem(rid="20260322")))
    assert error.code == "override_type_mismatch" and error.rid is None
    mismatch = oitem(rid=RID)
    mismatch = ProviderItem(
        "override",
        "upsert",
        "s1",
        1,
        RID,
        {"recurrence_id": "TZID=Europe/Paris:20260329T090000", "status": "cancelled"},
    )
    assert blocked(page(sitem(), mismatch)).code == "item_malformed"


def test_the_first_violated_step_is_reported():
    # step 1 (grammar) beats step 2 (conflict) and step 3 (orphan)
    pg = page(
        sitem("a", 1),
        sitem("a", 1, title="x"),
        oitem("ghost", 1),
        sitem("z", 1, rrule="FREQ=SECONDLY"),
    )
    assert blocked(pg).code == "freq_unsupported"
    # step 2 beats step 3
    assert (
        blocked(page(sitem("a", 1), sitem("a", 1, title="x"), oitem("ghost", 1))).code
        == "sequence_conflict"
    )


def test_equal_errors_pick_the_first_entity_in_write_order_not_page_position():
    first = blocked(
        page(sitem("b", rrule="FREQ=SECONDLY"), sitem("a", rrule="FREQ=YEARLY;BYHOUR=1"))
    )
    second = blocked(
        page(sitem("a", rrule="FREQ=YEARLY;BYHOUR=1"), sitem("b", rrule="FREQ=SECONDLY"))
    )
    assert first.code == second.code
    assert first.uid == second.uid == "a"


# ---------------------------------------------------------------------------------------------
# Step 5: limits on the final state
# ---------------------------------------------------------------------------------------------
def test_limits_apply_to_the_final_state_of_the_page_not_intermediate_states():
    assert blocked(page(sitem("n")), series_active=200, series_total=200).code == "series_limit"
    # one delete plus one add at the limit passes
    full = [stored_series("old")]
    plan = run(
        page(sitem("old", 2, op="delete"), sitem("new", 1)),
        full,
        series_active=200,
        series_total=200,
    )
    assert plan.change_rows == 2
    assert (
        blocked(page(sitem("n", 1, op="delete")), series_active=0, series_total=400).code
        == "tombstone_limit"
    )


def test_override_limits_and_the_change_log_limit():
    series = stored_series()
    active = [stored_override(rid=f"2026-01-{d:02d}T09:00:00", sequence=1) for d in range(1, 29)]
    many = []
    for index in range(100):
        many.append(
            stored_override(rid=f"2025-{index // 28 + 1:02d}-{index % 28 + 1:02d}T09:00:00")
        )
    full = [*active, *many][:100]
    extra = oitem(rid="TZID=Europe/Paris:20260322T090000", sequence=5)
    pg = page(extra)
    assert blocked(pg, [series], full).code in {"override_limit", "override_unmatched"}
    assert blocked(page(sitem()), applied_seq=5000).code == "change_log_full"
    assert run(page(sitem()), applied_seq=4999).change_rows == 1


def test_tombstones_count_toward_the_total_override_limit():
    series = stored_series()
    tombs = [
        stored_override(rid=f"2025-{m:02d}-{d:02d}T09:00:00", sequence=1, state="deleted")
        for m in range(1, 9)
        for d in range(1, 29)
    ][:200]
    assert blocked(page(oitem(sequence=3, op="delete")), [series], tombs).code == "tombstone_limit"


def test_a_cascade_frees_the_active_override_budget_of_its_series():
    series = stored_series()
    active = [stored_override(rid=f"2026-01-{d:02d}T09:00:00") for d in range(1, 29)]
    plan = run(page(sitem(sequence=2, op="delete")), [series], active)
    assert len(plan.series[0].cascade) == 28


def test_hashes_are_content_hashes_and_deletes_share_the_fixed_tombstone_hash():
    one = run(page(sitem(sequence=1)))
    two = run(page(sitem(sequence=9)))
    assert one.series[0].hash == two.series[0].hash != codes.TOMBSTONE_HASH
    assert run(page(sitem(sequence=1, op="delete"))).series[0].hash == codes.TOMBSTONE_HASH
    assert planner.hash_of(None) == codes.TOMBSTONE_HASH
    assert (
        codes.TOMBSTONE_HASH == "136a90c93d282c605c5a7003b6a381fa429e9bce3201d454cb59a41480005b01"
    )
