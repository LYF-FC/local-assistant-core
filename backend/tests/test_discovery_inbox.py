import pytest
from test_approvals import signin
from test_discovery import create, feedback
from test_discovery_ideas import idea


def inbox(client, headers, **filters):
    return client.post("/api/v1/discovery/inbox", headers=headers, json=filters)


def test_literal_search_topic_stage_interest_and_cursor_intersect(auth_client):
    headers = signin(auth_client, "bob")
    first = idea(
        auth_client,
        headers,
        title="Synthetic 100%_literal",
        summary="A quoted Idea",
        topic="photo-local",
    ).json()
    second = create(auth_client, headers, title="Synthetic evidenced", topic="photo-local").json()
    third = create(auth_client, headers, title="Other topic", topic="other-topic").json()
    assert feedback(auth_client, headers, second, "later").status_code == 200
    assert feedback(auth_client, headers, third, "not_relevant").status_code == 200
    assert [r["id"] for r in inbox(auth_client, headers, q="%_").json()["items"]] == [first["id"]]
    assert [
        r["id"]
        for r in inbox(
            auth_client,
            headers,
            q="quoted IDEA",
            topic="photo-local",
            stage="idea",
            interest="unanswered",
        ).json()["items"]
    ] == [first["id"]]
    assert [
        r["id"]
        for r in inbox(auth_client, headers, stage="proposal", interest="later").json()["items"]
    ] == [second["id"]]
    assert inbox(auth_client, headers, interest="not_relevant").json()["items"] == []
    assert [
        r["id"]
        for r in inbox(
            auth_client, headers, interest="not_relevant", include_dismissed=True
        ).json()["items"]
    ] == [third["id"]]
    page = inbox(auth_client, headers, limit=1, topic="photo-local").json()
    cursor = page["next_cursor"]
    assert page["items"][0]["id"] == second["id"]
    assert [
        r["id"]
        for r in inbox(
            auth_client,
            headers,
            topic="photo-local",
            after=cursor["id"],
            after_priority=cursor["priority"],
        ).json()["items"]
    ] == [first["id"]]


@pytest.mark.parametrize(
    "change",
    [
        {"q": "x" * 121},
        {"q": "private\nquery"},
        {"q": "query\n"},
        {"topic": "bad topic"},
        {"stage": "confirmed"},
        {"interest": "approved"},
        {"limit": 26},
        {"limit": True},
        {"include_dismissed": "true"},
        {"after_priority": True},
        {"scope": "work_private"},
    ],
)
def test_strict_inbox_filters(auth_client, change):
    headers = signin(auth_client, "bob")
    assert inbox(auth_client, headers, **change).status_code == 422


def test_inbox_requires_current_session_csrf_and_private_owner(auth_client, auth_store):
    assert inbox(auth_client, {}).status_code == 401
    headers = signin(auth_client, "bob")
    row = idea(auth_client, headers).json()
    assert inbox(auth_client, {}).status_code == 403
    assert inbox(auth_client, dict(headers, Origin="https://other.invalid")).status_code == 403
    other = signin(auth_client)
    assert all(
        r["id"] != row["id"] for r in inbox(auth_client, other, q="Synthetic").json()["items"]
    )
    assert inbox(auth_client, other, after_priority=999).status_code == 422
