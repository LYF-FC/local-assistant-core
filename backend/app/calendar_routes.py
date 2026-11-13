from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session, sessionmaker

from app import calendar_contracts as contract
from app import calendar_sync, calendars
from app.auth_routes import get_db
from app.manual_tasks import Expected, Scoped
from app.task_routes import execute

router = APIRouter(prefix="/api/v1/calendars", tags=["calendar snapshots"])


@router.post("")
def create(body: contract.Create, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(db, request, lambda token, csrf: calendars.create(db, token, csrf, body))


@router.post("/query")
def query(body: contract.Query, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(db, request, lambda token, csrf: calendars.listing(db, token, csrf, body))


@router.post("/briefing")
def briefing(body: contract.Briefing, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(db, request, lambda token, csrf: calendars.briefing(db, token, csrf, body))


# Explicit typed routes keep validation ahead of the transaction boundary.
@router.post("/{identifier}/read")
def read(identifier: UUID, body: Scoped, request: Request, db: Annotated[Session, Depends(get_db)]):
    return execute(
        db,
        request,
        lambda token, csrf: calendars.operate(db, token, csrf, identifier, body, "read"),
    )


@router.post("/{identifier}/import")
def ingest(
    identifier: UUID,
    body: contract.Import,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    return execute(
        db,
        request,
        lambda token, csrf: calendars.operate(db, token, csrf, identifier, body, "import"),
    )


@router.post("/{identifier}/unavailable")
def unavailable(
    identifier: UUID,
    body: contract.Unavailable,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    return execute(
        db,
        request,
        lambda token, csrf: calendars.operate(db, token, csrf, identifier, body, "unavailable"),
    )


@router.post("/{identifier}/forget")
def forget(
    identifier: UUID, body: Expected, request: Request, db: Annotated[Session, Depends(get_db)]
):
    return execute(
        db,
        request,
        lambda token, csrf: calendars.operate(db, token, csrf, identifier, body, "forget"),
    )


@router.post("/{identifier}/history")
def history(
    identifier: UUID,
    body: contract.History,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    return execute(
        db,
        request,
        lambda token, csrf: calendars.operate(db, token, csrf, identifier, body, "history"),
    )


@router.post("/{identifier}/export")
def export(
    identifier: UUID,
    body: contract.Export,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    response = execute(
        db,
        request,
        lambda token, csrf: calendars.operate(db, token, csrf, identifier, body, "export"),
    )
    if response.status_code == 200:
        response.headers["Content-Disposition"] = (
            'attachment; filename="butler-calendar-history-v1.json"'
        )
    return response


# Provider-mode routes (8.1). They are registered always and answer the same 404 when the synthetic
# store is not configured in development or test, so production exposes no difference from an
# unknown path. They are left out of the published schema.
def present():
    if not calendar_sync.enabled():
        raise HTTPException(status_code=404)


@router.post("/{identifier}/provider", include_in_schema=False)
def provider(
    identifier: UUID,
    body: contract.Provider,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    present()
    return execute(
        db, request, lambda token, csrf: calendar_sync.declare(db, token, csrf, identifier, body)
    )


@router.post("/{identifier}/sync-status", include_in_schema=False)
def sync_status(
    identifier: UUID, body: Scoped, request: Request, db: Annotated[Session, Depends(get_db)]
):
    present()
    return execute(
        db, request, lambda token, csrf: calendar_sync.status(db, token, csrf, identifier, body)
    )


@router.post("/{identifier}/sync", include_in_schema=False)
def sync(
    identifier: UUID,
    body: contract.Sync,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    present()
    allowed = execute(
        db, request, lambda token, csrf: calendar_sync.authorize(db, token, csrf, identifier, body)
    )
    if allowed.status_code != 200:
        return allowed
    # One bounded pass, outside the request transaction (the provider call holds no database
    # transaction); the pass never repeats.
    summary = calendar_sync.sync_source(
        sessionmaker(bind=db.get_bind(), expire_on_commit=False),
        identifier,
        explicit=True,
        resync=body.resync,
    )
    return execute(
        db,
        request,
        lambda token, csrf: calendar_sync.status(db, token, csrf, identifier, body, summary),
    )
