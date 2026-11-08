"""Shared committed synthetic review fixture for isolated PostgreSQL tests."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.engine import make_url
from work_storage_helpers import PASSWORD, connect, insert

from app import work_drafts, work_lifecycle, work_read, work_review
from app.config import settings
from app.main import app
from app.models import User
from app.work_manage import administer
from app.work_review_storage import provision_reviews


@pytest.fixture
def review_case(scenario, storage_case):
    client, headers, _, maker, user_id = scenario
    case = dict(
        storage_case["a"],
        client=client,
        headers=headers,
        maker=maker,
        actor=user_id,
        storage=storage_case,
    )
    case["source"] = insert(storage_case)
    case["policy"] = uuid4()
    with maker.begin() as db:
        administer(db, "grant", case["slug"], db.get(User, user_id).slug)
    with connect() as db:
        db.execute(
            "INSERT INTO work.retention_policies VALUES(%s,%s,86400)",
            (case["workspace"], case["policy"]),
        )
        db.execute(
            "INSERT INTO work.source_registry(workspace_id,id) VALUES(%s,%s)",
            (case["workspace"], case["source"]),
        )
        provision_reviews(db, case["slug"])
    with connect() as db, db.transaction():
        case["item"] = work_drafts.create(
            db,
            case["workspace"],
            user_id,
            case["policy"],
            work_lifecycle.Draft(
                kind="decision",
                marker="synthetic:review-note",
                source_ids=(case["source"],),
                retain_until=datetime.now(UTC) + timedelta(hours=1),
            ),
        )
    engine = work_read.workspace_engine(
        make_url(settings.database_url).set(username=case["login"], password=PASSWORD)
    )
    app.dependency_overrides[work_review.get_review_engines] = lambda: work_read.WorkspaceEngines(
        {case["workspace"]: engine}
    )
    case["engine"] = engine
    try:
        yield case
    finally:
        app.dependency_overrides.pop(work_review.get_review_engines, None)
        engine.dispose()
